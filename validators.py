"""
Input validation utilities for the Meal Planner application
"""
import re
from datetime import date
from typing import Optional, Tuple

def validate_meal_name(meal_name: str) -> Tuple[bool, Optional[str]]:
    """Validate meal name"""
    if not meal_name:
        return False, "Meal name is required"
    
    meal_name = meal_name.strip()
    
    if len(meal_name) < 2:
        return False, "Meal name must be at least 2 characters long"
    
    if len(meal_name) > 200:
        return False, "Meal name must be less than 200 characters"
    
    # Check for potentially harmful characters
    if re.search(r'[<>{}[\]\\]', meal_name):
        return False, "Meal name contains invalid characters"
    
    return True, None

def validate_servings(servings: any) -> Tuple[bool, Optional[str], Optional[int]]:
    """Validate servings count"""
    if servings is None:
        return False, "Servings is required", None
    
    try:
        servings_int = int(servings)
    except (ValueError, TypeError):
        return False, "Servings must be a number", None
    
    if servings_int < 1:
        return False, "Servings must be at least 1", None
    
    if servings_int > 50:
        return False, "Servings cannot exceed 50", None
    
    return True, None, servings_int

def validate_day(day: str) -> Tuple[bool, Optional[str]]:
    """Validate day name"""
    valid_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    if not day:
        return False, "Day is required"
    
    if day not in valid_days:
        return False, f"Day must be one of: {', '.join(valid_days)}"
    
    return True, None

def validate_meal_type(meal_type: str) -> Tuple[bool, Optional[str]]:
    """Validate meal type"""
    valid_types = ['Breakfast', 'Lunch', 'Dinner', 'Snack']
    
    if not meal_type:
        return False, "Meal type is required"
    
    if meal_type not in valid_types:
        return False, f"Meal type must be one of: {', '.join(valid_types)}"
    
    return True, None

def validate_week_start_date(week_start_str: str) -> Tuple[bool, Optional[str], Optional[date]]:
    """Validate and parse week start date"""
    if not week_start_str:
        return False, "Week start date is required", None
    
    # Clean the string
    week_start_str = week_start_str.strip()
    if '?' in week_start_str:
        week_start_str = week_start_str.split('?')[0]
    
    try:
        parsed_date = date.fromisoformat(week_start_str)
    except ValueError:
        return False, "Invalid date format. Use YYYY-MM-DD", None
    
    # Check if date is reasonable (not too far in past/future)
    today = date.today()
    if parsed_date < date(2020, 1, 1):
        return False, "Date cannot be before 2020", None
    
    if parsed_date > date(2030, 12, 31):
        return False, "Date cannot be after 2030", None
    
    return True, None, parsed_date

def validate_ingredient_name(name: str) -> Tuple[bool, Optional[str]]:
    """Validate ingredient name"""
    if not name:
        return False, "Ingredient name is required"
    
    name = name.strip()
    
    if len(name) < 1:
        return False, "Ingredient name cannot be empty"
    
    if len(name) > 100:
        return False, "Ingredient name must be less than 100 characters"
    
    return True, None

def validate_quantity(quantity: any) -> Tuple[bool, Optional[str], Optional[float]]:
    """Validate ingredient quantity"""
    if quantity is None:
        return False, "Quantity is required", None
    
    try:
        quantity_float = float(quantity)
    except (ValueError, TypeError):
        return False, "Quantity must be a number", None
    
    if quantity_float < 0:
        return False, "Quantity cannot be negative", None
    
    if quantity_float > 10000:
        return False, "Quantity is too large", None
    
    return True, None, quantity_float

def sanitize_string(input_str: str) -> str:
    """Sanitize string input to prevent XSS"""
    if not input_str:
        return ""
    
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>]', '', input_str)
    return sanitized.strip()

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> Tuple[bool, Optional[str], Optional[str]]:
    e = normalize_email(email)
    if not e or len(e) > 255:
        return False, "Enter a valid email address.", None
    if not _EMAIL_RE.match(e):
        return False, "Enter a valid email address.", None
    return True, None, e


def validate_password(password: str, min_len: int = 6) -> Tuple[bool, Optional[str]]:
    if not password or len(password) < min_len:
        return False, f"Password must be at least {min_len} characters."
    if len(password) > 128:
        return False, "Password is too long."
    return True, None


def validate_recipe_cuisine_filter(raw: str) -> Tuple[bool, Optional[str], str]:
    """Query param for recipes list: cuisine name or 'other' for non-starter recipes."""
    from starter_recipes import STARTER_CUISINES

    s = (raw or "").strip()
    if not s:
        return True, None, ""
    if s.lower() == "other":
        return True, None, "other"
    for name in STARTER_CUISINES:
        if s.lower() == name.lower():
            return True, None, name
    allowed = ", ".join(list(STARTER_CUISINES) + ["Other"])
    return False, f"Cuisine must be one of: {allowed}", ""


def validate_recipe_diet_filter(raw: str) -> Tuple[bool, Optional[str], str]:
    """Query param for recipes list: all, vegetarian, or non-vegetarian."""
    s = (raw or "").strip().lower()
    if not s or s in ("all", "any"):
        return True, None, ""
    if s in ("veg", "vegetarian"):
        return True, None, "veg"
    if s in ("non_veg", "nonveg", "non-veg", "non_vegetarian"):
        return True, None, "non_veg"
    return False, "Invalid diet filter", ""


def validate_role(role: str) -> Tuple[bool, Optional[str]]:
    allowed = ("admin", "gyama")
    r = (role or "").strip()
    if r not in allowed:
        return False, f"Role must be one of: {', '.join(allowed)}"
    return True, None


def validate_ai_diet_profile(data: dict) -> Tuple[bool, Optional[str], Optional[dict]]:
    """Validate AI diet questionnaire; returns cleaned dict on success."""
    goals = {"lose_weight", "gain_weight", "maintain"}
    activity = {"sedentary", "light", "moderate", "active", "very_active"}
    sex_opts = {"female", "male", "other", "prefer_not_say"}

    try:
        weight = float(data.get("weight_kg"))
        height = float(data.get("height_cm"))
        age = int(data.get("age"))
    except (TypeError, ValueError):
        return False, "Weight, height, and age must be valid numbers.", None

    if weight < 25 or weight > 300:
        return False, "Weight (kg) should be between 25 and 300.", None
    if height < 80 or height > 250:
        return False, "Height (cm) should be between 80 and 250.", None
    if age < 13 or age > 120:
        return False, "Age should be between 13 and 120.", None

    sex = (data.get("sex") or "").strip()
    if sex not in sex_opts:
        return False, "Please select a valid sex option.", None

    goal = (data.get("goal") or "").strip()
    if goal not in goals:
        return False, "Please select a weight goal.", None

    act = (data.get("activity_level") or "").strip()
    if act not in activity:
        return False, "Please select an activity level.", None

    restrictions = sanitize_string(str(data.get("dietary_restrictions") or ""))[:2000]
    allergies = sanitize_string(str(data.get("allergies") or ""))[:2000]
    notes = sanitize_string(str(data.get("extra_notes") or ""))[:2000]

    return True, None, {
        "weight_kg": weight,
        "height_cm": height,
        "age": age,
        "sex": sex,
        "goal": goal,
        "activity_level": act,
        "dietary_restrictions": restrictions or None,
        "allergies": allergies or None,
        "extra_notes": notes or None,
    }


def validate_style_hint(style_hint) -> Tuple[bool, Optional[str], str]:
    """Optional short hint for pantry / AI generation (empty allowed)."""
    if style_hint is None or not str(style_hint).strip():
        return True, None, ""
    h = sanitize_string(str(style_hint).strip())
    if len(h) > 500:
        return False, "Style hint must be 500 characters or less", ""
    return True, None, h

def validate_optional_recipe_image_url(
    raw: Optional[str],
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Optional HTTPS/HTTP URL for recipe cover image."""
    s = (raw or "").strip()
    if not s:
        return True, None, None
    if len(s) > 512:
        return False, "Image URL must be 512 characters or less", None
    low = s.lower()
    if not (low.startswith("https://") or low.startswith("http://")):
        return False, "Image URL must start with http:// or https://", None
    if " " in s or "\n" in s or "\r" in s or "\t" in s:
        return False, "Image URL cannot contain whitespace", None
    return True, None, s


def validate_recipe_id(recipe_id: any) -> Tuple[bool, Optional[str], Optional[int]]:
    """Validate recipe ID"""
    if recipe_id is None:
        return False, "Recipe ID is required", None
    
    try:
        recipe_id_int = int(recipe_id)
    except (ValueError, TypeError):
        return False, "Recipe ID must be a number", None
    
    if recipe_id_int < 1:
        return False, "Invalid recipe ID", None
    
    return True, None, recipe_id_int
