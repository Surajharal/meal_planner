"""
Starter recipe catalog for empty databases.

Structure per cuisine:
  - 5 vegetarian recipes
  - 5 non-vegetarian recipes

Cuisines (8): Indian, Italian, Mexican, Japanese, Chinese, Thai, Mediterranean, American.
Each cuisine: 5 vegetarian + 5 non-vegetarian = 80 starter recipes total.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from database import add_ingredient_to_recipe, create_recipe
from models import Recipe, RecipeIngredient
from recipe_thumbnail_service import assign_recipe_thumbnail
from sqlalchemy.orm import joinedload
from starter_recipes_more import MORE_STARTER_RECIPES

logger = logging.getLogger(__name__)

STARTER_CUISINES: Tuple[str, ...] = (
    "Indian",
    "Italian",
    "Mexican",
    "Japanese",
    "Chinese",
    "Thai",
    "Mediterranean",
    "American",
)

RECIPES_PER_CUISINE_PER_DIET = 5

# Each entry: cuisine, diet_label (for description), and recipe fields.
_BASE_STARTER_RECIPES: List[Dict[str, Any]] = [
    # —— Indian · Vegetarian (5) ——
    {
        "cuisine": "Indian",
        "diet": "Vegetarian",
        "name": "Dal Tadka",
        "description": "Comforting spiced yellow lentils with garlic tempering.",
        "instructions": "1. Rinse dal and pressure-cook with turmeric and water until soft.\n2. Mash lightly and simmer with salt.\n3. Heat ghee, add cumin, garlic, and dried red chili; pour over dal.\n4. Garnish with cilantro and serve with rice or roti.",
        "prep_time": 10,
        "cook_time": 25,
        "servings": 4,
        "calories_kcal": 720,
        "protein_g": 36,
        "carbs_g": 96,
        "fat_g": 18,
        "ingredients": [
            {"name": "yellow lentils", "quantity": 200, "unit": "g", "category": "grains"},
            {"name": "onion", "quantity": 1, "unit": "piece", "category": "vegetables"},
            {"name": "tomato", "quantity": 2, "unit": "piece", "category": "vegetables"},
            {"name": "garlic", "quantity": 4, "unit": "clove", "category": "vegetables"},
            {"name": "ghee", "quantity": 2, "unit": "tbsp", "category": "dairy"},
            {"name": "cumin seeds", "quantity": 1, "unit": "tsp", "category": "spices"},
            {"name": "turmeric", "quantity": 0.5, "unit": "tsp", "category": "spices"},
        ],
    },
    {
        "cuisine": "Indian",
        "diet": "Vegetarian",
        "name": "Vegetable Pulao",
        "description": "Fragrant basmati rice with mixed vegetables and whole spices.",
        "instructions": "1. Rinse rice and soak 20 minutes.\n2. Sauté whole spices, onion, and ginger-garlic paste in oil.\n3. Add vegetables; stir 3 minutes.\n4. Add rice, water, and salt; cover and cook until rice is fluffy.\n5. Rest 5 minutes, fluff, and serve.",
        "prep_time": 15,
        "cook_time": 30,
        "servings": 4,
        "calories_kcal": 880,
        "protein_g": 20,
        "carbs_g": 168,
        "fat_g": 14,
        "ingredients": [
            {"name": "basmati rice", "quantity": 300, "unit": "g", "category": "grains"},
            {"name": "carrot", "quantity": 2, "unit": "piece", "category": "vegetables"},
            {"name": "green peas", "quantity": 100, "unit": "g", "category": "vegetables"},
            {"name": "cauliflower", "quantity": 150, "unit": "g", "category": "vegetables"},
            {"name": "onion", "quantity": 1, "unit": "piece", "category": "vegetables"},
            {"name": "vegetable oil", "quantity": 2, "unit": "tbsp", "category": "other"},
            {"name": "bay leaf", "quantity": 2, "unit": "piece", "category": "spices"},
        ],
    },
    {
        "cuisine": "Indian",
        "diet": "Vegetarian",
        "name": "Palak Paneer",
        "description": "Creamy spinach curry with soft paneer cubes.",
        "instructions": "1. Blanch spinach; blend to a smooth purée.\n2. Pan-fry paneer cubes until golden; set aside.\n3. Cook onion, ginger, and garlic; add spices and tomato.\n4. Stir in spinach purée and simmer.\n5. Add paneer and cream; cook 5 minutes and serve.",
        "prep_time": 15,
        "cook_time": 25,
        "servings": 4,
        "calories_kcal": 1040,
        "protein_g": 48,
        "carbs_g": 32,
        "fat_g": 72,
        "ingredients": [
            {"name": "spinach", "quantity": 500, "unit": "g", "category": "vegetables"},
            {"name": "paneer", "quantity": 300, "unit": "g", "category": "dairy"},
            {"name": "onion", "quantity": 1, "unit": "piece", "category": "vegetables"},
            {"name": "tomato", "quantity": 2, "unit": "piece", "category": "vegetables"},
            {"name": "heavy cream", "quantity": 100, "unit": "ml", "category": "dairy"},
            {"name": "garam masala", "quantity": 1, "unit": "tsp", "category": "spices"},
        ],
    },
    {
        "cuisine": "Indian",
        "diet": "Vegetarian",
        "name": "Chana Masala",
        "description": "Punjabi-style chickpeas in a tangy tomato-onion gravy.",
        "instructions": "1. Sauté onions until golden; add ginger-garlic and spices.\n2. Add tomato and cook until oil separates.\n3. Add cooked chickpeas and some water; simmer 15 minutes.\n4. Finish with amchur and cilantro.",
        "prep_time": 10,
        "cook_time": 30,
        "servings": 4,
        "calories_kcal": 920,
        "protein_g": 40,
        "carbs_g": 128,
        "fat_g": 24,
        "ingredients": [
            {"name": "chickpeas", "quantity": 400, "unit": "g", "category": "grains"},
            {"name": "onion", "quantity": 2, "unit": "piece", "category": "vegetables"},
            {"name": "tomato", "quantity": 3, "unit": "piece", "category": "vegetables"},
            {"name": "ginger", "quantity": 1, "unit": "tbsp", "category": "vegetables"},
            {"name": "coriander powder", "quantity": 2, "unit": "tsp", "category": "spices"},
            {"name": "cumin powder", "quantity": 1, "unit": "tsp", "category": "spices"},
        ],
    },
    {
        "cuisine": "Indian",
        "diet": "Vegetarian",
        "name": "Aloo Gobi",
        "description": "Dry-style potatoes and cauliflower with cumin and turmeric.",
        "instructions": "1. Heat oil; add cumin seeds.\n2. Add potato and cauliflower; toss with turmeric and salt.\n3. Cover and cook on low until tender, stirring occasionally.\n4. Uncover, raise heat slightly to brown edges; add garam masala and serve.",
        "prep_time": 15,
        "cook_time": 25,
        "servings": 4,
        "calories_kcal": 640,
        "protein_g": 16,
        "carbs_g": 88,
        "fat_g": 24,
        "ingredients": [
            {"name": "potato", "quantity": 400, "unit": "g", "category": "vegetables"},
            {"name": "cauliflower", "quantity": 400, "unit": "g", "category": "vegetables"},
            {"name": "onion", "quantity": 1, "unit": "piece", "category": "vegetables"},
            {"name": "vegetable oil", "quantity": 3, "unit": "tbsp", "category": "other"},
            {"name": "turmeric", "quantity": 1, "unit": "tsp", "category": "spices"},
            {"name": "cumin seeds", "quantity": 1, "unit": "tsp", "category": "spices"},
        ],
    },
    # —— Indian · Non-vegetarian (5) ——
    {
        "cuisine": "Indian",
        "diet": "Non-vegetarian",
        "name": "Chicken Curry",
        "description": "Home-style north Indian chicken in onion-tomato gravy.",
        "instructions": "1. Marinate chicken with yogurt, salt, and turmeric 20 minutes.\n2. Brown chicken in oil; remove.\n3. Cook onions, ginger-garlic, and spices; add tomato.\n4. Return chicken; add water and simmer until cooked.\n5. Garnish with cilantro.",
        "prep_time": 20,
        "cook_time": 35,
        "servings": 4,
        "calories_kcal": 1400,
        "protein_g": 120,
        "carbs_g": 24,
        "fat_g": 88,
        "ingredients": [
            {"name": "chicken thigh", "quantity": 800, "unit": "g", "category": "poultry"},
            {"name": "onion", "quantity": 2, "unit": "piece", "category": "vegetables"},
            {"name": "tomato", "quantity": 2, "unit": "piece", "category": "vegetables"},
            {"name": "yogurt", "quantity": 100, "unit": "g", "category": "dairy"},
            {"name": "ginger garlic paste", "quantity": 2, "unit": "tbsp", "category": "vegetables"},
            {"name": "garam masala", "quantity": 1, "unit": "tsp", "category": "spices"},
        ],
    },
    {
        "cuisine": "Indian",
        "diet": "Non-vegetarian",
        "name": "Chicken Biryani",
        "description": "Layered spiced rice and marinated chicken dum cooked.",
        "instructions": "1. Marinate chicken with yogurt and biryani spices.\n2. Par-cook basmati rice with whole spices.\n3. Layer rice and chicken in a heavy pot; top with fried onions and saffron milk.\n4. Seal and cook on low 25–30 minutes.\n5. Rest, then mix gently and serve.",
        "prep_time": 30,
        "cook_time": 45,
        "servings": 4,
        "calories_kcal": 2200,
        "protein_g": 140,
        "carbs_g": 240,
        "fat_g": 72,
        "ingredients": [
            {"name": "chicken", "quantity": 700, "unit": "g", "category": "poultry"},
            {"name": "basmati rice", "quantity": 400, "unit": "g", "category": "grains"},
            {"name": "onion", "quantity": 3, "unit": "piece", "category": "vegetables"},
            {"name": "yogurt", "quantity": 150, "unit": "g", "category": "dairy"},
            {"name": "biryani masala", "quantity": 2, "unit": "tbsp", "category": "spices"},
            {"name": "ghee", "quantity": 3, "unit": "tbsp", "category": "dairy"},
        ],
    },
    {
        "cuisine": "Indian",
        "diet": "Non-vegetarian",
        "name": "Fish Curry",
        "description": "Coastal-style fish fillets in coconut-tamarind curry.",
        "instructions": "1. Marinate fish with turmeric and salt.\n2. Sauté onion, curry leaves, and spice paste.\n3. Add coconut milk and tamarind; simmer.\n4. Gently add fish; cook until just opaque.\n5. Serve with rice.",
        "prep_time": 15,
        "cook_time": 20,
        "servings": 4,
        "calories_kcal": 1200,
        "protein_g": 96,
        "carbs_g": 16,
        "fat_g": 80,
        "ingredients": [
            {"name": "white fish fillet", "quantity": 600, "unit": "g", "category": "fish"},
            {"name": "coconut milk", "quantity": 400, "unit": "ml", "category": "other"},
            {"name": "onion", "quantity": 1, "unit": "piece", "category": "vegetables"},
            {"name": "tamarind paste", "quantity": 1, "unit": "tbsp", "category": "spices"},
            {"name": "curry leaves", "quantity": 10, "unit": "piece", "category": "spices"},
            {"name": "red chili powder", "quantity": 1, "unit": "tsp", "category": "spices"},
        ],
    },
    {
        "cuisine": "Indian",
        "diet": "Non-vegetarian",
        "name": "Egg Bhurji",
        "description": "Scrambled eggs with onion, tomato, and green chili.",
        "instructions": "1. Sauté onion, chili, and tomato until soft.\n2. Add turmeric and salt.\n3. Pour beaten eggs; scramble on medium heat.\n4. Finish with cilantro; serve with bread or roti.",
        "prep_time": 5,
        "cook_time": 10,
        "servings": 4,
        "calories_kcal": 560,
        "protein_g": 32,
        "carbs_g": 12,
        "fat_g": 44,
        "ingredients": [
            {"name": "eggs", "quantity": 8, "unit": "piece", "category": "egg"},
            {"name": "onion", "quantity": 1, "unit": "piece", "category": "vegetables"},
            {"name": "tomato", "quantity": 2, "unit": "piece", "category": "vegetables"},
            {"name": "green chili", "quantity": 2, "unit": "piece", "category": "vegetables"},
            {"name": "vegetable oil", "quantity": 2, "unit": "tbsp", "category": "other"},
            {"name": "turmeric", "quantity": 0.5, "unit": "tsp", "category": "spices"},
        ],
    },
    {
        "cuisine": "Indian",
        "diet": "Non-vegetarian",
        "name": "Lamb Keema",
        "description": "Spiced minced lamb with peas, great with pav or rice.",
        "instructions": "1. Brown lamb mince in oil; drain excess fat if needed.\n2. Add onion, ginger-garlic, and spices; cook 5 minutes.\n3. Add tomato and peas; simmer until lamb is cooked.\n4. Adjust salt; serve with lemon and onions.",
        "prep_time": 10,
        "cook_time": 25,
        "servings": 4,
        "calories_kcal": 1600,
        "protein_g": 100,
        "carbs_g": 32,
        "fat_g": 112,
        "ingredients": [
            {"name": "ground lamb", "quantity": 600, "unit": "g", "category": "meat"},
            {"name": "green peas", "quantity": 150, "unit": "g", "category": "vegetables"},
            {"name": "onion", "quantity": 2, "unit": "piece", "category": "vegetables"},
            {"name": "tomato", "quantity": 2, "unit": "piece", "category": "vegetables"},
            {"name": "ginger garlic paste", "quantity": 1, "unit": "tbsp", "category": "vegetables"},
            {"name": "garam masala", "quantity": 1, "unit": "tsp", "category": "spices"},
        ],
    },
    # —— Italian · Vegetarian (5) ——
    {
        "cuisine": "Italian",
        "diet": "Vegetarian",
        "name": "Margherita Pizza",
        "description": "Classic tomato, mozzarella, and basil on a thin crust.",
        "instructions": "1. Stretch pizza dough on a floured surface.\n2. Spread tomato sauce; top with mozzarella.\n3. Bake at 250°C (480°F) until crust is crisp and cheese bubbles.\n4. Add fresh basil and olive oil before serving.",
        "prep_time": 20,
        "cook_time": 12,
        "servings": 4,
        "calories_kcal": 2000,
        "protein_g": 72,
        "carbs_g": 224,
        "fat_g": 80,
        "ingredients": [
            {"name": "pizza dough", "quantity": 500, "unit": "g", "category": "grains"},
            {"name": "tomato sauce", "quantity": 200, "unit": "ml", "category": "vegetables"},
            {"name": "mozzarella", "quantity": 300, "unit": "g", "category": "dairy"},
            {"name": "fresh basil", "quantity": 20, "unit": "g", "category": "vegetables"},
            {"name": "olive oil", "quantity": 2, "unit": "tbsp", "category": "other"},
        ],
    },
    {
        "cuisine": "Italian",
        "diet": "Vegetarian",
        "name": "Pasta al Pomodoro",
        "description": "Simple spaghetti with garlic, olive oil, and tomato.",
        "instructions": "1. Cook spaghetti until al dente; reserve pasta water.\n2. Sauté garlic in olive oil until fragrant.\n3. Add crushed tomatoes; simmer 10 minutes.\n4. Toss pasta with sauce, basil, and pasta water as needed.",
        "prep_time": 10,
        "cook_time": 20,
        "servings": 4,
        "calories_kcal": 1200,
        "protein_g": 32,
        "carbs_g": 192,
        "fat_g": 32,
        "ingredients": [
            {"name": "spaghetti", "quantity": 400, "unit": "g", "category": "grains"},
            {"name": "crushed tomatoes", "quantity": 400, "unit": "g", "category": "vegetables"},
            {"name": "garlic", "quantity": 4, "unit": "clove", "category": "vegetables"},
            {"name": "olive oil", "quantity": 4, "unit": "tbsp", "category": "other"},
            {"name": "fresh basil", "quantity": 15, "unit": "g", "category": "vegetables"},
        ],
    },
    {
        "cuisine": "Italian",
        "diet": "Vegetarian",
        "name": "Mushroom Risotto",
        "description": "Creamy arborio rice with sautéed mushrooms and parmesan.",
        "instructions": "1. Sauté mushrooms in butter; set aside.\n2. Toast rice in butter; deglaze with wine.\n3. Add warm stock ladle by ladle, stirring until creamy.\n4. Fold in mushrooms, parmesan, and butter; rest 2 minutes.",
        "prep_time": 15,
        "cook_time": 30,
        "servings": 4,
        "calories_kcal": 1400,
        "protein_g": 36,
        "carbs_g": 200,
        "fat_g": 48,
        "ingredients": [
            {"name": "arborio rice", "quantity": 320, "unit": "g", "category": "grains"},
            {"name": "mushrooms", "quantity": 300, "unit": "g", "category": "vegetables"},
            {"name": "vegetable stock", "quantity": 1, "unit": "L", "category": "other"},
            {"name": "parmesan", "quantity": 80, "unit": "g", "category": "dairy"},
            {"name": "butter", "quantity": 40, "unit": "g", "category": "dairy"},
        ],
    },
    {
        "cuisine": "Italian",
        "diet": "Vegetarian",
        "name": "Caprese Salad",
        "description": "Fresh mozzarella, tomatoes, and basil with balsamic.",
        "instructions": "1. Slice tomatoes and mozzarella.\n2. Arrange on a platter with basil leaves.\n3. Drizzle olive oil and balsamic glaze.\n4. Season with salt and pepper; serve chilled.",
        "prep_time": 15,
        "cook_time": 0,
        "servings": 4,
        "calories_kcal": 800,
        "protein_g": 40,
        "carbs_g": 16,
        "fat_g": 64,
        "ingredients": [
            {"name": "mozzarella", "quantity": 300, "unit": "g", "category": "dairy"},
            {"name": "tomato", "quantity": 4, "unit": "piece", "category": "vegetables"},
            {"name": "fresh basil", "quantity": 20, "unit": "g", "category": "vegetables"},
            {"name": "olive oil", "quantity": 3, "unit": "tbsp", "category": "other"},
            {"name": "balsamic vinegar", "quantity": 2, "unit": "tbsp", "category": "other"},
        ],
    },
    {
        "cuisine": "Italian",
        "diet": "Vegetarian",
        "name": "Eggplant Parmigiana",
        "description": "Baked layers of eggplant, tomato sauce, and cheese.",
        "instructions": "1. Salt eggplant slices; rest 20 minutes, pat dry.\n2. Pan-fry eggplant until golden.\n3. Layer eggplant, tomato sauce, and cheeses in a baking dish.\n4. Bake at 190°C (375°F) until bubbling; rest before slicing.",
        "prep_time": 25,
        "cook_time": 35,
        "servings": 4,
        "calories_kcal": 1100,
        "protein_g": 44,
        "carbs_g": 72,
        "fat_g": 72,
        "ingredients": [
            {"name": "eggplant", "quantity": 2, "unit": "piece", "category": "vegetables"},
            {"name": "tomato sauce", "quantity": 400, "unit": "ml", "category": "vegetables"},
            {"name": "mozzarella", "quantity": 200, "unit": "g", "category": "dairy"},
            {"name": "parmesan", "quantity": 60, "unit": "g", "category": "dairy"},
            {"name": "olive oil", "quantity": 4, "unit": "tbsp", "category": "other"},
        ],
    },
    # —— Italian · Non-vegetarian (5) ——
    {
        "cuisine": "Italian",
        "diet": "Non-vegetarian",
        "name": "Spaghetti Carbonara",
        "description": "Roman pasta with eggs, pecorino, and pancetta.",
        "instructions": "1. Cook spaghetti; reserve pasta water.\n2. Crisp pancetta in a pan.\n3. Whisk eggs and cheese off heat.\n4. Toss hot pasta with pancetta; remove from heat and mix in egg mixture quickly.\n5. Thin with pasta water; season with pepper.",
        "prep_time": 10,
        "cook_time": 15,
        "servings": 4,
        "calories_kcal": 1600,
        "protein_g": 64,
        "carbs_g": 176,
        "fat_g": 72,
        "ingredients": [
            {"name": "spaghetti", "quantity": 400, "unit": "g", "category": "grains"},
            {"name": "pancetta", "quantity": 200, "unit": "g", "category": "pork"},
            {"name": "eggs", "quantity": 4, "unit": "piece", "category": "egg"},
            {"name": "pecorino cheese", "quantity": 100, "unit": "g", "category": "dairy"},
            {"name": "black pepper", "quantity": 1, "unit": "tsp", "category": "spices"},
        ],
    },
    {
        "cuisine": "Italian",
        "diet": "Non-vegetarian",
        "name": "Chicken Parmigiana",
        "description": "Breaded chicken cutlets baked with marinara and mozzarella.",
        "instructions": "1. Pound chicken; bread with flour, egg, and breadcrumbs.\n2. Pan-fry until golden.\n3. Top with marinara and mozzarella.\n4. Bake until cheese melts; serve with pasta or salad.",
        "prep_time": 20,
        "cook_time": 25,
        "servings": 4,
        "calories_kcal": 1800,
        "protein_g": 140,
        "carbs_g": 64,
        "fat_g": 96,
        "ingredients": [
            {"name": "chicken breast", "quantity": 600, "unit": "g", "category": "poultry"},
            {"name": "breadcrumbs", "quantity": 150, "unit": "g", "category": "grains"},
            {"name": "marinara sauce", "quantity": 400, "unit": "ml", "category": "vegetables"},
            {"name": "mozzarella", "quantity": 200, "unit": "g", "category": "dairy"},
            {"name": "eggs", "quantity": 2, "unit": "piece", "category": "egg"},
        ],
    },
    {
        "cuisine": "Italian",
        "diet": "Non-vegetarian",
        "name": "Spaghetti Bolognese",
        "description": "Slow-simmered meat sauce over spaghetti.",
        "instructions": "1. Sauté onion, carrot, and celery in olive oil.\n2. Brown ground beef; add tomato paste and wine.\n3. Add crushed tomatoes; simmer 30–40 minutes.\n4. Cook spaghetti; serve topped with sauce and parmesan.",
        "prep_time": 15,
        "cook_time": 45,
        "servings": 4,
        "calories_kcal": 2000,
        "protein_g": 100,
        "carbs_g": 200,
        "fat_g": 88,
        "ingredients": [
            {"name": "ground beef", "quantity": 500, "unit": "g", "category": "meat"},
            {"name": "spaghetti", "quantity": 400, "unit": "g", "category": "grains"},
            {"name": "crushed tomatoes", "quantity": 400, "unit": "g", "category": "vegetables"},
            {"name": "onion", "quantity": 1, "unit": "piece", "category": "vegetables"},
            {"name": "carrot", "quantity": 1, "unit": "piece", "category": "vegetables"},
            {"name": "celery", "quantity": 2, "unit": "stalk", "category": "vegetables"},
        ],
    },
    {
        "cuisine": "Italian",
        "diet": "Non-vegetarian",
        "name": "Prosciutto Pizza",
        "description": "White-base pizza with mozzarella, arugula, and prosciutto.",
        "instructions": "1. Stretch dough; brush with olive oil (no tomato).\n2. Bake with mozzarella until crisp.\n3. Top with prosciutto and arugula after baking.\n4. Finish with shaved parmesan.",
        "prep_time": 20,
        "cook_time": 12,
        "servings": 4,
        "calories_kcal": 2100,
        "protein_g": 88,
        "carbs_g": 200,
        "fat_g": 104,
        "ingredients": [
            {"name": "pizza dough", "quantity": 500, "unit": "g", "category": "grains"},
            {"name": "mozzarella", "quantity": 250, "unit": "g", "category": "dairy"},
            {"name": "prosciutto", "quantity": 120, "unit": "g", "category": "pork"},
            {"name": "arugula", "quantity": 60, "unit": "g", "category": "vegetables"},
            {"name": "parmesan", "quantity": 40, "unit": "g", "category": "dairy"},
        ],
    },
    {
        "cuisine": "Italian",
        "diet": "Non-vegetarian",
        "name": "Seafood Linguine",
        "description": "Linguine with shrimp, garlic, white wine, and parsley.",
        "instructions": "1. Cook linguine until al dente.\n2. Sauté garlic and chili in olive oil.\n3. Add shrimp; cook until pink.\n4. Deglaze with wine; toss pasta with parsley and lemon.",
        "prep_time": 15,
        "cook_time": 15,
        "servings": 4,
        "calories_kcal": 1400,
        "protein_g": 88,
        "carbs_g": 176,
        "fat_g": 32,
        "ingredients": [
            {"name": "linguine", "quantity": 400, "unit": "g", "category": "grains"},
            {"name": "shrimp", "quantity": 500, "unit": "g", "category": "seafood"},
            {"name": "garlic", "quantity": 4, "unit": "clove", "category": "vegetables"},
            {"name": "white wine", "quantity": 120, "unit": "ml", "category": "other"},
            {"name": "fresh parsley", "quantity": 20, "unit": "g", "category": "vegetables"},
            {"name": "lemon", "quantity": 1, "unit": "piece", "category": "fruits"},
        ],
    },
]

STARTER_RECIPES: List[Dict[str, Any]] = _BASE_STARTER_RECIPES + MORE_STARTER_RECIPES


def _starter_description(spec: Dict[str, Any]) -> str:
    prefix = f"Starter · {spec['cuisine']} · {spec['diet']}. "
    return prefix + (spec.get("description") or "")


def ensure_starter_recipes(db: Session) -> int:
    """
    Insert starter recipes when the library is empty.
    Returns number of recipes created (0 if already seeded).
    """
    if db.query(Recipe).count() > 0:
        return 0

    created = 0
    for spec in STARTER_RECIPES:
        recipe = create_recipe(
            db,
            name=spec["name"],
            description=_starter_description(spec),
            instructions=spec["instructions"],
            prep_time=int(spec.get("prep_time", 0)),
            cook_time=int(spec.get("cook_time", 0)),
            servings=int(spec.get("servings", 4)),
            calories_kcal=spec.get("calories_kcal"),
            protein_g=spec.get("protein_g"),
            carbs_g=spec.get("carbs_g"),
            fat_g=spec.get("fat_g"),
        )
        for ing in spec.get("ingredients", []):
            add_ingredient_to_recipe(
                db,
                recipe_id=recipe.id,
                ingredient_name=ing["name"],
                quantity=float(ing["quantity"]),
                unit=ing.get("unit", "unit"),
                category=ing.get("category", "other"),
            )
        full = (
            db.query(Recipe)
            .options(
                joinedload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient)
            )
            .filter(Recipe.id == recipe.id)
            .one()
        )
        assign_recipe_thumbnail(db, full)
        created += 1

    logger.info(
        "Seeded %s starter recipes (%s cuisines × veg/non-veg)",
        created,
        len(STARTER_CUISINES),
    )
    return created


def starter_recipe_summary() -> Dict[str, int]:
    """Counts by cuisine and diet for display/logging."""
    summary: Dict[str, int] = {}
    for spec in STARTER_RECIPES:
        key = f"{spec['cuisine']} · {spec['diet']}"
        summary[key] = summary.get(key, 0) + 1
    return summary


def starter_cuisine_counts() -> Dict[str, int]:
    """Total recipes per cuisine."""
    counts: Dict[str, int] = {}
    for spec in STARTER_RECIPES:
        c = spec["cuisine"]
        counts[c] = counts.get(c, 0) + 1
    return counts
