from datetime import date, timedelta

from validators import (
    validate_day,
    validate_email,
    validate_meal_name,
    validate_meal_type,
    validate_servings,
    validate_week_start_date,
)


def test_validate_meal_name_ok():
    ok, err = validate_meal_name("Chicken Curry")
    assert ok is True
    assert err is None


def test_validate_meal_name_rejects_empty():
    ok, err = validate_meal_name("")
    assert ok is False


def test_validate_servings_ok():
    ok, err, val = validate_servings("4")
    assert ok is True
    assert val == 4


def test_validate_servings_rejects_high():
    ok, err, val = validate_servings("99")
    assert ok is False


def test_validate_day_ok():
    ok, err = validate_day("Monday")
    assert ok is True


def test_validate_meal_type_ok():
    ok, err = validate_meal_type("Dinner")
    assert ok is True


def test_validate_week_start_date_ok():
    monday = date.today() - timedelta(days=date.today().weekday())
    ok, err, parsed = validate_week_start_date(monday.isoformat())
    assert ok is True
    assert parsed == monday


def test_validate_email_ok():
    ok, err, email = validate_email("user@example.com")
    assert ok is True
    assert email == "user@example.com"
