"""Tests for AI diet plan → weekly calendar apply."""
from datetime import date, timedelta
from unittest.mock import patch

from database import get_week_start_date
from meal_planner import MealPlanner, _collect_empty_diet_slots
from models import Meal, Recipe, SessionLocal, User, init_db
from werkzeug.security import generate_password_hash


def _empty_plan_grid():
    days = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    types = ["Breakfast", "Lunch", "Dinner", "Snack"]
    return {d: {t: None for t in types} for d in days}


def test_collect_empty_diet_slots_skips_past_and_occupied():
    week = get_week_start_date(date.today())
    grid = _empty_plan_grid()
    grid["Friday"]["Dinner"] = object()
    slots, stats = _collect_empty_diet_slots(grid, week, ["Dinner", "Lunch"])
    assert stats["skipped_occupied"] >= 1
    for s in slots:
        assert not (s["day"] == "Friday" and s["meal_type"] == "Dinner")
    for s in slots:
        slot_date = week + timedelta(
            days=[
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ].index(s["day"])
        )
        assert slot_date >= date.today()


def test_apply_diet_profile_skips_thumbnails():
    init_db()
    db = SessionLocal()
    try:
        user = User(
            username="diettest@example.com",
            password_hash=generate_password_hash("secret"),
            email="diettest@example.com",
            role="gyama",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        week = get_week_start_date(date.today())
        planner = MealPlanner(db)
        profile = {
            "age": 30,
            "sex": "female",
            "weight_kg": 65,
            "height_cm": 165,
            "goal": "maintain",
            "activity_level": "moderate",
            "dietary_restrictions": "",
            "allergies": "",
            "extra_notes": "",
        }
        fake_recipe = {
            "name": "Test Bowl",
            "description": "Test",
            "instructions": "Cook.",
            "prep_time": 5,
            "cook_time": 10,
            "servings": 4,
            "ingredients": [
                {"name": "Rice", "quantity": 1, "unit": "cup", "category": "grains"}
            ],
        }
        slot = {"day": "Friday", "meal_type": "Dinner"}
        if week + timedelta(days=4) < date.today():
            slot = {"day": "Sunday", "meal_type": "Dinner"}

        with patch.object(
            planner.gemini,
            "generate_full_recipes_for_plan_slots",
            return_value=[{"day": slot["day"], "meal_type": slot["meal_type"], "recipe": fake_recipe}],
        ):
            with patch(
                "meal_planner.assign_recipe_thumbnail",
            ) as mock_thumb:
                result = planner.apply_diet_profile_to_empty_week(
                    profile,
                    week,
                    user.id,
                    max_meals=1,
                    meal_types=["Dinner"],
                    assign_thumbnail=False,
                )
        assert result["added"] == 1
        mock_thumb.assert_not_called()
    finally:
        db.query(Meal).delete()
        db.query(Recipe).delete()
        db.query(User).delete()
        db.commit()
        db.close()


def test_apply_diet_respects_max_meals_cap():
    init_db()
    db = SessionLocal()
    try:
        user = User(
            username="cap@example.com",
            password_hash=generate_password_hash("secret"),
            email="cap@example.com",
            role="gyama",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        week = get_week_start_date(date.today())
        planner = MealPlanner(db)
        stats = planner.count_empty_diet_slots(user.id, week, ["Dinner"])
        if stats["eligible"] < 2:
            return
        profile = {
            "age": 25,
            "sex": "male",
            "weight_kg": 70,
            "height_cm": 175,
            "goal": "maintain",
            "activity_level": "light",
        }

        def fake_gen(prof, slots, servings=4):
            out = []
            for s in slots:
                out.append(
                    {
                        "day": s["day"],
                        "meal_type": s["meal_type"],
                        "recipe": {
                            "name": f"Meal {s['day']}",
                            "instructions": "Step 1",
                            "ingredients": [
                                {
                                    "name": "Egg",
                                    "quantity": 1,
                                    "unit": "unit",
                                    "category": "other",
                                }
                            ],
                        },
                    }
                )
            return out

        with patch.object(
            planner.gemini, "generate_full_recipes_for_plan_slots", side_effect=fake_gen
        ):
            result = planner.apply_diet_profile_to_empty_week(
                profile,
                week,
                user.id,
                max_meals=2,
                meal_types=["Dinner"],
                assign_thumbnail=False,
            )
        assert result["added"] <= 2
        assert result["attempted"] <= 2
    finally:
        db.query(Meal).delete()
        db.query(Recipe).delete()
        db.query(User).delete()
        db.commit()
        db.close()
