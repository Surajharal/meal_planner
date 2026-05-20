from unittest.mock import patch

from database import create_recipe, recipe_cuisine
from models import Recipe, SessionLocal, init_db
from recipe_thumbnail_service import (
    CUISINE_FALLBACK_IMAGE_URLS,
    _recipe_context,
    assign_recipe_thumbnail,
    cuisine_fallback_image_url,
    try_set_cuisine_fallback_thumbnail,
)


def test_recipe_context_includes_cuisine():
    r = Recipe(
        name="Dal Tadka",
        description="Starter · Indian · Vegetarian. Comforting lentils.",
        instructions="Cook.",
    )
    query, name_tokens, _ = _recipe_context(r)
    assert "indian" in query.lower()
    assert "dal" in query.lower() or "tadka" in query.lower()
    assert recipe_cuisine(r) == "Indian"


def test_cuisine_fallback_url_for_starter():
    r = Recipe(
        name="Margherita Pizza",
        description="Starter · Italian · Vegetarian.",
        instructions="Bake.",
    )
    assert cuisine_fallback_image_url(r) == CUISINE_FALLBACK_IMAGE_URLS["Italian"]


def test_assign_recipe_thumbnail_uses_pexels_then_fallback():
    init_db()
    db = SessionLocal()
    try:
        recipe = create_recipe(
            db,
            name="Test Curry",
            description="Starter · Indian · Vegetarian. Test.",
            instructions="Simmer.",
        )
        with patch(
            "recipe_thumbnail_service.fetch_pexels_food_photo_url",
            return_value=None,
        ):
            assert assign_recipe_thumbnail(db, recipe) is True
        db.refresh(recipe)
        assert recipe.image_url == CUISINE_FALLBACK_IMAGE_URLS["Indian"]
    finally:
        db.close()


def test_try_set_cuisine_fallback_skips_when_image_present():
    init_db()
    db = SessionLocal()
    try:
        recipe = create_recipe(
            db,
            name="Has Image",
            description="Starter · Thai · Vegetarian.",
            instructions="Mix.",
            image_url="https://example.com/photo.jpg",
        )
        assert try_set_cuisine_fallback_thumbnail(db, recipe) is False
    finally:
        db.close()
