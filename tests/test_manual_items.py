def _login(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "test@example.com"
        sess["role"] = "gyama"


def _add_shopping_item(client, name):
    response = client.post(
        "/add_shopping_item",
        json={
            "name": name,
            "quantity": "2",
            "unit": "pcs",
            "category": "produce",
            "week_start": "2026-05-25",
        },
    )
    assert response.status_code == 200
    return response.get_json()["item_id"]


def _add_inventory_item(client, name):
    response = client.post(
        "/add_inventory_item",
        json={
            "name": name,
            "quantity": "3",
            "unit": "pcs",
            "category": "produce",
            "week_start": "2026-05-25",
        },
    )
    assert response.status_code == 200
    return response.get_json()["ingredient_id"]


def test_add_inventory_item_shows_in_other_inventory(client):
    _login(client)
    item_name = "Test Pantry Mango"

    response = client.post(
        "/add_inventory_item",
        data={
            "name": item_name,
            "quantity": "3",
            "unit": "pcs",
            "category": "produce",
            "week_start": "2026-05-25",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Other available inventory" in html
    assert item_name in html


def test_add_shopping_item_shows_in_list(client):
    _login(client)
    item_name = "Test Shopping Apples"

    response = client.post(
        "/add_shopping_item",
        data={
            "name": item_name,
            "quantity": "6",
            "unit": "pcs",
            "category": "produce",
            "week_start": "2026-05-25",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert item_name in html
    assert "Added manually" in html


def test_add_manual_items_with_name_only_defaults_quantity_and_unit(client):
    _login(client)
    inventory_name = "Test Pantry Name Only Papaya"
    shopping_name = "Test Shopping Name Only Kiwi"

    inventory_response = client.post(
        "/add_inventory_item",
        data={
            "name": inventory_name,
            "category": "produce",
            "week_start": "2026-05-25",
        },
        follow_redirects=True,
    )
    shopping_response = client.post(
        "/add_shopping_item",
        data={
            "name": shopping_name,
            "category": "produce",
            "week_start": "2026-05-25",
        },
        follow_redirects=True,
    )

    assert inventory_response.status_code == 200
    assert shopping_response.status_code == 200
    assert inventory_name in inventory_response.get_data(as_text=True)
    assert "1.0 unit" in inventory_response.get_data(as_text=True)
    assert shopping_name in shopping_response.get_data(as_text=True)
    assert "1.0 unit" in shopping_response.get_data(as_text=True)


def test_add_manual_items_with_quantity_or_unit_only(client):
    _login(client)
    quantity_only = "Test Shopping Quantity Only Plums"
    unit_only = "Test Shopping Unit Only Cherries"

    quantity_response = client.post(
        "/add_shopping_item",
        data={
            "name": quantity_only,
            "quantity": "7",
            "category": "produce",
            "week_start": "2026-05-25",
        },
        follow_redirects=True,
    )
    unit_response = client.post(
        "/add_shopping_item",
        data={
            "name": unit_only,
            "unit": "box",
            "category": "produce",
            "week_start": "2026-05-25",
        },
        follow_redirects=True,
    )

    assert quantity_response.status_code == 200
    assert unit_response.status_code == 200
    assert "7.0 unit" in quantity_response.get_data(as_text=True)
    assert "1.0 box" in unit_response.get_data(as_text=True)


def test_edit_manual_shopping_item(client):
    _login(client)
    item_id = _add_shopping_item(client, "Test Shopping Pears")

    response = client.post(
        f"/update_manual_shopping_item/{item_id}",
        data={
            "name": "Test Shopping Green Pears",
            "quantity": "4",
            "unit": "pcs",
            "category": "produce",
            "week_start": "2026-05-25",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Test Shopping Green Pears" in html
    assert "4.0 pcs" in html


def test_edit_manual_shopping_item_can_clear_quantity_and_unit(client):
    _login(client)
    item_id = _add_shopping_item(client, "Test Shopping Clear Qty Unit")

    response = client.post(
        f"/update_manual_shopping_item/{item_id}",
        data={
            "name": "Test Shopping Clear Qty Unit",
            "quantity": "",
            "unit": "",
            "category": "produce",
            "week_start": "2026-05-25",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert "1.0 unit" in response.get_data(as_text=True)


def test_delete_manual_shopping_item(client):
    _login(client)
    item_name = "Test Shopping Delete Grapes"
    item_id = _add_shopping_item(client, item_name)

    response = client.post(
        f"/delete_manual_shopping_item/{item_id}",
        data={"week_start": "2026-05-25"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert item_name not in response.get_data(as_text=True)


def test_move_manual_shopping_item_to_inventory(client):
    _login(client)
    item_name = "Test Shopping Move Oranges"
    item_id = _add_shopping_item(client, item_name)

    response = client.post(
        f"/shopping_item_to_inventory/{item_id}",
        data={"week_start": "2026-05-25"},
    )

    assert response.status_code == 302

    shopping_response = client.get("/shopping_list?week_start=2026-05-25")
    assert item_name not in shopping_response.get_data(as_text=True)

    inventory_response = client.get("/inventory?week_start=2026-05-25")
    inventory_html = inventory_response.get_data(as_text=True)
    assert "Other available inventory" in inventory_html
    assert item_name in inventory_html


def test_edit_and_delete_inventory_item(client):
    _login(client)
    item_name = "Test Pantry Edit Bananas"
    ingredient_id = _add_inventory_item(client, item_name)

    edit_response = client.post(
        f"/update_inventory_item/{ingredient_id}",
        data={
            "name": item_name,
            "quantity": "5",
            "unit": "pcs",
            "category": "produce",
            "previous_unit": "pcs",
            "week_start": "2026-05-25",
        },
        follow_redirects=True,
    )

    assert edit_response.status_code == 200
    edit_html = edit_response.get_data(as_text=True)
    assert item_name in edit_html
    assert "5.0 pcs" in edit_html

    delete_response = client.post(
        f"/delete_inventory_item/{ingredient_id}",
        data={"unit": "pcs", "week_start": "2026-05-25"},
        follow_redirects=True,
    )

    assert delete_response.status_code == 200
    assert item_name not in delete_response.get_data(as_text=True)
