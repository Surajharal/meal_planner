import re

from sqlalchemy.orm import Session
from models import (
    Meal,
    Recipe,
    Ingredient,
    RecipeIngredient,
    Inventory,
    UserRecipeFavorite,
    SessionLocal,
    init_db,
)
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional

def get_week_start_date(target_date: date = None) -> date:
    """Get the Monday of the week for the given date"""
    if target_date is None:
        target_date = date.today()
    days_since_monday = target_date.weekday()
    return target_date - timedelta(days=days_since_monday)

def get_or_create_ingredient(db: Session, name: str, category: str, default_unit: str = 'unit') -> Ingredient:
    """Get existing ingredient or create new one"""
    ingredient = db.query(Ingredient).filter(Ingredient.name == name).first()
    if not ingredient:
        ingredient = Ingredient(name=name, category=category, default_unit=default_unit)
        db.add(ingredient)
        db.commit()
        db.refresh(ingredient)
    return ingredient

def create_recipe(
    db: Session,
    name: str,
    description: str,
    instructions: str,
    prep_time: int,
    cook_time: int,
    servings: int = 4,
    calories_kcal: Optional[float] = None,
    protein_g: Optional[float] = None,
    carbs_g: Optional[float] = None,
    fat_g: Optional[float] = None,
    image_url: Optional[str] = None,
) -> Recipe:
    """Create a new recipe"""
    recipe = Recipe(
        name=name,
        description=description,
        instructions=instructions,
        prep_time=prep_time,
        cook_time=cook_time,
        servings=servings,
        calories_kcal=calories_kcal,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        image_url=image_url,
    )
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return recipe

def add_ingredient_to_recipe(db: Session, recipe_id: int, ingredient_name: str,
                             quantity: float, unit: str, category: str) -> RecipeIngredient:
    """Add an ingredient to a recipe"""
    ingredient = get_or_create_ingredient(db, ingredient_name, category, unit)
    
    recipe_ingredient = RecipeIngredient(
        recipe_id=recipe_id,
        ingredient_id=ingredient.id,
        quantity=quantity,
        unit=unit
    )
    db.add(recipe_ingredient)
    db.commit()
    db.refresh(recipe_ingredient)
    return recipe_ingredient

def create_meal(
    db: Session,
    day: str,
    meal_type: str,
    recipe_id: int,
    user_id: int,
    servings: int = 4,
    week_start_date: date = None,
) -> Meal:
    """Create a meal entry for one user's weekly plan."""
    if week_start_date is None:
        week_start_date = get_week_start_date()
    
    meal = Meal(
        user_id=user_id,
        day=day,
        meal_type=meal_type,
        recipe_id=recipe_id,
        servings=servings,
        week_start_date=week_start_date
    )
    db.add(meal)
    db.commit()
    db.refresh(meal)
    return meal

def get_weekly_meals(
    db: Session, user_id: int, week_start_date: date = None
) -> List[Meal]:
    """Get all meals for a user's week."""
    if week_start_date is None:
        week_start_date = get_week_start_date()
    
    return (
        db.query(Meal)
        .filter(
            Meal.week_start_date == week_start_date,
            Meal.user_id == user_id,
        )
        .all()
    )


def get_meal_by_id_for_user(
    db: Session, meal_id: int, user_id: int
) -> Optional[Meal]:
    return (
        db.query(Meal)
        .filter(Meal.id == meal_id, Meal.user_id == user_id)
        .first()
    )

def get_recipe_by_id(db: Session, recipe_id: int) -> Optional[Recipe]:
    """Get recipe by ID"""
    return db.query(Recipe).filter(Recipe.id == recipe_id).first()


def replace_recipe_from_ai_data(db: Session, recipe_id: int, recipe_data: dict) -> Optional[Recipe]:
    """Replace shared recipe content and ingredients from AI JSON."""
    from nutrition import nutrition_fields_from_ai_recipe

    recipe = get_recipe_by_id(db, recipe_id)
    if not recipe:
        return None

    instructions = recipe_data.get("instructions", "")
    if isinstance(instructions, list):
        instructions = "\n".join(str(step) for step in instructions)

    cal, prot, carb, fat = nutrition_fields_from_ai_recipe(recipe_data)
    recipe.name = recipe_data.get("name", recipe.name)
    recipe.description = recipe_data.get("description", "") or ""
    recipe.instructions = instructions
    recipe.prep_time = int(recipe_data.get("prep_time", 0) or 0)
    recipe.cook_time = int(recipe_data.get("cook_time", 0) or 0)
    recipe.servings = int(recipe_data.get("servings", recipe.servings) or recipe.servings)
    recipe.calories_kcal = cal
    recipe.protein_g = prot
    recipe.carbs_g = carb
    recipe.fat_g = fat

    db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe_id).delete()
    for ing in recipe_data.get("ingredients", []):
        add_ingredient_to_recipe(
            db,
            recipe_id=recipe.id,
            ingredient_name=ing["name"],
            quantity=ing["quantity"],
            unit=ing.get("unit", "unit"),
            category=ing.get("category", "other"),
        )

    db.commit()
    db.refresh(recipe)
    return recipe


def update_recipe_image_url(
    db: Session, recipe_id: int, image_url: Optional[str]
) -> Optional[Recipe]:
    """Set or clear recipes.image_url (None clears)."""
    recipe = get_recipe_by_id(db, recipe_id)
    if not recipe:
        return None
    recipe.image_url = image_url
    db.commit()
    db.refresh(recipe)
    return recipe

def get_all_recipes(db: Session) -> List[Recipe]:
    """Get all recipes"""
    return db.query(Recipe).all()

def search_recipes(db: Session, search_term: str) -> List[Recipe]:
    """Search recipes by name or description"""
    if not search_term or len(search_term.strip()) < 2:
        return []
    
    search_term = f"%{search_term.strip().lower()}%"
    return db.query(Recipe).filter(
        (Recipe.name.ilike(search_term)) | (Recipe.description.ilike(search_term))
    ).all()

def filter_recipes_by_category(db: Session, category: str = None) -> List[Recipe]:
    """Filter recipes by ingredient category"""
    if not category:
        return get_all_recipes(db)
    
    # Get recipes that have ingredients in the specified category
    from models import RecipeIngredient, Ingredient
    recipes = db.query(Recipe).join(RecipeIngredient).join(Ingredient).filter(
        Ingredient.category.ilike(f"%{category}%")
    ).distinct().all()
    return recipes

def get_favorite_recipe_ids_for_user(db: Session, user_id: int) -> set:
    """Recipe IDs starred by this user (recipes themselves are shared app-wide)."""
    rows = (
        db.query(UserRecipeFavorite.recipe_id)
        .filter(UserRecipeFavorite.user_id == user_id)
        .all()
    )
    return {r[0] for r in rows}


def get_favorite_recipes(db: Session, user_id: int) -> List[Recipe]:
    """Recipes starred by this user."""
    return (
        db.query(Recipe)
        .join(UserRecipeFavorite, UserRecipeFavorite.recipe_id == Recipe.id)
        .filter(UserRecipeFavorite.user_id == user_id)
        .order_by(Recipe.name)
        .all()
    )


def is_recipe_favorite_for_user(db: Session, recipe_id: int, user_id: int) -> bool:
    return (
        db.query(UserRecipeFavorite)
        .filter(
            UserRecipeFavorite.user_id == user_id,
            UserRecipeFavorite.recipe_id == recipe_id,
        )
        .first()
        is not None
    )


def toggle_recipe_favorite(db: Session, recipe_id: int, user_id: int):
    """Toggle this user's star on a shared recipe. Returns (recipe, is_favorite_now)."""
    recipe = get_recipe_by_id(db, recipe_id)
    if not recipe:
        raise ValueError(f"Recipe with ID {recipe_id} not found")

    row = (
        db.query(UserRecipeFavorite)
        .filter(
            UserRecipeFavorite.user_id == user_id,
            UserRecipeFavorite.recipe_id == recipe_id,
        )
        .first()
    )
    if row:
        db.delete(row)
        now = False
    else:
        db.add(UserRecipeFavorite(user_id=user_id, recipe_id=recipe_id))
        now = True
    db.commit()
    db.refresh(recipe)
    return recipe, now

def delete_meal(db: Session, meal_id: int, user_id: int) -> bool:
    """Delete a meal if it belongs to the user."""
    meal = (
        db.query(Meal)
        .filter(Meal.id == meal_id, Meal.user_id == user_id)
        .first()
    )
    if meal:
        db.delete(meal)
        db.commit()
        return True
    return False

def update_inventory(db: Session, ingredient_id: int, quantity: float, unit: str,
                    available: bool, week_start_date: date = None) -> Inventory:
    """Update or create inventory entry"""
    if week_start_date is None:
        week_start_date = get_week_start_date()
    
    inventory = db.query(Inventory).filter(
        Inventory.ingredient_id == ingredient_id,
        Inventory.week_start_date == week_start_date
    ).first()
    
    if inventory:
        inventory.quantity = quantity
        inventory.unit = unit
        inventory.available = available
    else:
        inventory = Inventory(
            ingredient_id=ingredient_id,
            quantity=quantity,
            unit=unit,
            available=available,
            week_start_date=week_start_date
        )
        db.add(inventory)
    
    db.commit()
    db.refresh(inventory)
    return inventory

def get_weekly_inventory(db: Session, week_start_date: date = None) -> List[Inventory]:
    """Get all inventory items for a week"""
    if week_start_date is None:
        week_start_date = get_week_start_date()
    
    return db.query(Inventory).filter(Inventory.week_start_date == week_start_date).all()

def get_ingredient_by_id(db: Session, ingredient_id: int) -> Optional[Ingredient]:
    """Get ingredient by ID"""
    return db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()

def get_all_ingredients(db: Session) -> List[Ingredient]:
    """Get all ingredients"""
    return db.query(Ingredient).all()


_NONVEG_NAME_RE = re.compile(
    r"\b(chicken|beef|pork|lamb|mutton|turkey|duck|bacon|ham|salmon|tuna|cod|haddock|trout|"
    r"fish|prawns?|shrimp|crab|lobster|anchov|sardine|mackerel|meat|steak|sausage|pepperoni|"
    r"prosciutto|ground beef|oxtail|venison|squid|octopus|clam|mussels?|oysters?)\b",
    re.I,
)
_EGG_NAME_RE = re.compile(r"\b(eggs?|egg whites?|egg yolks?)\b", re.I)

_NONVEG_CATEGORY_SUBSTR = (
    "meat",
    "poultry",
    "seafood",
    "fish",
    "chicken",
    "beef",
    "pork",
    "egg",
    "lamb",
    "mutton",
    "bacon",
    "ham",
    "turkey",
    "shellfish",
)


def recipe_is_non_vegetarian(recipe) -> bool:
    """True if any ingredient category/name suggests meat, fish, or eggs (heuristic)."""
    for ri in getattr(recipe, "ingredients", []) or []:
        ing = ri.ingredient
        cat = (ing.category or "").lower()
        for kw in _NONVEG_CATEGORY_SUBSTR:
            if kw in cat:
                return True
        name = ing.name or ""
        if _NONVEG_NAME_RE.search(name) or _EGG_NAME_RE.search(name):
            return True
    return False


_STARTER_CUISINE_PREFIX_RE = re.compile(r"^Starter · ([^·]+) · ", re.I)


def recipe_cuisine(recipe) -> Optional[str]:
    """Cuisine from starter catalog description, or None for user/AI-added recipes."""
    desc = (getattr(recipe, "description", None) or "").strip()
    m = _STARTER_CUISINE_PREFIX_RE.match(desc)
    return m.group(1).strip() if m else None


def recipe_matches_cuisine_filter(recipe, cuisine: str) -> bool:
    """
    cuisine: '' (all), a STARTER_CUISINES name, or 'other' for non-starter recipes.
    """
    if not cuisine:
        return True
    c = cuisine.strip().lower()
    rc = recipe_cuisine(recipe)
    if c == "other":
        return rc is None
    return (rc or "").lower() == c


def recipe_matches_diet_filter(recipe, diet: str) -> bool:
    """
    diet: '' (all), 'veg', 'non_veg'.
    Recipes with no ingredients are treated as vegetarian for the veg filter only.
    """
    if not diet:
        return True
    is_nv = recipe_is_non_vegetarian(recipe)
    has_ing = bool(getattr(recipe, "ingredients", None))
    if diet == "veg":
        return not is_nv
    if diet == "non_veg":
        return is_nv if has_ing else False
    return True
