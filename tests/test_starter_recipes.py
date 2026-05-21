from models import Meal, Recipe, RecipeIngredient, SessionLocal, init_db
from starter_recipes import (
    RECIPES_PER_CUISINE_PER_DIET,
    STARTER_CUISINES,
    STARTER_RECIPES,
    ensure_starter_recipes,
    starter_cuisine_counts,
    starter_recipe_summary,
)


def test_starter_catalog_shape():
    assert len(STARTER_CUISINES) == 8
    summary = starter_recipe_summary()
    for cuisine in STARTER_CUISINES:
        assert summary[f"{cuisine} · Vegetarian"] == RECIPES_PER_CUISINE_PER_DIET
        assert summary[f"{cuisine} · Non-vegetarian"] == RECIPES_PER_CUISINE_PER_DIET
    assert len(STARTER_RECIPES) == len(STARTER_CUISINES) * RECIPES_PER_CUISINE_PER_DIET * 2
    assert len(STARTER_RECIPES) == 80
    counts = starter_cuisine_counts()
    assert all(counts[c] == 10 for c in STARTER_CUISINES)


def test_ensure_starter_recipes_idempotent():
    init_db()
    db = SessionLocal()
    try:
        db.query(Meal).delete()
        db.query(RecipeIngredient).delete()
        db.query(Recipe).delete()
        db.commit()
        first = ensure_starter_recipes(db)
        second = ensure_starter_recipes(db)
        assert first == 80
        assert second == 0
        assert db.query(Recipe).count() == 80
        without_image = (
            db.query(Recipe)
            .filter((Recipe.image_url.is_(None)) | (Recipe.image_url == ""))
            .count()
        )
        assert without_image == 80
    finally:
        db.close()
