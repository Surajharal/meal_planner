"""Add-meal links must pass day/plan_date as proper query params (not a second '?')."""
from datetime import date

from app import app


def test_add_meal_link_from_calendar_includes_day_param():
    week_start = date(2026, 5, 18)
    with app.test_request_context(
        "/",
        method="GET",
    ):
        from flask import url_for

        url = url_for(
            "add_meal",
            week_start=week_start.isoformat(),
            day="Friday",
            meal_type="Lunch",
            plan_date="2026-05-22",
        )
    assert url.count("?") == 1
    assert "day=Friday" in url
    assert "plan_date=2026-05-22" in url
    assert "week_start=2026-05-18" in url


def test_add_meal_get_preselects_from_plan_date():
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["username"] = "test@example.com"
            sess["role"] = "gyama"
        resp = client.get(
            "/add_meal?week_start=2026-05-18&day=Friday&meal_type=Lunch&plan_date=2026-05-22"
        )
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Friday (May 22)" in html
    assert 'value="Friday"' in html and "selected" in html
