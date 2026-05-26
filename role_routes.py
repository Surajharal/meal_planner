"""Admin user management and AI diet plan routes (all logged-in users)."""
import logging

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from config import Config
from database import get_week_start_date
from gemini_service import GeminiService
from meal_planner import MealPlanner
from models import (
    SessionLocal,
    SignupVerification,
    User,
    AiDietPlan,
    UserRecipeFavorite,
    Meal,
)
from rbac import ALL_ROLES, ROLE_ADMIN, ROLE_GYAMA
from validators import (
    validate_ai_diet_profile,
    validate_email,
    validate_password,
    validate_role,
    validate_week_start_date,
)

logger = logging.getLogger(__name__)


def _admin_only():
    if session.get("role") != ROLE_ADMIN:
        flash("Only administrators can access that page.", "error")
        return redirect(url_for("index"))
    return None


def register_role_routes(app):
    from extensions import limiter

    @app.route("/admin/users", methods=["GET", "POST"])
    @limiter.limit("60/minute", methods=["POST"])
    def admin_users():
        redir = _admin_only()
        if redir:
            return redir
        db = SessionLocal()
        try:
            if request.method == "POST":
                action = request.form.get("action")
                if action == "create":
                    ok_e, err_e, email = validate_email(request.form.get("email") or "")
                    password = request.form.get("password") or ""
                    ok_p, err_p = validate_password(password)
                    if not ok_e:
                        flash(err_e or "Invalid email.", "error")
                    elif not ok_p:
                        flash(err_p or "Invalid password.", "error")
                    elif db.query(User).filter(User.email == email).first():
                        flash("A user with this email already exists.", "error")
                    elif db.query(User).filter(User.username == email).first():
                        flash("A user with this email already exists.", "error")
                    else:
                        db.add(
                            User(
                                username=email,
                                email=email,
                                password_hash=generate_password_hash(password),
                                role=ROLE_GYAMA,
                            )
                        )
                        db.commit()
                        flash(f"User {email} created (gyama).", "success")
                elif action == "set_role":
                    uid = request.form.get("user_id")
                    new_role = (request.form.get("role") or "").strip()
                    ok, err = validate_role(new_role)
                    if not ok:
                        flash(err, "error")
                    else:
                        try:
                            uid_int = int(uid)
                        except (TypeError, ValueError):
                            flash("Invalid user.", "error")
                        else:
                            target = db.query(User).filter(User.id == uid_int).first()
                            if not target:
                                flash("User not found.", "error")
                            elif (
                                session.get("user_id") == uid_int
                                and new_role != ROLE_ADMIN
                                and db.query(User).filter(User.role == ROLE_ADMIN).count() <= 1
                            ):
                                flash("You cannot remove the last admin.", "error")
                            else:
                                target.role = new_role
                                db.commit()
                                flash("Role updated.", "success")
                elif action == "delete":
                    uid = request.form.get("user_id")
                    try:
                        uid_int = int(uid)
                    except (TypeError, ValueError):
                        flash("Invalid user.", "error")
                    else:
                        if uid_int == session.get("user_id"):
                            flash("You cannot delete the account you are signed in with.", "error")
                        else:
                            target = db.query(User).filter(User.id == uid_int).first()
                            if not target:
                                flash("User not found.", "error")
                            else:
                                admin_count = db.query(User).filter(User.role == ROLE_ADMIN).count()
                                if target.role == ROLE_ADMIN and admin_count <= 1:
                                    flash("You cannot delete the only administrator.", "error")
                                else:
                                    db.query(AiDietPlan).filter(
                                        AiDietPlan.user_id == uid_int
                                    ).delete(synchronize_session=False)
                                    db.query(UserRecipeFavorite).filter(
                                        UserRecipeFavorite.user_id == uid_int
                                    ).delete(synchronize_session=False)
                                    db.query(Meal).filter(
                                        Meal.user_id == uid_int
                                    ).delete(synchronize_session=False)
                                    em = (target.email or "").strip()
                                    if em:
                                        db.query(SignupVerification).filter(
                                            SignupVerification.email == em
                                        ).delete(synchronize_session=False)
                                    label = target.email or target.username
                                    db.delete(target)
                                    db.commit()
                                    flash(f"User {label} has been removed.", "success")
                return redirect(url_for("admin_users"))

            users = db.query(User).order_by(User.username).all()
            return render_template("admin_users.html", users=users, all_roles=ALL_ROLES)
        finally:
            db.close()

    @app.route("/ai-diet-plan", methods=["GET", "POST"])
    @limiter.limit("12/hour", methods=["POST"])
    def ai_diet_plan():
        uid = session["user_id"]
        if request.method == "POST":
            ok, err, profile = validate_ai_diet_profile(request.form)
            if not ok:
                flash(err, "error")
                return render_template("ai_diet_plan.html", form=request.form)
            try:
                gemini = GeminiService()
                plan_text = gemini.generate_personalized_diet_plan(profile)
            except ValueError as e:
                flash(str(e), "error")
                return render_template("ai_diet_plan.html", form=request.form)
            except Exception as e:
                logger.exception("AI diet plan failed")
                flash("Could not generate a plan right now. Please try again.", "error")
                return render_template("ai_diet_plan.html", form=request.form)

            db = SessionLocal()
            try:
                row = AiDietPlan(
                    user_id=uid,
                    weight_kg=profile["weight_kg"],
                    height_cm=profile["height_cm"],
                    age=profile["age"],
                    sex=profile["sex"],
                    goal=profile["goal"],
                    activity_level=profile["activity_level"],
                    dietary_restrictions=profile.get("dietary_restrictions"),
                    allergies=profile.get("allergies"),
                    extra_notes=profile.get("extra_notes"),
                    generated_plan=plan_text,
                )
                db.add(row)
                db.commit()
                db.refresh(row)
                flash("Your personalized diet outline has been generated.", "success")
                return redirect(
                    url_for("ai_diet_plan_detail", plan_id=row.id, new="1")
                )
            finally:
                db.close()

        return render_template("ai_diet_plan.html", form=None)

    @app.route("/ai-diet-plan/history")
    def ai_diet_plan_history():
        uid = session["user_id"]
        db = SessionLocal()
        try:
            plans = (
                db.query(AiDietPlan)
                .filter(AiDietPlan.user_id == uid)
                .order_by(AiDietPlan.created_at.desc())
                .all()
            )
            return render_template("ai_diet_history.html", plans=plans)
        finally:
            db.close()

    def _parse_apply_meal_types(form) -> list:
        valid = {"Breakfast", "Lunch", "Dinner", "Snack"}
        selected = [m for m in form.getlist("meal_types") if m in valid]
        return selected or ["Dinner", "Lunch"]

    def _flash_diet_apply_result(result: dict) -> None:
        if result["message"] == "no_empty_slots":
            flash(
                "No empty meal slots for the selected meal types on upcoming days. "
                "Try another week (use the Monday of the week on Weekly Plan) or remove a meal first.",
                "warning",
            )
            return
        if result["message"] == "suggest_failed":
            flash(
                result["errors"][0]
                if result["errors"]
                else "Could not generate meals. Try again later.",
                "error",
            )
            return
        eligible = result.get("eligible", 0)
        added = result.get("added", 0)
        remaining = result.get("remaining_empty", 0)
        if added:
            msg = f"Added {added} meal(s) with new recipes"
            if eligible:
                msg += f" ({added} of {eligible} empty slots filled)"
            if remaining:
                msg += (
                    f". {remaining} empty slot(s) left — tap “Fill remaining slots” "
                    "or run again (fewer meal types = faster)."
                )
            else:
                msg += "."
            flash(msg, "success")
        if result["message"] == "quota_stopped":
            flash(
                (result["errors"][0] if result["errors"] else "API limit reached.")
                + (f" Added {added} before stopping." if added else ""),
                "warning",
            )
        elif result.get("errors"):
            flash("Some slots failed: " + "; ".join(result["errors"][:4]), "warning")
        if not added and result["message"] == "ok" and not result.get("errors"):
            flash("No meals were added.", "warning")

    @app.route("/ai-diet-plan/<int:plan_id>/apply-week", methods=["POST"])
    @limiter.limit("12/hour", methods=["POST"])
    def ai_diet_plan_apply_week(plan_id):
        """Suggest meals from diet profile and generate recipes into empty week slots."""
        uid = session["user_id"]
        role = session.get("role")
        db = SessionLocal()
        try:
            plan = db.query(AiDietPlan).filter(AiDietPlan.id == plan_id).first()
            if not plan:
                flash("Plan not found.", "error")
                return redirect(url_for("ai_diet_plan_history"))
            if plan.user_id != uid and role != ROLE_ADMIN:
                flash("You cannot use this plan.", "error")
                return redirect(url_for("ai_diet_plan_history"))

            week_raw = (request.form.get("week_start") or "").strip()
            if week_raw:
                ok_w, err_w, wk = validate_week_start_date(week_raw)
                if not ok_w:
                    flash(err_w or "Invalid week.", "error")
                    return redirect(url_for("ai_diet_plan_detail", plan_id=plan_id))
                week_start_date = get_week_start_date(wk)
            else:
                week_start_date = get_week_start_date()

            profile = {
                "age": plan.age,
                "sex": plan.sex,
                "weight_kg": plan.weight_kg,
                "height_cm": plan.height_cm,
                "goal": plan.goal,
                "activity_level": plan.activity_level,
                "dietary_restrictions": plan.dietary_restrictions,
                "allergies": plan.allergies,
                "extra_notes": plan.extra_notes,
            }
            meal_types = _parse_apply_meal_types(request.form)
            planner = MealPlanner(db)
            result = planner.apply_diet_profile_to_empty_week(
                profile,
                week_start_date,
                uid,
                max_meals=Config.DIET_APPLY_MAX_MEALS,
                meal_types=meal_types,
                assign_thumbnail=False,
            )
            _flash_diet_apply_result(result)

            if result.get("remaining_empty", 0) > 0:
                return redirect(
                    url_for(
                        "ai_diet_plan_detail",
                        plan_id=plan_id,
                        week_start=week_start_date.isoformat(),
                        filled="1",
                    )
                )
            return redirect(url_for("index", week_start=week_start_date.isoformat()))
        except ValueError as e:
            db.rollback()
            flash(str(e), "error")
            return redirect(url_for("ai_diet_plan_detail", plan_id=plan_id))
        except Exception:
            db.rollback()
            logger.exception("AI diet apply-week failed")
            flash("Could not add meals from this diet plan. Please try again.", "error")
            return redirect(url_for("ai_diet_plan_detail", plan_id=plan_id))
        finally:
            db.close()

    @app.route("/ai-diet-plan/<int:plan_id>/delete", methods=["POST"])
    @limiter.limit("60/minute", methods=["POST"])
    def ai_diet_plan_delete(plan_id):
        uid = session["user_id"]
        role = session.get("role")
        db = SessionLocal()
        try:
            plan = db.query(AiDietPlan).filter(AiDietPlan.id == plan_id).first()
            if not plan:
                flash("Plan not found.", "error")
                return redirect(url_for("ai_diet_plan_history"))
            if plan.user_id != uid and role != ROLE_ADMIN:
                flash("You cannot delete this plan.", "error")
                return redirect(url_for("ai_diet_plan_history"))
            db.delete(plan)
            db.commit()
            flash("AI diet plan deleted.", "success")
            return redirect(url_for("ai_diet_plan_history"))
        finally:
            db.close()

    @app.route("/ai-diet-plan/<int:plan_id>")
    def ai_diet_plan_detail(plan_id):
        uid = session["user_id"]
        role = session.get("role")
        db = SessionLocal()
        try:
            plan = db.query(AiDietPlan).filter(AiDietPlan.id == plan_id).first()
            if not plan:
                flash("Plan not found.", "error")
                return redirect(url_for("ai_diet_plan"))
            if plan.user_id != uid and role != ROLE_ADMIN:
                flash("You cannot view this plan.", "error")
                return redirect(url_for("ai_diet_plan_history"))
            show_new_prompt = request.args.get("new") == "1"
            week_arg = (request.args.get("week_start") or "").strip()
            if week_arg:
                ok_w, _, wk = validate_week_start_date(week_arg)
                week_start_date = get_week_start_date(wk) if ok_w else get_week_start_date()
            else:
                week_start_date = get_week_start_date()
            planner = MealPlanner(db)
            all_types = ["Dinner", "Lunch", "Breakfast", "Snack"]
            slot_stats = planner.count_empty_diet_slots(
                uid, week_start_date, ["Dinner", "Lunch"]
            )
            slot_stats_all = planner.count_empty_diet_slots(
                uid, week_start_date, all_types
            )
            show_fill_remaining = (
                request.args.get("filled") == "1"
                and slot_stats_all.get("eligible", 0) > 0
            )
            return render_template(
                "ai_diet_detail.html",
                plan=plan,
                show_new_prompt=show_new_prompt,
                week_start_date=week_start_date,
                slot_stats=slot_stats,
                slot_stats_all=slot_stats_all,
                show_fill_remaining=show_fill_remaining,
                default_meal_types=["Dinner", "Lunch"],
                all_meal_types=all_types,
            )
        finally:
            db.close()
