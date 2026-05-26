from sqlalchemy.orm import Session
from database import (
    create_recipe,
    add_ingredient_to_recipe,
    create_meal,
    get_weekly_meals,
    get_meal_by_id_for_user,
    get_accessible_recipe_by_id,
    get_recipe_by_id,
    get_or_create_ingredient,
    create_recipe_from_ai_data,
    replace_recipe_from_ai_data,
)
from gemini_service import GeminiService
from nutrition import nutrition_fields_from_ai_recipe
from recipe_thumbnail_service import assign_recipe_thumbnail
from validators import validate_meal_name
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

from database import get_week_start_date
from config import Config

_DAYS_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
_ALL_MEAL_TYPES = ["Dinner", "Lunch", "Breakfast", "Snack"]
_DEFAULT_APPLY_MEAL_TYPES = ["Dinner", "Lunch"]


def _collect_empty_diet_slots(
    plan_grid: Dict,
    week_start_date: date,
    meal_types: List[str],
) -> tuple[List[Dict[str, str]], Dict[str, int]]:
    """Empty future slots in fill order (Dinner → Lunch → Breakfast → Snack per day)."""
    empty_slots: List[Dict[str, str]] = []
    skipped_past = 0
    skipped_occupied = 0
    for day in _DAYS_ORDER:
        for mt in meal_types:
            if mt not in _ALL_MEAL_TYPES:
                continue
            if plan_grid[day][mt] is not None:
                skipped_occupied += 1
                continue
            slot_date = week_start_date + timedelta(days=_DAYS_ORDER.index(day))
            if slot_date < date.today():
                skipped_past += 1
                continue
            empty_slots.append({"day": day, "meal_type": mt})
    return empty_slots, {
        "skipped_past": skipped_past,
        "skipped_occupied": skipped_occupied,
        "eligible": len(empty_slots),
    }


class MealPlanner:
    def __init__(self, db: Session):
        self.db = db
        self.gemini = GeminiService()

    # Batch this many slots per Gemini call when filling the week (fewer API requests vs 1 recipe per slot).
    _AI_PLAN_RECIPE_BATCH_SIZE = 5

    def count_empty_diet_slots(
        self,
        user_id: int,
        week_start_date: date,
        meal_types: Optional[List[str]] = None,
    ) -> Dict:
        """Stats for empty future slots on a week (no AI calls)."""
        types = meal_types or list(_DEFAULT_APPLY_MEAL_TYPES)
        plan_grid = self.get_weekly_plan(user_id, week_start_date)
        _, stats = _collect_empty_diet_slots(plan_grid, week_start_date, types)
        return stats

    def _add_generated_recipe_to_plan(
        self,
        recipe_data: Dict,
        day: str,
        meal_type: str,
        user_id: int,
        servings: int = 4,
        week_start_date: date = None,
        assign_thumbnail: bool = True,
    ) -> Dict:
        """Persist AI recipe JSON and a meal row (no extra Gemini call)."""
        instructions = recipe_data["instructions"]
        if isinstance(instructions, list):
            instructions = "\n".join(str(step) for step in instructions)

        cal, prot, carb, fat = nutrition_fields_from_ai_recipe(recipe_data)
        recipe = create_recipe(
            self.db,
            name=recipe_data["name"],
            description=recipe_data.get("description", ""),
            instructions=instructions,
            prep_time=recipe_data.get("prep_time", 0),
            cook_time=recipe_data.get("cook_time", 0),
            servings=recipe_data.get("servings", servings),
            calories_kcal=cal,
            protein_g=prot,
            carbs_g=carb,
            fat_g=fat,
        )

        for ing in recipe_data.get("ingredients", []):
            add_ingredient_to_recipe(
                self.db,
                recipe_id=recipe.id,
                ingredient_name=ing["name"],
                quantity=ing["quantity"],
                unit=ing.get("unit", "unit"),
                category=ing.get("category", "other"),
            )

        if assign_thumbnail:
            assign_recipe_thumbnail(self.db, recipe)

        meal = create_meal(
            self.db,
            day=day,
            meal_type=meal_type,
            recipe_id=recipe.id,
            user_id=user_id,
            servings=servings,
            week_start_date=week_start_date,
        )

        return {
            "meal": meal,
            "recipe": recipe,
            "ingredients": recipe_data.get("ingredients", []),
        }
    
    def generate_and_add_meal(
        self,
        meal_name: str,
        day: str,
        meal_type: str,
        user_id: int,
        servings: int = 4,
        week_start_date: date = None,
    ) -> Dict:
        """Generate a recipe using Gemini and add it to the meal plan"""
        recipe_data = self.gemini.generate_recipe(meal_name, meal_type, servings)
        return self._add_generated_recipe_to_plan(
            recipe_data, day, meal_type, user_id, servings, week_start_date
        )
    
    def generate_recipe_from_pantry_only(
        self,
        pantry_entries: List[Dict],
        meal_type: str,
        servings: int = 4,
        style_hint: str = "",
    ) -> Dict:
        """AI recipe from pantry only (no meal row). Shared library entry."""
        sorted_entries = sorted(
            pantry_entries,
            key=lambda e: e.get("name", "").lower(),
        )
        pantry_lines = [
            f"{e['name']}: {e['quantity']} {e['unit']}"
            for e in sorted_entries
        ]
        recipe_data = self.gemini.generate_recipe_from_pantry(
            pantry_lines, meal_type, servings, style_hint or ""
        )
        instructions = recipe_data["instructions"]
        if isinstance(instructions, list):
            instructions = "\n".join(str(step) for step in instructions)
        cal, prot, carb, fat = nutrition_fields_from_ai_recipe(recipe_data)
        recipe = create_recipe(
            self.db,
            name=recipe_data["name"],
            description=recipe_data.get("description", ""),
            instructions=instructions,
            prep_time=recipe_data.get("prep_time", 0),
            cook_time=recipe_data.get("cook_time", 0),
            servings=recipe_data.get("servings", servings),
            calories_kcal=cal,
            protein_g=prot,
            carbs_g=carb,
            fat_g=fat,
        )
        for ing in recipe_data.get("ingredients", []):
            add_ingredient_to_recipe(
                self.db,
                recipe_id=recipe.id,
                ingredient_name=ing["name"],
                quantity=ing["quantity"],
                unit=ing.get("unit", "unit"),
                category=ing.get("category", "other"),
            )
        assign_recipe_thumbnail(self.db, recipe)
        return {
            "recipe": recipe,
            "ingredients": recipe_data.get("ingredients", []),
        }

    def generate_and_add_meal_from_pantry(
        self,
        pantry_entries: List[Dict],
        day: str,
        meal_type: str,
        user_id: int,
        servings: int = 4,
        week_start_date: date = None,
        style_hint: str = "",
    ) -> Dict:
        """Generate a recipe constrained to pantry ingredients and add to the meal plan."""
        built = self.generate_recipe_from_pantry_only(
            pantry_entries, meal_type, servings, style_hint
        )
        recipe = built["recipe"]
        meal = create_meal(
            self.db,
            day=day,
            meal_type=meal_type,
            recipe_id=recipe.id,
            user_id=user_id,
            servings=servings,
            week_start_date=week_start_date,
        )
        return {
            "meal": meal,
            "recipe": recipe,
            "ingredients": built.get("ingredients", []),
        }
    
    def add_existing_recipe_to_meal(
        self,
        recipe_id: int,
        day: str,
        meal_type: str,
        user_id: int,
        servings: int = 4,
        week_start_date: date = None,
    ) -> Dict:
        """Add an existing recipe to a meal plan"""
        recipe = get_accessible_recipe_by_id(self.db, recipe_id, user_id)
        if not recipe:
            raise ValueError(f"Recipe with ID {recipe_id} not found")
        
        meal = create_meal(
            self.db,
            day=day,
            meal_type=meal_type,
            recipe_id=recipe_id,
            user_id=user_id,
            servings=servings,
            week_start_date=week_start_date
        )
        
        return {
            'meal': meal,
            'recipe': recipe
        }
    
    def get_weekly_plan(self, user_id: int, week_start_date: date = None) -> Dict:
        """Get the complete weekly meal plan organized by day for one user."""
        if week_start_date is None:
            week_start_date = get_week_start_date()

        meals = get_weekly_meals(self.db, user_id, week_start_date)
        
        # Organize by day and meal type
        plan = {}
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        
        for day in days:
            plan[day] = {
                'Breakfast': None,
                'Lunch': None,
                'Dinner': None,
                'Snack': None
            }
        
        for meal in meals:
            if meal.day in plan and meal.meal_type in plan[meal.day]:
                plan[meal.day][meal.meal_type] = meal
        
        return plan
    
    def get_meal_details(self, meal_id: int, user_id: int) -> Optional[Dict]:
        """Get detailed information about a meal for this user."""
        meal = get_meal_by_id_for_user(self.db, meal_id, user_id)
        
        if not meal:
            return None
        
        recipe = get_recipe_by_id(self.db, meal.recipe_id)
        if not recipe:
            return None
        
        return {
            'meal': meal,
            'recipe': recipe,
            'ingredients': [
                {
                    'id': ri.ingredient.id,
                    'name': ri.ingredient.name,
                    'quantity': ri.quantity,
                    'unit': ri.unit,
                    'category': ri.ingredient.category
                }
                for ri in recipe.ingredients
            ]
        }

    def _quota_error_message(self) -> str:
        return (
            "Gemini API quota or rate limit (free tier is small). "
            "Wait a few minutes, try again later, or enable billing in Google AI Studio. "
            "https://ai.google.dev/gemini-api/docs/rate-limits"
        )

    def _is_quota_error(self, ex: Exception) -> bool:
        em = str(ex)
        return "429" in em or "quota" in em.lower()

    def _generate_recipes_for_chunk(
        self,
        profile: Dict,
        chunk: List[Dict[str, str]],
        errors: List[str],
    ) -> List[Dict]:
        """Batched Gemini call; on failure retry each slot once (unless quota)."""
        try:
            return self.gemini.generate_full_recipes_for_plan_slots(
                profile, chunk, servings=4
            )
        except Exception as ex:
            if self._is_quota_error(ex):
                raise
            if len(chunk) == 1:
                slot = chunk[0]
                errors.append(f"{slot['day']} {slot['meal_type']}: {ex}")
                return []
            rows: List[Dict] = []
            for slot in chunk:
                try:
                    rows.extend(
                        self.gemini.generate_full_recipes_for_plan_slots(
                            profile, [slot], servings=4
                        )
                    )
                except Exception as ex2:
                    if self._is_quota_error(ex2):
                        raise
                    errors.append(f"{slot['day']} {slot['meal_type']}: {ex2}")
            return rows

    def apply_diet_profile_to_empty_week(
        self,
        profile: Dict,
        week_start_date: date,
        user_id: int,
        max_meals: Optional[int] = None,
        meal_types: Optional[List[str]] = None,
        assign_thumbnail: bool = False,
    ) -> Dict:
        """
        Fill empty future (today+) meal slots using the diet profile.
        Uses batched Gemini calls (several full recipes per request) to stay under API quotas.
        """
        types = meal_types or list(_DEFAULT_APPLY_MEAL_TYPES)
        cap = max_meals if max_meals is not None else Config.DIET_APPLY_MAX_MEALS
        cap = max(1, min(28, int(cap)))

        plan_grid = self.get_weekly_plan(user_id, week_start_date)
        empty_slots, slot_stats = _collect_empty_diet_slots(
            plan_grid, week_start_date, types
        )
        eligible = slot_stats["eligible"]
        if not empty_slots:
            return {
                "added": 0,
                "message": "no_empty_slots",
                "errors": [],
                "eligible": 0,
                "attempted": 0,
                "remaining_empty": 0,
                "skipped_past": slot_stats["skipped_past"],
                "skipped_occupied": slot_stats["skipped_occupied"],
            }

        to_fill = empty_slots[:cap]
        added = 0
        errors: List[str] = []
        batch = self._AI_PLAN_RECIPE_BATCH_SIZE
        quota_stopped = False

        for i in range(0, len(to_fill), batch):
            chunk = to_fill[i : i + batch]
            try:
                rows = self._generate_recipes_for_chunk(profile, chunk, errors)
            except Exception as ex:
                if self._is_quota_error(ex):
                    errors.append(self._quota_error_message())
                    quota_stopped = True
                    break
                label = f"{chunk[0]['day']} {chunk[0]['meal_type']}"
                if len(chunk) > 1:
                    label += f" … {chunk[-1]['day']} {chunk[-1]['meal_type']}"
                errors.append(f"{label}: {ex}")
                continue

            for row in rows:
                recipe_data = row["recipe"]
                ok, err = validate_meal_name(recipe_data.get("name", ""))
                if not ok:
                    errors.append(
                        err or f"Invalid meal name for {row['day']} {row['meal_type']}"
                    )
                    continue
                try:
                    self._add_generated_recipe_to_plan(
                        recipe_data,
                        row["day"],
                        row["meal_type"],
                        user_id,
                        4,
                        week_start_date,
                        assign_thumbnail=assign_thumbnail,
                    )
                    added += 1
                except Exception as ex:
                    self.db.rollback()
                    errors.append(f"{row['day']} {row['meal_type']}: {ex}")

        plan_grid_after = self.get_weekly_plan(user_id, week_start_date)
        remaining_empty, _ = _collect_empty_diet_slots(
            plan_grid_after, week_start_date, types
        )

        message = "ok"
        if quota_stopped:
            message = "quota_stopped"
        elif not added and errors:
            message = "suggest_failed"

        return {
            "added": added,
            "message": message,
            "errors": errors,
            "eligible": eligible,
            "attempted": len(to_fill),
            "remaining_empty": len(remaining_empty),
            "skipped_past": slot_stats["skipped_past"],
            "skipped_occupied": slot_stats["skipped_occupied"],
        }

    def copy_week_plan(
        self,
        user_id: int,
        source_week: date,
        target_week: date,
    ) -> Dict[str, int]:
        """Copy meals from source week into empty slots on target week (same user)."""
        source_meals = get_weekly_meals(self.db, user_id, source_week)
        target_plan = self.get_weekly_plan(user_id, target_week)
        days = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        day_index = {d: i for i, d in enumerate(days)}
        copied = 0
        skipped = 0

        for meal in source_meals:
            if target_plan.get(meal.day, {}).get(meal.meal_type):
                skipped += 1
                continue
            slot_date = target_week + timedelta(days=day_index.get(meal.day, 0))
            if slot_date < date.today():
                skipped += 1
                continue
            create_meal(
                self.db,
                day=meal.day,
                meal_type=meal.meal_type,
                recipe_id=meal.recipe_id,
                user_id=user_id,
                servings=meal.servings,
                week_start_date=target_week,
            )
            target_plan[meal.day][meal.meal_type] = meal
            copied += 1

        return {"copied": copied, "skipped": skipped}

    def regenerate_shared_recipe(
        self, recipe_id: int, tweak: str = ""
    ) -> Tuple[Optional[object], Optional[str]]:
        """AI-regenerate content for a shared recipe. Returns (recipe, error_message)."""
        recipe = get_recipe_by_id(self.db, recipe_id)
        if not recipe:
            return None, "Recipe not found"
        try:
            recipe_data = self.gemini.regenerate_recipe(
                recipe.name,
                meal_type="dinner",
                servings=recipe.servings or 4,
                tweak=tweak or "",
            )
            updated = replace_recipe_from_ai_data(self.db, recipe_id, recipe_data)
            if updated:
                assign_recipe_thumbnail(self.db, updated)
            return updated, None
        except Exception as exc:
            return None, str(exc)

    def regenerate_private_recipe(
        self, recipe_id: int, user_id: int, tweak: str = ""
    ) -> Tuple[Optional[object], Optional[str]]:
        """AI-regenerate a recipe into a private copy for this user."""
        source = get_accessible_recipe_by_id(self.db, recipe_id, user_id)
        if not source:
            return None, "Recipe not found"
        try:
            recipe_data = self.gemini.regenerate_recipe(
                source.name,
                meal_type="dinner",
                servings=source.servings or 4,
                tweak=tweak or "",
            )
            private_recipe = create_recipe_from_ai_data(
                self.db,
                recipe_data,
                user_id=user_id,
                fallback_name=source.name,
                fallback_servings=source.servings or 4,
            )
            if source.image_url and not private_recipe.image_url:
                private_recipe.image_url = source.image_url
                self.db.commit()
                self.db.refresh(private_recipe)
            else:
                assign_recipe_thumbnail(self.db, private_recipe)
            return private_recipe, None
        except Exception as exc:
            return None, str(exc)
