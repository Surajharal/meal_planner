"""Recipe nutrition: parse AI output and scale totals to a meal's servings."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# Meal / Recipe ORM instances (duck-typed)


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if x != x or x < 0:  # NaN
        return None
    return round(x, 1)


def nutrition_fields_from_ai_recipe(recipe_data: dict) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Extract calories + macros from Gemini JSON (totals for the whole recipe / all servings)."""
    raw = recipe_data.get("nutrition")
    if not isinstance(raw, dict):
        return (None, None, None, None)

    def pick(*keys: str) -> Optional[float]:
        for k in keys:
            v = _safe_float(raw.get(k))
            if v is not None:
                return v
        return None

    return (
        pick("calories_kcal", "calories", "kcal"),
        pick("protein_g", "protein"),
        pick("carbs_g", "carbohydrates_g", "carbs"),
        pick("fat_g", "fat"),
    )


def scaled_nutrition_for_meal(meal) -> Optional[Dict[str, Optional[float]]]:
    """Scale stored recipe totals to this meal's `servings` (vs recipe's base servings)."""
    r = getattr(meal, "recipe", None)
    if r is None:
        return None
    if (
        getattr(r, "calories_kcal", None) is None
        and getattr(r, "protein_g", None) is None
        and getattr(r, "carbs_g", None) is None
        and getattr(r, "fat_g", None) is None
    ):
        return None

    rs = getattr(r, "servings", None) or 1
    if rs <= 0:
        rs = 1
    ms = getattr(meal, "servings", None) or 0
    factor = ms / rs

    def sc(val: Optional[float]) -> Optional[float]:
        if val is None:
            return None
        return round(val * factor, 1)

    return {
        "calories_kcal": sc(getattr(r, "calories_kcal", None)),
        "protein_g": sc(getattr(r, "protein_g", None)),
        "carbs_g": sc(getattr(r, "carbs_g", None)),
        "fat_g": sc(getattr(r, "fat_g", None)),
    }


def batch_nutrition_for_recipe(recipe) -> Optional[Dict[str, Optional[float]]]:
    """Totals stored on the recipe (for the recipe's default serving count)."""
    if recipe is None:
        return None
    if (
        getattr(recipe, "calories_kcal", None) is None
        and getattr(recipe, "protein_g", None) is None
        and getattr(recipe, "carbs_g", None) is None
        and getattr(recipe, "fat_g", None) is None
    ):
        return None
    return {
        "calories_kcal": getattr(recipe, "calories_kcal", None),
        "protein_g": getattr(recipe, "protein_g", None),
        "carbs_g": getattr(recipe, "carbs_g", None),
        "fat_g": getattr(recipe, "fat_g", None),
        "servings": getattr(recipe, "servings", None) or 1,
    }


def per_serving_nutrition_for_recipe(recipe) -> Optional[Dict[str, Any]]:
    """Divide stored batch totals by the recipe's serving count (one portion)."""
    b = batch_nutrition_for_recipe(recipe)
    if not b:
        return None
    rs = float(b.get("servings") or 1)
    if rs <= 0:
        rs = 1.0

    def div(val: Optional[float]) -> Optional[float]:
        if val is None:
            return None
        return round(float(val) / rs, 1)

    return {
        "calories_kcal": div(_safe_float(b.get("calories_kcal"))),
        "protein_g": div(_safe_float(b.get("protein_g"))),
        "carbs_g": div(_safe_float(b.get("carbs_g"))),
        "fat_g": div(_safe_float(b.get("fat_g"))),
        "recipe_servings": int(rs) if rs == int(rs) else rs,
    }


def per_serving_nutrition_for_meal(meal) -> Optional[Dict[str, Any]]:
    """Nutrition for one portion on the plan (scaled batch ÷ meal.servings)."""
    scaled = scaled_nutrition_for_meal(meal)
    if not scaled:
        return None
    ms = getattr(meal, "servings", None)
    try:
        msv = float(ms) if ms is not None else 0.0
    except (TypeError, ValueError):
        msv = 0.0
    if msv <= 0:
        return None

    def div(val: Optional[float]) -> Optional[float]:
        if val is None:
            return None
        return round(float(val) / msv, 1)

    return {
        "calories_kcal": div(scaled.get("calories_kcal")),
        "protein_g": div(scaled.get("protein_g")),
        "carbs_g": div(scaled.get("carbs_g")),
        "fat_g": div(scaled.get("fat_g")),
        "meal_servings": int(msv) if msv == int(msv) else msv,
    }
