from database import recipe_cuisine, recipe_matches_cuisine_filter
from models import Recipe
from validators import validate_recipe_cuisine_filter


def _recipe(desc: str) -> Recipe:
    r = Recipe(
        name="Test",
        description=desc,
        instructions="Steps",
        prep_time=0,
        cook_time=0,
        servings=4,
    )
    r.ingredients = []
    return r


def test_recipe_cuisine_from_starter_description():
    r = _recipe("Starter · Mexican · Vegetarian. Bean bowl.")
    assert recipe_cuisine(r) == "Mexican"


def test_recipe_cuisine_other():
    r = _recipe("AI generated pasta recipe for dinner.")
    assert recipe_cuisine(r) is None
    assert recipe_matches_cuisine_filter(r, "other") is True
    assert recipe_matches_cuisine_filter(r, "Italian") is False


def test_recipe_matches_cuisine_filter():
    r = _recipe("Starter · Japanese · Non-vegetarian. Sushi.")
    assert recipe_matches_cuisine_filter(r, "Japanese") is True
    assert recipe_matches_cuisine_filter(r, "") is True


def test_validate_recipe_cuisine_filter():
    ok, err, val = validate_recipe_cuisine_filter("Thai")
    assert ok and val == "Thai"
    ok, err, val = validate_recipe_cuisine_filter("other")
    assert ok and val == "other"
    ok, err, val = validate_recipe_cuisine_filter("invalid")
    assert not ok
