from uuid import uuid4


def _login(client, user_id, username):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = username
        sess["role"] = "gyama"


def _get_or_create_user(db, user_id, username):
    from models import User

    user = db.query(User).filter(User.id == user_id).first()
    if user:
        return user
    user = User(
        id=user_id,
        username=username,
        email=username,
        password_hash="test-password-hash",
        role="gyama",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_shared_recipe(db):
    from database import add_ingredient_to_recipe, create_recipe

    suffix = uuid4().hex
    recipe = create_recipe(
        db,
        name=f"Shared Regen Source {suffix}",
        description="Original shared recipe",
        instructions="Original instructions",
        prep_time=5,
        cook_time=10,
        servings=2,
    )
    add_ingredient_to_recipe(
        db,
        recipe.id,
        f"Shared Regen Ingredient {suffix}",
        1,
        "unit",
        "other",
    )
    return recipe


def test_regenerate_recipe_creates_private_copy(client, monkeypatch):
    from models import SessionLocal

    owner_id = 91001
    other_id = 91002
    owner_email = "private-regen-owner@example.com"
    other_email = "private-regen-other@example.com"

    db = SessionLocal()
    try:
        _get_or_create_user(db, owner_id, owner_email)
        _get_or_create_user(db, other_id, other_email)
        shared = _create_shared_recipe(db)
        shared_id = shared.id
        shared_name = shared.name
    finally:
        db.close()

    def fake_regenerate_recipe(self, recipe_name, meal_type, servings, tweak):
        return {
            "name": f"{recipe_name} - {tweak}",
            "description": "Private regenerated recipe",
            "instructions": ["Mix", "Serve"],
            "prep_time": 3,
            "cook_time": 4,
            "servings": servings,
            "ingredients": [
                {
                    "name": f"Private Regen Ingredient {uuid4().hex}",
                    "quantity": 2,
                    "unit": "unit",
                    "category": "other",
                }
            ],
        }

    monkeypatch.setattr(
        "meal_planner.GeminiService.regenerate_recipe",
        fake_regenerate_recipe,
    )

    _login(client, owner_id, owner_email)
    response = client.post(
        f"/recipe/{shared_id}/regenerate",
        json={"tweak": "less spicy"},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    private_id = data["recipe_id"]
    assert private_id != shared_id

    db = SessionLocal()
    try:
        from database import get_recipe_by_id

        original = get_recipe_by_id(db, shared_id)
        private = get_recipe_by_id(db, private_id)
        assert original.name == shared_name
        assert original.user_id is None
        assert private.user_id == owner_id
        assert "less spicy" in private.name
    finally:
        db.close()

    owner_page = client.get(f"/recipe/{private_id}")
    assert owner_page.status_code == 200
    assert "Private recipe" in owner_page.get_data(as_text=True)

    _login(client, other_id, other_email)
    other_page = client.get(f"/recipe/{private_id}")
    assert other_page.status_code == 302

    other_api = client.get("/api/recipes").get_json()
    assert private_id not in {recipe["id"] for recipe in other_api["recipes"]}
