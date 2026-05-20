from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, abort, session
from flask_wtf.csrf import CSRFError
from sqlalchemy.orm import Session
from models import init_db, get_db, SessionLocal
from meal_planner import MealPlanner
from ingredient_manager import IngredientManager
from shopping_list import ShoppingListGenerator
from database import (
    get_recipe_by_id,
    update_recipe_image_url,
    delete_meal,
    get_all_recipes,
    get_week_start_date,
    get_favorite_recipes,
    get_favorite_recipe_ids_for_user,
    is_recipe_favorite_for_user,
    recipe_matches_diet_filter,
    recipe_matches_cuisine_filter,
    recipe_cuisine,
    recipe_is_non_vegetarian,
)
from gemini_service import GeminiService
from recipe_thumbnail_service import (
    backfill_missing_thumbnails,
    get_last_pexels_error,
    pexels_configured,
    try_set_recipe_thumbnail_from_stock,
)
from auth import ensure_admin_user_row, register_auth
from config import Config
from extensions import csrf, limiter
from rbac import ROLE_ADMIN, ROLE_GYAMA
from role_routes import register_role_routes
from production import register_production_routes
from validators import (
    validate_meal_name,
    validate_servings,
    validate_day,
    validate_meal_type,
    validate_week_start_date,
    sanitize_string,
    validate_recipe_id,
    validate_style_hint,
    validate_recipe_diet_filter,
    validate_recipe_cuisine_filter,
    validate_optional_recipe_image_url,
)
from datetime import date, timedelta
import json
import logging
import time

from werkzeug.middleware.proxy_fix import ProxyFix

def parse_week_start_date(week_start_str):
    """Parse week_start date string, handling malformed input"""
    if not week_start_str:
        return None
    
    # Clean the string - remove any query parameters or extra characters
    week_start_str = week_start_str.strip()
    
    # Split on '?' to remove query parameters if present
    if '?' in week_start_str:
        week_start_str = week_start_str.split('?')[0]
    
    # Try to parse the date
    try:
        return date.fromisoformat(week_start_str)
    except ValueError:
        # If parsing fails, return None to use default
        return None

def is_date_in_past(target_date: date) -> bool:
    """Check if a date is in the past (before today)"""
    return target_date < date.today()

def get_day_date_from_week(week_start_date: date, day_name: str) -> date:
    """Get the actual date for a day name in a given week"""
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    day_index = days.index(day_name)
    return week_start_date + timedelta(days=day_index)

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config["WTF_CSRF_ENABLED"] = True
app.config["WTF_CSRF_TIME_LIMIT"] = None
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = Config.SESSION_COOKIE_SECURE
app.config["RATELIMIT_STORAGE_URI"] = Config.RATE_LIMIT_STORAGE_URI
app.config["RATELIMIT_DEFAULT"] = Config.RATE_LIMIT_DEFAULT

csrf.init_app(app)
limiter.init_app(app)

if Config.TRUST_PROXY:
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
    )

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if Config.IS_PRODUCTION:
    if not Config.smtp_configured():
        logger.warning(
            "Production: SMTP is not configured; self-service signup cannot send OTP emails. "
            "Set SMTP_HOST, SMTP_FROM, and credentials."
        )
    weak = (Config.SECRET_KEY or "").strip()
    if len(weak) < 32 or "dev-secret" in weak.lower():
        logger.warning(
            "Production: use a long random SECRET_KEY (e.g. openssl rand -hex 32)."
        )

# Initialize database
init_db()
ensure_admin_user_row()
register_auth(app)
register_role_routes(app)
register_production_routes(app)


@app.context_processor
def inject_auth_context():
    r = session.get("role")
    return {
        "current_username": session.get("username"),
        "current_user_id": session.get("user_id"),
        "current_role": r,
        "is_admin": r == ROLE_ADMIN,
        "is_gyama": r == ROLE_GYAMA,
        # Phones on http://192.168.x.x cannot store Secure cookies (unlike localhost on Mac).
        "session_cookie_blocked_over_http": bool(
            Config.SESSION_COOKIE_SECURE and not request.is_secure
        ),
    }


@app.template_filter("meal_nutrition")
def filter_meal_nutrition(meal):
    from nutrition import scaled_nutrition_for_meal

    return scaled_nutrition_for_meal(meal)


@app.template_filter("recipe_nutrition")
def filter_recipe_nutrition(recipe):
    from nutrition import batch_nutrition_for_recipe

    return batch_nutrition_for_recipe(recipe)


@app.template_filter("meal_nutrition_per_serving")
def filter_meal_nutrition_per_serving(meal):
    from nutrition import per_serving_nutrition_for_meal

    return per_serving_nutrition_for_meal(meal)


@app.template_filter("recipe_nutrition_per_serving")
def filter_recipe_nutrition_per_serving(recipe):
    from nutrition import per_serving_nutrition_for_recipe

    return per_serving_nutrition_for_recipe(recipe)


@app.template_filter("recipe_diet_label")
def filter_recipe_diet_label(recipe):
    """vegetarian | non_vegetarian | unknown (no ingredients)."""
    if not getattr(recipe, "ingredients", None):
        return "unknown"
    return "non_vegetarian" if recipe_is_non_vegetarian(recipe) else "vegetarian"


@app.template_filter("recipe_cuisine_label")
def filter_recipe_cuisine_label(recipe):
    """Cuisine name for starter recipes, or empty string."""
    return recipe_cuisine(recipe) or ""


# Initialize services
def get_meal_planner():
    db = SessionLocal()
    return MealPlanner(db), db

def get_ingredient_manager():
    db = SessionLocal()
    return IngredientManager(db), db

def get_shopping_list_generator():
    db = SessionLocal()
    return ShoppingListGenerator(db), db

@app.route('/')
def index():
    """Home page - Weekly meal plan view"""
    db = SessionLocal()
    try:
        week_start = request.args.get('week_start')
        week_start_date = parse_week_start_date(week_start) if week_start else None
        if not week_start_date:
            week_start_date = get_week_start_date()
        
        uid = session["user_id"]
        planner = MealPlanner(db)
        weekly_plan = planner.get_weekly_plan(uid, week_start_date)
        
        # Get next and previous week
        next_week = week_start_date + timedelta(days=7)
        prev_week = week_start_date - timedelta(days=7)
        
        # Calculate date for each day of the week and check if past
        day_dates = {}
        day_is_past = {}
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        for i, day in enumerate(days):
            day_date = week_start_date + timedelta(days=i)
            day_dates[day] = day_date
            day_is_past[day] = is_date_in_past(day_date)
        
        return render_template('index.html', 
                             weekly_plan=weekly_plan,
                             week_start_date=week_start_date,
                             next_week=next_week,
                             prev_week=prev_week,
                             day_dates=day_dates,
                             day_is_past=day_is_past)
    finally:
        db.close()

@app.route('/add_meal', methods=['GET', 'POST'])
@limiter.limit("18/minute", methods=["POST"])
def add_meal():
    """Add a new meal to the plan"""
    if request.method == 'POST':
        db = SessionLocal()
        try:
            data = request.get_json()
            if not data:
                return jsonify({
                    'success': False,
                    'message': 'Invalid request data'
                }), 400
            
            # Validate meal name
            meal_name = data.get('meal_name', '').strip()
            is_valid, error_msg = validate_meal_name(meal_name)
            if not is_valid:
                return jsonify({
                    'success': False,
                    'message': error_msg
                }), 400
            meal_name = sanitize_string(meal_name)
            
            # Validate day
            day = data.get('day', '')
            is_valid, error_msg = validate_day(day)
            if not is_valid:
                return jsonify({
                    'success': False,
                    'message': error_msg
                }), 400
            
            # Validate meal type
            meal_type = data.get('meal_type', 'Dinner')
            is_valid, error_msg = validate_meal_type(meal_type)
            if not is_valid:
                return jsonify({
                    'success': False,
                    'message': error_msg
                }), 400
            
            # Validate servings
            servings = data.get('servings', 4)
            is_valid, error_msg, servings_int = validate_servings(servings)
            if not is_valid:
                return jsonify({
                    'success': False,
                    'message': error_msg
                }), 400
            
            # Validate week start date
            week_start = data.get('week_start')
            if week_start:
                is_valid, error_msg, week_start_date = validate_week_start_date(week_start)
                if not is_valid:
                    return jsonify({
                        'success': False,
                        'message': error_msg
                    }), 400
            else:
                week_start_date = get_week_start_date()
            
            # Validate that the selected day is not in the past
            day_date = get_day_date_from_week(week_start_date, day)
            if is_date_in_past(day_date):
                return jsonify({
                    'success': False,
                    'message': f'Cannot add meals for past dates. {day} ({day_date.strftime("%B %d, %Y")}) is in the past.'
                }), 400
            
            uid = session["user_id"]
            planner = MealPlanner(db)
            result = planner.generate_and_add_meal(
                meal_name=meal_name,
                day=day,
                meal_type=meal_type,
                user_id=uid,
                servings=servings_int,
                week_start_date=week_start_date
            )
            
            logger.info(f"Meal '{meal_name}' added successfully for {day}")
            
            return jsonify({
                'success': True,
                'message': f'Meal "{meal_name}" added successfully!',
                'meal_id': result['meal'].id,
                'recipe_id': result['recipe'].id
            })
        except ValueError as e:
            logger.warning(f"Validation error: {str(e)}")
            return jsonify({
                'success': False,
                'message': str(e)
            }), 400
        except Exception as e:
            logger.error(f"Error adding meal: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'message': 'An error occurred while adding the meal. Please try again.'
            }), 500
        finally:
            db.close()
    
    # GET request - show form
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    week_start_date = None
    plan_date_raw = (request.args.get("plan_date") or "").strip()
    if plan_date_raw:
        try:
            plan_date = date.fromisoformat(plan_date_raw.split("?")[0])
            week_start_date = get_week_start_date(plan_date)
        except ValueError:
            pass
    if not week_start_date:
        week_start = request.args.get('week_start')
        week_start_date = parse_week_start_date(week_start) if week_start else None
    if not week_start_date:
        week_start_date = get_week_start_date()
    
    # Check if recipe_id is provided (for quick add from recipes page)
    recipe_id = request.args.get('recipe_id')
    preselected_recipe = None
    preselected_is_favorite = False
    if recipe_id:
        try:
            is_valid, _, recipe_id_int = validate_recipe_id(recipe_id)
            if is_valid:
                db_check = SessionLocal()
                try:
                    preselected_recipe = get_recipe_by_id(db_check, recipe_id_int)
                    uid = session.get("user_id")
                    if preselected_recipe and uid:
                        preselected_is_favorite = is_recipe_favorite_for_user(
                            db_check, recipe_id_int, uid
                        )
                finally:
                    db_check.close()
        except Exception:
            pass
    
    # Calculate which days are in the past
    day_dates = {}
    day_is_past = {}
    for i, day in enumerate(days):
        day_date = week_start_date + timedelta(days=i)
        day_dates[day] = day_date
        day_is_past[day] = is_date_in_past(day_date)

    preselected_day = None
    if plan_date_raw:
        try:
            plan_date = date.fromisoformat(plan_date_raw.split("?")[0])
            if week_start_date <= plan_date < week_start_date + timedelta(days=7):
                preselected_day = days[plan_date.weekday()]
        except ValueError:
            pass
    day_arg = (request.args.get("day") or "").strip()
    if not preselected_day and day_arg:
        ok_day, _ = validate_day(day_arg)
        if ok_day and not day_is_past.get(day_arg, True):
            preselected_day = day_arg

    preselected_meal_type = "Dinner"
    meal_type_arg = (request.args.get("meal_type") or "").strip()
    if meal_type_arg:
        ok_mt, _ = validate_meal_type(meal_type_arg)
        if ok_mt:
            preselected_meal_type = meal_type_arg
    
    db_pantry = SessionLocal()
    try:
        ingredient_manager = IngredientManager(db_pantry)
        available_raw = ingredient_manager.get_available_ingredients(week_start_date)
        pantry_items = sorted(
            [
                {'name': v['name'], 'quantity': v['quantity'], 'unit': v['unit']}
                for v in available_raw.values()
            ],
            key=lambda x: x['name'].lower(),
        )
        has_pantry = len(pantry_items) > 0
    finally:
        db_pantry.close()
    
    open_pantry_tab = request.args.get('tab') == 'pantry' and has_pantry
    
    return render_template(
        'add_meal.html',
        week_start_date=week_start_date,
        day_dates=day_dates,
        day_is_past=day_is_past,
        preselected_day=preselected_day,
        preselected_meal_type=preselected_meal_type,
        preselected_recipe=preselected_recipe,
        preselected_is_favorite=preselected_is_favorite,
        pantry_items=pantry_items,
        has_pantry=has_pantry,
        open_pantry_tab=open_pantry_tab,
    )

_PENDING_PANTRY_RECIPE_TTL_SEC = 900


@app.route('/add_meal_from_pantry', methods=['POST'])
@limiter.limit("8/minute")
def add_meal_from_pantry():
    """Generate a recipe from pantry (step 1), then confirm add to plan (step 2)."""
    db = SessionLocal()
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400

        mode = (data.get('mode') or 'generate').strip().lower()

        if mode == 'cancel_pending':
            session.pop('pending_pantry_recipe_id', None)
            session.pop('pending_pantry_recipe_expiry', None)
            return jsonify({
                'success': True,
                'message': 'The recipe stays in your shared Recipes list — it was not added to this week.',
            })

        if mode == 'confirm':
            if not data.get('confirmed'):
                return jsonify({
                    'success': False,
                    'message': 'Please confirm adding this recipe to your plan.',
                }), 400

            recipe_id = data.get('recipe_id')
            is_valid, error_msg, recipe_id_int = validate_recipe_id(recipe_id)
            if not is_valid:
                return jsonify({'success': False, 'message': error_msg}), 400

            pending = session.get('pending_pantry_recipe_id')
            pending_exp = float(session.get('pending_pantry_recipe_expiry') or 0)
            if pending != recipe_id_int or time.time() > pending_exp:
                return jsonify({
                    'success': False,
                    'message': 'This recipe is no longer pending. Generate again from the pantry tab.',
                }), 400

            day = data.get('day', '')
            is_valid, error_msg = validate_day(day)
            if not is_valid:
                return jsonify({'success': False, 'message': error_msg}), 400

            meal_type = data.get('meal_type', 'Dinner')
            is_valid, error_msg = validate_meal_type(meal_type)
            if not is_valid:
                return jsonify({'success': False, 'message': error_msg}), 400

            servings = data.get('servings', 4)
            is_valid, error_msg, servings_int = validate_servings(servings)
            if not is_valid:
                return jsonify({'success': False, 'message': error_msg}), 400

            week_start = data.get('week_start')
            if week_start:
                is_valid, error_msg, week_start_date = validate_week_start_date(week_start)
                if not is_valid:
                    return jsonify({'success': False, 'message': error_msg}), 400
            else:
                week_start_date = get_week_start_date()

            day_date = get_day_date_from_week(week_start_date, day)
            if is_date_in_past(day_date):
                return jsonify({
                    'success': False,
                    'message': f'Cannot add meals for past dates. {day} ({day_date.strftime("%B %d, %Y")}) is in the past.',
                }), 400

            recipe = get_recipe_by_id(db, recipe_id_int)
            if not recipe:
                session.pop('pending_pantry_recipe_id', None)
                session.pop('pending_pantry_recipe_expiry', None)
                return jsonify({'success': False, 'message': 'Recipe not found.'}), 404

            uid = session["user_id"]
            planner = MealPlanner(db)
            result = planner.add_existing_recipe_to_meal(
                recipe_id_int,
                day,
                meal_type,
                uid,
                servings_int,
                week_start_date,
            )
            session.pop('pending_pantry_recipe_id', None)
            session.pop('pending_pantry_recipe_expiry', None)
            logger.info(
                'Pantry recipe %s confirmed on %s %s',
                recipe_id_int,
                day,
                meal_type,
            )
            return jsonify({
                'success': True,
                'message': f'Added "{result["recipe"].name}" to {day} ({meal_type}).',
                'meal_id': result['meal'].id,
                'recipe_id': recipe_id_int,
            })

        # mode == generate
        if not data.get('confirmed'):
            return jsonify({
                'success': False,
                'message': 'Please confirm that you want AI to generate a recipe from your pantry ingredients.',
            }), 400

        week_start = data.get('week_start')
        if week_start:
            is_valid, error_msg, week_start_date = validate_week_start_date(week_start)
            if not is_valid:
                return jsonify({'success': False, 'message': error_msg}), 400
        else:
            week_start_date = get_week_start_date()

        is_valid, error_msg, style_hint = validate_style_hint(data.get('style_hint', ''))
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400

        ingredient_manager = IngredientManager(db)
        available_raw = ingredient_manager.get_available_ingredients(week_start_date)
        if not available_raw:
            return jsonify({
                'success': False,
                'message': 'No available ingredients in inventory for this week. Add quantities on the Inventory page first.',
            }), 400

        pantry_entries = list(available_raw.values())
        planner = MealPlanner(db)
        result = planner.generate_recipe_from_pantry_only(
            pantry_entries=pantry_entries,
            meal_type='Dinner',
            servings=4,
            style_hint=style_hint,
        )
        recipe = result['recipe']
        session['pending_pantry_recipe_id'] = recipe.id
        session['pending_pantry_recipe_expiry'] = time.time() + _PENDING_PANTRY_RECIPE_TTL_SEC

        desc = (recipe.description or '')[:400]
        logger.info('Pantry recipe generated (pending confirm): %s id=%s', recipe.name, recipe.id)
        return jsonify({
            'success': True,
            'pending': True,
            'recipe_id': recipe.id,
            'name': recipe.name,
            'description': desc,
            'prep_time': recipe.prep_time,
            'cook_time': recipe.cook_time,
            'servings': recipe.servings,
            'meal_type': 'Dinner',
            'message': f'Generated “{recipe.name}”. Do you want to add it to your weekly plan?',
        })
    except ValueError as e:
        logger.warning('Pantry meal validation: %s', str(e))
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        logger.error('Error adding pantry meal: %s', str(e), exc_info=True)
        return jsonify({
            'success': False,
            'message': 'An error occurred while generating the recipe. Please try again.',
        }), 500
    finally:
        db.close()

@app.route('/meal/<int:meal_id>')
def view_meal(meal_id):
    """View detailed meal information"""
    db = SessionLocal()
    try:
        planner = MealPlanner(db)
        meal_details = planner.get_meal_details(meal_id, session["user_id"])
        
        if not meal_details:
            flash('Meal not found', 'error')
            return redirect(url_for('index'))
        
        return render_template('meal_details.html', meal_details=meal_details)
    finally:
        db.close()

@app.route('/recipe/<int:recipe_id>')
def view_recipe(recipe_id):
    """View detailed recipe information"""
    db = SessionLocal()
    try:
        recipe = get_recipe_by_id(db, recipe_id)
        
        if not recipe:
            flash('Recipe not found', 'error')
            return redirect(url_for('recipes'))
        
        # Get ingredients for the recipe
        ingredients = [
            {
                'id': ri.ingredient.id,
                'name': ri.ingredient.name,
                'quantity': ri.quantity,
                'unit': ri.unit,
                'category': ri.ingredient.category
            }
            for ri in recipe.ingredients
        ]
        
        uid = session.get("user_id")
        recipe_favorited = (
            is_recipe_favorite_for_user(db, recipe_id, uid) if uid else False
        )

        recipe_details = {
            'recipe': recipe,
            'ingredients': ingredients,
        }

        return render_template(
            'recipe_details.html',
            recipe_details=recipe_details,
            recipe_favorited=recipe_favorited,
        )
    finally:
        db.close()


@app.route("/recipe/<int:recipe_id>/stock-thumbnail", methods=["POST"])
@limiter.limit("45/minute")
def recipe_apply_stock_thumbnail(recipe_id):
    """Search Pexels by recipe name and set image_url (requires PEXELS_API_KEY)."""
    db = SessionLocal()
    try:
        if not pexels_configured():
            return jsonify(
                {
                    "success": False,
                    "message": "Stock photos are not configured. Add PEXELS_API_KEY to .env (free at pexels.com/api).",
                }
            ), 400
        recipe = get_recipe_by_id(db, recipe_id)
        if not recipe:
            return jsonify({"success": False, "message": "Recipe not found"}), 404
        if recipe.image_url:
            return jsonify(
                {
                    "success": True,
                    "message": "Recipe already has a photo. Remove it first to search again.",
                    "image_url": recipe.image_url,
                }
            )
        if not try_set_recipe_thumbnail_from_stock(db, recipe):
            err = get_last_pexels_error()
            if err and "No matching stock photo found" not in err and "No confident stock photo match found" not in err:
                return jsonify({"success": False, "message": err}), 502
            return jsonify(
                {
                    "success": False,
                    "message": "No stock photo matched this recipe name. Try another name or paste an image URL.",
                }
            ), 404
        return jsonify(
            {
                "success": True,
                "message": "Stock photo added from Pexels.",
                "image_url": recipe.image_url,
            }
        )
    finally:
        db.close()


@app.route("/recipe/<int:recipe_id>/image", methods=["POST"])
@limiter.limit("60/minute")
def update_recipe_image(recipe_id):
    """Set or clear shared recipe cover image URL (admin only)."""
    db = SessionLocal()
    try:
        if session.get("role") != ROLE_ADMIN:
            return jsonify({"success": False, "message": "Only admin can edit recipe photos."}), 403
        data = request.get_json(silent=True) or {}
        raw = data.get("image_url")
        if raw is None:
            raw_s = ""
        elif isinstance(raw, str):
            raw_s = raw
        else:
            raw_s = str(raw)
        ok, err, url = validate_optional_recipe_image_url(raw_s)
        if not ok:
            return jsonify({"success": False, "message": err or "Invalid URL"}), 400
        recipe = update_recipe_image_url(db, recipe_id, url)
        if not recipe:
            return jsonify({"success": False, "message": "Recipe not found"}), 404
        return jsonify(
            {
                "success": True,
                "message": "Image updated" if url else "Image removed",
                "image_url": recipe.image_url,
            }
        )
    finally:
        db.close()


@app.route("/copy_week", methods=["POST"])
@limiter.limit("15/minute", methods=["POST"])
def copy_week():
    """Copy meals from a source week into empty slots on the target week."""
    target_raw = request.form.get("target_week") or ""
    source_raw = request.form.get("source_week") or ""
    target_week = parse_week_start_date(target_raw) or get_week_start_date()
    source_week = parse_week_start_date(source_raw)
    if not source_week:
        flash("Invalid source week.", "error")
        return redirect(url_for("index", week_start=target_week.isoformat()))

    db = SessionLocal()
    try:
        planner = MealPlanner(db)
        result = planner.copy_week_plan(session["user_id"], source_week, target_week)
        if result["copied"]:
            flash(
                f"Copied {result['copied']} meal(s) from the previous week "
                f"({result['skipped']} slot(s) skipped — already filled or in the past).",
                "success",
            )
        else:
            flash(
                "No meals were copied. Slots may already be filled or dates are in the past.",
                "warning",
            )
    except Exception as e:
        logger.error("copy_week failed: %s", e, exc_info=True)
        flash("Could not copy the week. Please try again.", "error")
    finally:
        db.close()

    return redirect(url_for("index", week_start=target_week.isoformat()))


@app.route("/recipe/<int:recipe_id>/regenerate", methods=["POST"])
@limiter.limit("8/minute", methods=["POST"])
def regenerate_recipe_route(recipe_id):
    """AI-regenerate a shared recipe (updates for all users)."""
    ok_rid, err_rid, recipe_id_int = validate_recipe_id(recipe_id)
    if not ok_rid:
        return jsonify({"success": False, "message": err_rid}), 400

    data = request.get_json(silent=True) or {}
    ok_t, err_t, tweak = validate_style_hint(data.get("tweak", ""))
    if not ok_t:
        return jsonify({"success": False, "message": err_t}), 400

    db = SessionLocal()
    try:
        planner = MealPlanner(db)
        updated, err = planner.regenerate_shared_recipe(recipe_id_int, tweak)
        if err or not updated:
            return jsonify(
                {"success": False, "message": err or "Recipe not found"}
            ), 404 if err == "Recipe not found" else 500
        return jsonify(
            {
                "success": True,
                "message": "Recipe regenerated. This updates the shared library for everyone.",
                "recipe_id": updated.id,
                "redirect": url_for("view_recipe", recipe_id=updated.id),
            }
        )
    except Exception as e:
        logger.error("regenerate_recipe failed: %s", e, exc_info=True)
        return jsonify(
            {"success": False, "message": "AI regeneration failed. Try again in a moment."}
        ), 500
    finally:
        db.close()


@app.route('/delete_meal/<int:meal_id>', methods=['POST'])
@limiter.limit("90/minute")
def delete_meal_route(meal_id):
    """Delete a meal from the plan"""
    db = SessionLocal()
    try:
        if delete_meal(db, meal_id, session["user_id"]):
            return jsonify({'success': True, 'message': 'Meal deleted successfully'})
        else:
            return jsonify({'success': False, 'message': 'Meal not found'}), 404
    finally:
        db.close()

@app.route('/inventory')
def inventory():
    """Ingredient inventory management"""
    db = SessionLocal()
    try:
        week_start = request.args.get('week_start')
        week_start_date = parse_week_start_date(week_start) if week_start else None
        if not week_start_date:
            week_start_date = get_week_start_date()
        
        uid = session["user_id"]
        ingredient_manager = IngredientManager(db)
        comparison = ingredient_manager.compare_required_vs_available(uid, week_start_date)
        required = ingredient_manager.get_required_ingredients_for_week(uid, week_start_date)
        available = ingredient_manager.get_available_ingredients(week_start_date)
        categorized = ingredient_manager.get_ingredients_by_category()
        
        return render_template('inventory.html',
                             comparison=comparison,
                             required=required,
                             available=available,
                             categorized=categorized,
                             week_start_date=week_start_date)
    finally:
        db.close()

@app.route('/update_inventory', methods=['POST'])
@limiter.limit("120/minute")
def update_inventory_route():
    """Update ingredient availability"""
    db = SessionLocal()
    try:
        data = request.get_json()
        ingredient_id = int(data.get('ingredient_id'))
        quantity = float(data.get('quantity', 0))
        unit = data.get('unit', 'unit')
        available = data.get('available', True)
        week_start = data.get('week_start')
        week_start_date = parse_week_start_date(week_start) if week_start else None
        if not week_start_date:
            week_start_date = get_week_start_date()
        
        ingredient_manager = IngredientManager(db)
        ingredient_manager.update_ingredient_availability(
            ingredient_id=ingredient_id,
            quantity=quantity,
            unit=unit,
            available=available,
            week_start_date=week_start_date
        )
        
        return jsonify({'success': True, 'message': 'Inventory updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400
    finally:
        db.close()

@app.route('/shopping_list')
def shopping_list():
    """Generate and display shopping list"""
    db = SessionLocal()
    try:
        week_start = request.args.get('week_start')
        week_start_date = parse_week_start_date(week_start) if week_start else None
        if not week_start_date:
            week_start_date = get_week_start_date()
        
        uid = session["user_id"]
        generator = ShoppingListGenerator(db)
        shopping_list_data = generator.generate_shopping_list(uid, week_start_date)
        summary = generator.get_shopping_list_summary(uid, week_start_date)
        
        return render_template('shopping_list.html',
                             shopping_list=shopping_list_data,
                             summary=summary,
                             week_start_date=week_start_date)
    finally:
        db.close()

@app.route('/suggest_meals', methods=['POST'])
@limiter.limit("20/minute")
def suggest_meals():
    """Get meal suggestions from Gemini"""
    try:
        data = request.get_json()
        preferences = data.get('preferences', '')
        dietary_restrictions = data.get('dietary_restrictions', '')
        
        gemini = GeminiService()
        suggestions = gemini.suggest_meals(preferences, dietary_restrictions)
        
        return jsonify({
            'success': True,
            'suggestions': suggestions
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 400

@app.route('/api/pantry-ingredients')
def api_pantry_ingredients():
    """Available inventory ingredients for the week (for pantry recipe UI)."""
    db = SessionLocal()
    try:
        week_start = request.args.get('week_start')
        week_start_date = parse_week_start_date(week_start) if week_start else None
        if not week_start_date:
            week_start_date = get_week_start_date()
        ingredient_manager = IngredientManager(db)
        available_raw = ingredient_manager.get_available_ingredients(week_start_date)
        items = sorted(
            [
                {
                    'id': v['ingredient_id'],
                    'name': v['name'],
                    'quantity': v['quantity'],
                    'unit': v['unit'],
                }
                for v in available_raw.values()
            ],
            key=lambda x: x['name'].lower(),
        )
        return jsonify({'success': True, 'ingredients': items})
    finally:
        db.close()

@app.route('/api/recipes')
def api_recipes():
    """API endpoint to get all recipes as JSON"""
    from nutrition import batch_nutrition_for_recipe

    db = SessionLocal()
    try:
        recipes_list = get_all_recipes(db)
        uid = session.get("user_id")
        fav_ids = get_favorite_recipe_ids_for_user(db, uid) if uid else set()
        out = []
        for r in recipes_list:
            row = {
                'id': r.id,
                'name': r.name,
                'description': r.description,
                'prep_time': r.prep_time,
                'cook_time': r.cook_time,
                'servings': r.servings,
                'image_url': getattr(r, "image_url", None),
                'is_favorite': r.id in fav_ids,
            }
            nb = batch_nutrition_for_recipe(r)
            if nb:
                row['nutrition'] = nb
            out.append(row)
        return jsonify({'success': True, 'recipes': out})
    finally:
        db.close()

@app.route('/add_existing_recipe', methods=['POST'])
@limiter.limit("30/minute")
def add_existing_recipe():
    """Add an existing recipe to meal plan"""
    db = SessionLocal()
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Invalid request data'}), 400
        
        # Validate inputs
        recipe_id = data.get('recipe_id')
        is_valid, error_msg, recipe_id_int = validate_recipe_id(recipe_id)
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400
        
        day = data.get('day', '')
        is_valid, error_msg = validate_day(day)
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400
        
        meal_type = data.get('meal_type', 'Dinner')
        is_valid, error_msg = validate_meal_type(meal_type)
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400
        
        servings = data.get('servings', 4)
        is_valid, error_msg, servings_int = validate_servings(servings)
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400
        
        week_start = data.get('week_start')
        if week_start:
            is_valid, error_msg, week_start_date = validate_week_start_date(week_start)
            if not is_valid:
                return jsonify({'success': False, 'message': error_msg}), 400
        else:
            week_start_date = get_week_start_date()
        
        # Validate that the selected day is not in the past
        day_date = get_day_date_from_week(week_start_date, day)
        if is_date_in_past(day_date):
            return jsonify({
                'success': False,
                'message': f'Cannot add meals for past dates. {day} ({day_date.strftime("%B %d, %Y")}) is in the past.'
            }), 400
        
        uid = session["user_id"]
        planner = MealPlanner(db)
        result = planner.add_existing_recipe_to_meal(
            recipe_id_int,
            day,
            meal_type,
            uid,
            servings_int,
            week_start_date,
        )
        
        logger.info(f"Existing recipe {recipe_id_int} added to meal plan for {day}")
        
        return jsonify({
            'success': True,
            'message': f'Recipe "{result["recipe"].name}" added to meal plan!',
            'meal_id': result['meal'].id,
            'recipe_id': result['recipe'].id
        })
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        logger.error(f"Error adding existing recipe: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': 'An error occurred. Please try again.'}), 500
    finally:
        db.close()

@app.route('/recipes')
def recipes():
    """View all recipes with search and filter"""
    db = SessionLocal()
    try:
        from database import search_recipes, filter_recipes_by_category

        uid = session.get("user_id")
        fav_ids = get_favorite_recipe_ids_for_user(db, uid) if uid else set()

        show_favorites = request.args.get('favorites', 'false').lower() == 'true'
        search_term = request.args.get('search', '').strip()
        category_filter = request.args.get('category', '').strip()
        ok_diet, _, diet_filter = validate_recipe_diet_filter(
            request.args.get("diet", "")
        )
        if not ok_diet:
            diet_filter = ""

        ok_cuisine, _, cuisine_filter = validate_recipe_cuisine_filter(
            request.args.get("cuisine", "")
        )
        if not ok_cuisine:
            cuisine_filter = ""

        if show_favorites:
            recipes_list = get_favorite_recipes(db, uid) if uid else []
        else:
            recipes_list = get_all_recipes(db)
        
        # Apply search filter
        if search_term:
            recipes_list = [r for r in recipes_list if 
                          search_term.lower() in r.name.lower() or 
                          (r.description and search_term.lower() in r.description.lower())]
        
        # Apply category filter
        if category_filter:
            # Filter recipes that have ingredients in the specified category
            filtered = []
            for recipe in recipes_list:
                for ri in recipe.ingredients:
                    if category_filter.lower() in ri.ingredient.category.lower():
                        filtered.append(recipe)
                        break
            recipes_list = filtered

        if diet_filter:
            recipes_list = [
                r for r in recipes_list if recipe_matches_diet_filter(r, diet_filter)
            ]

        if cuisine_filter:
            recipes_list = [
                r for r in recipes_list
                if recipe_matches_cuisine_filter(r, cuisine_filter)
            ]

        # Get unique categories for filter dropdown
        all_recipes = get_all_recipes(db)
        categories = set()
        for recipe in all_recipes:
            for ri in recipe.ingredients:
                categories.add(ri.ingredient.category)
        categories = sorted(list(categories))

        week_start_date = get_week_start_date()

        from starter_recipes import STARTER_CUISINES

        return render_template(
            'recipes.html',
            recipes=recipes_list,
            show_favorites=show_favorites,
            search_term=search_term,
            category_filter=category_filter,
            diet_filter=diet_filter,
            cuisine_filter=cuisine_filter,
            cuisine_options=list(STARTER_CUISINES),
            categories=categories,
            favorite_recipe_ids=fav_ids,
            week_start_date=week_start_date,
            stock_thumbnails_available=pexels_configured(),
        )
    except Exception as e:
        logger.error(f"Error loading recipes: {str(e)}", exc_info=True)
        flash('An error occurred while loading recipes', 'error')
        return render_template(
            'recipes.html',
            recipes=[],
            show_favorites=False,
            search_term='',
            category_filter='',
            diet_filter='',
            cuisine_filter='',
            cuisine_options=[],
            categories=[],
            favorite_recipe_ids=set(),
            week_start_date=get_week_start_date(),
            stock_thumbnails_available=pexels_configured(),
        )
    finally:
        db.close()


@app.route("/recipes/backfill-thumbnails", methods=["POST"])
@limiter.limit("8/hour")
def recipes_backfill_thumbnails():
    """Batch: set Pexels thumbnails for recipes that have no image_url."""
    if not session.get("user_id"):
        return jsonify({"success": False, "message": "Sign in required."}), 401
    db = SessionLocal()
    try:
        data = request.get_json(silent=True) or {}
        raw_limit = data.get("limit", 15)
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = 15
        updated, remainder = backfill_missing_thumbnails(db, limit)
        err = get_last_pexels_error()
        if updated == 0 and remainder > 0 and err and "No matching stock photo found" not in err and "No confident stock photo match found" not in err:
            return jsonify({"success": False, "message": err}), 502
        return jsonify(
            {
                "success": True,
                "updated": updated,
                "checked_without_new_image": remainder,
                "message": f"Added {updated} photo(s). {remainder} recipe(s) still without a match (or already had a URL).",
            }
        )
    finally:
        db.close()


@app.route('/toggle_favorite/<int:recipe_id>', methods=['POST'])
@limiter.limit("120/minute")
def toggle_favorite(recipe_id):
    """Toggle favorite status of a recipe"""
    db = SessionLocal()
    try:
        uid = session.get("user_id")
        if not uid:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401

        # Validate recipe ID
        is_valid, error_msg, recipe_id_int = validate_recipe_id(recipe_id)
        if not is_valid:
            return jsonify({'success': False, 'message': error_msg}), 400

        from database import toggle_recipe_favorite

        recipe, is_fav = toggle_recipe_favorite(db, recipe_id_int, uid)
        logger.info(
            "Recipe %s favorite for user %s toggled to %s",
            recipe_id_int,
            uid,
            is_fav,
        )

        return jsonify({
            'success': True,
            'is_favorite': is_fav,
            'message': 'Recipe added to favorites' if is_fav else 'Recipe removed from favorites',
        })
    except ValueError as e:
        logger.warning(f"Recipe not found: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 404
    except Exception as e:
        logger.error(f"Error toggling favorite: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': 'An error occurred. Please try again.'}), 500
    finally:
        db.close()

# Error handlers
@app.errorhandler(CSRFError)
def handle_csrf_error(error):
    if (
        request.path.startswith("/api/")
        or request.is_json
        or (request.content_type and "json" in request.content_type)
    ):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Security token missing or expired. Refresh the page and try again.",
                }
            ),
            400,
        )
    flash("Your session expired or the form was invalid. Please try again.", "error")
    return redirect(request.referrer or url_for("login"))


@app.errorhandler(404)
def not_found_error(error):
    logger.warning(f"404 error: {request.url}")
    return render_template('error.html',
                         error_code=404,
                         error_title="Page Not Found",
                         error_message="The page you're looking for doesn't exist."), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"500 error: {str(error)}", exc_info=True)
    return render_template('error.html',
                         error_code=500,
                         error_title="Internal Server Error",
                         error_message="Something went wrong on our end. We're working on it!"), 500

@app.errorhandler(400)
def bad_request_error(error):
    logger.warning(f"400 error: {str(error)}")
    return render_template('error.html',
                         error_code=400,
                         error_title="Bad Request",
                         error_message="Invalid request. Please check your input and try again."), 400

if __name__ == '__main__':
    # Validate configuration
    try:
        from config import Config
        Config.validate()
    except ValueError as e:
        print(f"Configuration Error: {e}")
        print("Please create a .env file with GEMINI_API_KEY")
        exit(1)
    
    app.run(debug=True, host='0.0.0.0', port=5010)
