import json
import re
import time

import google.generativeai as genai
from google.api_core import exceptions as google_api_exceptions

from config import Config
from typing import Dict, List, Optional


def _is_quota_or_rate_limit(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (google_api_exceptions.ResourceExhausted, google_api_exceptions.TooManyRequests),
    ):
        return True
    msg = str(exc).lower()
    return "429" in msg or "quota" in msg or "resource exhausted" in msg


class GeminiService:
    def __init__(self):
        if not Config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not configured")
        genai.configure(api_key=Config.GEMINI_API_KEY)
        # Use gemini-1.5-flash (faster) or gemini-1.5-pro (more capable)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def _generate_content_text(self, prompt: str) -> str:
        """Call the model with retries on free-tier / burst quota (429)."""
        last: Optional[BaseException] = None
        for attempt in range(5):
            try:
                response = self.model.generate_content(prompt)
                return (response.text or "").strip()
            except Exception as e:
                last = e
                if _is_quota_or_rate_limit(e) and attempt < 4:
                    wait = min(90.0, (2**attempt) + 1.0)
                    m = re.search(r"retry in ([\d.]+)\s*s", str(e), re.I)
                    if m:
                        wait = max(wait, float(m.group(1)) + 1.0)
                    time.sleep(wait)
                    continue
                raise
        assert last is not None
        raise last
    
    def generate_recipe(self, meal_name: str, meal_type: str = "dinner", servings: int = 4) -> Dict:
        """Generate a recipe using Gemini AI"""
        prompt = f"""Generate a detailed recipe for {meal_name} ({meal_type}) for {servings} servings.

Please provide the response in the following JSON format:
{{
    "name": "{meal_name}",
    "description": "A brief description of the dish",
    "instructions": "Step-by-step cooking instructions. Number each step clearly.",
    "prep_time": <number in minutes>,
    "cook_time": <number in minutes>,
    "servings": {servings},
    "nutrition": {{
        "calories_kcal": <approximate TOTAL calories for the entire recipe (all servings combined)>,
        "protein_g": <approximate TOTAL protein in grams for the entire recipe>,
        "carbs_g": <approximate TOTAL carbohydrates in grams for the entire recipe>,
        "fat_g": <approximate TOTAL fat in grams for the entire recipe>
    }},
    "ingredients": [
        {{
            "name": "ingredient name",
            "quantity": <number>,
            "unit": "unit (kg, g, cup, tbsp, tsp, piece, etc.)",
            "category": "category (vegetables, spices, dairy, grains, meat, fruits, etc.)"
        }}
    ]
}}

Make sure to:
- Include all necessary ingredients with accurate quantities
- Provide clear, numbered step-by-step instructions
- Estimate realistic prep and cook times
- Categorize ingredients properly
- Provide best-effort nutrition estimates for the FULL batch (all {servings} servings); use numbers only
- Return ONLY valid JSON, no additional text before or after"""

        try:
            text = self._generate_content_text(prompt)
            
            # Clean the response to extract JSON
            # Remove markdown code blocks if present
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*', '', text)
            text = text.strip()
            
            # Try to parse JSON
            recipe_data = json.loads(text)
            
            # Validate required fields
            required_fields = ['name', 'instructions', 'ingredients']
            for field in required_fields:
                if field not in recipe_data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Set defaults
            recipe_data.setdefault('description', '')
            recipe_data.setdefault('prep_time', 0)
            recipe_data.setdefault('cook_time', 0)
            recipe_data.setdefault('servings', servings)
            if not isinstance(recipe_data.get("nutrition"), dict):
                recipe_data["nutrition"] = {}
            
            return recipe_data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse Gemini response as JSON: {str(e)}")
        except Exception as e:
            raise Exception(f"Error generating recipe: {str(e)}")
    
    def generate_recipe_from_pantry(
        self,
        pantry_lines: List[str],
        meal_type: str = "dinner",
        servings: int = 4,
        style_hint: str = "",
    ) -> Dict:
        """Generate a recipe that uses the user's available ingredients (plus basic staples)."""
        pantry_block = "\n".join(f"- {line}" for line in pantry_lines)
        hint_block = f"\nUser preferences / cuisine style (optional): {style_hint}\n" if style_hint.strip() else ""

        prompt = f"""You are helping plan a meal. The cook has ONLY these ingredients on hand (with approximate amounts):
{pantry_block}
{hint_block}
Meal type: {meal_type}
Servings: {servings}

You may ALSO use basic pantry staples if essential: salt, black pepper, water, cooking oil, sugar, and common spices (e.g. turmeric, cumin) only when necessary. Do not assume ingredients not listed above except those staples.

Invent ONE cohesive dish name and recipe that uses as much of the listed ingredients as reasonable.

Return ONLY valid JSON in this exact shape (no markdown, no extra text):
{{
    "name": "Short descriptive dish name",
    "description": "Brief description",
    "instructions": "Numbered step-by-step instructions as one string or clear steps.",
    "prep_time": <minutes as integer>,
    "cook_time": <minutes as integer>,
    "servings": {servings},
    "nutrition": {{
        "calories_kcal": <approximate TOTAL kcal for the entire recipe (all servings)>,
        "protein_g": <TOTAL protein g for entire recipe>,
        "carbs_g": <TOTAL carbs g for entire recipe>,
        "fat_g": <TOTAL fat g for entire recipe>
    }},
    "ingredients": [
        {{
            "name": "ingredient name",
            "quantity": <number>,
            "unit": "kg, g, cup, tbsp, tsp, piece, etc.",
            "category": "vegetables, spices, dairy, grains, meat, fruits, other"
        }}
    ]
}}

The ingredients array should reflect what the recipe actually uses (from the available list and allowed staples). Quantities should be realistic for {servings} servings. Nutrition values are estimates for the full batch."""

        try:
            text = self._generate_content_text(prompt)
            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*", "", text)
            text = text.strip()
            recipe_data = json.loads(text)
            required_fields = ["name", "instructions", "ingredients"]
            for field in required_fields:
                if field not in recipe_data:
                    raise ValueError(f"Missing required field: {field}")
            recipe_data.setdefault("description", "")
            recipe_data.setdefault("prep_time", 0)
            recipe_data.setdefault("cook_time", 0)
            recipe_data.setdefault("servings", servings)
            if not isinstance(recipe_data.get("nutrition"), dict):
                recipe_data["nutrition"] = {}
            return recipe_data
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse Gemini response as JSON: {str(e)}")
        except Exception as e:
            raise Exception(f"Error generating pantry recipe: {str(e)}")
    
    def extract_ingredients_from_text(self, recipe_text: str) -> List[Dict]:
        """Extract ingredients from recipe text using Gemini"""
        prompt = f"""Extract ingredients from the following recipe text and return them in JSON format:

{recipe_text}

Return a JSON array of ingredients in this format:
[
    {{
        "name": "ingredient name",
        "quantity": <number>,
        "unit": "unit (kg, g, cup, tbsp, tsp, piece, etc.)",
        "category": "category (vegetables, spices, dairy, grains, meat, fruits, etc.)"
    }}
]

Return ONLY valid JSON array, no additional text."""

        try:
            text = self._generate_content_text(prompt)
            
            # Clean the response
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*', '', text)
            text = text.strip()
            
            ingredients = json.loads(text)
            
            if not isinstance(ingredients, list):
                raise ValueError("Expected a list of ingredients")
            
            return ingredients
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse ingredients: {str(e)}")
        except Exception as e:
            raise Exception(f"Error extracting ingredients: {str(e)}")
    
    def suggest_meals(self, preferences: str = "", dietary_restrictions: str = "") -> List[str]:
        """Get meal suggestions from Gemini"""
        prompt = f"""Suggest 7 diverse meal ideas for a weekly meal plan.
        
Preferences: {preferences if preferences else "None"}
Dietary restrictions: {dietary_restrictions if dietary_restrictions else "None"}

Return a JSON array of meal names:
["Meal 1", "Meal 2", "Meal 3", ...]

Return ONLY valid JSON array, no additional text."""

        try:
            text = self._generate_content_text(prompt)
            
            # Clean the response
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*', '', text)
            text = text.strip()
            
            meals = json.loads(text)
            
            if not isinstance(meals, list):
                raise ValueError("Expected a list of meals")
            
            return meals[:7]  # Return max 7 meals
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse meal suggestions: {str(e)}")
        except Exception as e:
            raise Exception(f"Error getting meal suggestions: {str(e)}")

    def generate_personalized_diet_plan(self, profile: Dict) -> str:
        """Generate diet guidance from user profile. General wellness only — not medical advice."""
        goal_labels = {
            "lose_weight": "lose weight / fat loss",
            "gain_weight": "gain weight / build mass",
            "maintain": "maintain current weight",
        }
        activity_labels = {
            "sedentary": "mostly seated, little exercise",
            "light": "light exercise 1–3 days/week",
            "moderate": "moderate exercise 3–5 days/week",
            "active": "hard exercise 6–7 days/week",
            "very_active": "very hard daily exercise or physical job",
        }
        goal_txt = goal_labels.get(profile["goal"], profile["goal"])
        act_txt = activity_labels.get(profile["activity_level"], profile["activity_level"])
        restrictions = profile.get("dietary_restrictions") or "None stated"
        allergies = profile.get("allergies") or "None stated"
        notes = profile.get("extra_notes") or "None"

        prompt = f"""You are a supportive nutrition coach (not a doctor). Create a practical, encouraging weekly-style diet and lifestyle outline for this person.

Profile:
- Age: {profile['age']} years
- Sex: {profile['sex']}
- Weight: {profile['weight_kg']} kg
- Height: {profile['height_cm']} cm
- Goal: {goal_txt}
- Activity: {act_txt}
- Dietary preferences / restrictions: {restrictions}
- Allergies / avoid: {allergies}
- Extra notes from user: {notes}

Requirements:
1. Start with a short disclaimer that this is general wellness information, not medical advice, and they should consult a healthcare professional for medical conditions.
2. Estimate approximate daily calorie range if appropriate (state clearly it is an estimate).
3. Give macronutrient emphasis suited to their goal (high level, not overly precise).
4. Outline 7 days of meal ideas (breakfast, lunch, dinner, snacks) — realistic, varied, and respecting stated allergies/restrictions.
5. Add hydration, simple habits, and optional exercise tips aligned with their activity level.
6. Use clear headings and bullet points. Plain text or light markdown (## headings, - bullets). No JSON.
7. Be concise but actionable (roughly 800–1500 words)."""

        try:
            return self._generate_content_text(prompt)
        except Exception as e:
            raise Exception(f"Error generating diet plan: {str(e)}")

    def suggest_meals_for_plan_slots(
        self, profile: Dict, slots: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """
        Given user diet profile and empty (day, meal_type) slots, return one dish name per slot.
        slots: [{"day": "Monday", "meal_type": "Dinner"}, ...]
        Returns same length: [{"day", "meal_type", "meal_name"}, ...]
        """
        if not slots:
            return []

        goal_labels = {
            "lose_weight": "lose weight / fat loss",
            "gain_weight": "gain weight / build mass",
            "maintain": "maintain current weight",
        }
        activity_labels = {
            "sedentary": "mostly seated, little exercise",
            "light": "light exercise 1–3 days/week",
            "moderate": "moderate exercise 3–5 days/week",
            "active": "hard exercise 6–7 days/week",
            "very_active": "very hard daily exercise or physical job",
        }
        goal_txt = goal_labels.get(profile.get("goal"), profile.get("goal", ""))
        act_txt = activity_labels.get(
            profile.get("activity_level"), profile.get("activity_level", "")
        )
        restrictions = profile.get("dietary_restrictions") or "None stated"
        allergies = profile.get("allergies") or "None stated"
        notes = profile.get("extra_notes") or "None"

        slots_json = json.dumps(slots, ensure_ascii=False)
        prompt = f"""You are a meal planner (not a doctor). Suggest ONE concrete dish name for each empty calendar slot below.

User profile:
- Age: {profile.get("age")} years, sex: {profile.get("sex")}
- Weight: {profile.get("weight_kg")} kg, height: {profile.get("height_cm")} cm
- Goal: {goal_txt}
- Activity: {act_txt}
- Dietary restrictions / preferences: {restrictions}
- Allergies / avoid: {allergies}
- Extra notes: {notes}

Empty slots to fill (in order — output exactly one meal per slot, same order):
{slots_json}

Rules:
- Respect allergies and restrictions strictly.
- Names should be specific enough to cook (e.g. "Chicken tikka with brown rice", not just "protein").
- Vary cuisines and proteins across the week where possible.
- Snacks should be simple (e.g. yogurt with fruit, handful of nuts).

Return ONLY valid JSON in this shape (no markdown):
{{
  "meals": [
    {{"day": "Monday", "meal_type": "Dinner", "meal_name": "Dish name here"}},
    ...
  ]
}}

The "meals" array MUST have exactly {len(slots)} items, in the same order as the input slots, with matching "day" and "meal_type" for each."""

        try:
            text = self._generate_content_text(prompt)
            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*", "", text)
            text = text.strip()
            data = json.loads(text)
            meals = data.get("meals")
            if not isinstance(meals, list) or len(meals) != len(slots):
                raise ValueError("Invalid meals array length from model")
            out = []
            for i, slot in enumerate(slots):
                m = meals[i] if i < len(meals) else {}
                if not isinstance(m, dict):
                    raise ValueError("Invalid meal entry")
                name = str(m.get("meal_name", "")).strip()
                if not name:
                    raise ValueError(f"Missing meal_name for {slot['day']} {slot['meal_type']}")
                out.append(
                    {
                        "day": slot["day"],
                        "meal_type": slot["meal_type"],
                        "meal_name": name,
                    }
                )
            return out
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse meal slot suggestions: {e}")
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise Exception(f"Error suggesting meals for slots: {str(e)}")

    def generate_full_recipes_for_plan_slots(
        self,
        profile: Dict,
        slots: List[Dict[str, str]],
        servings: int = 4,
    ) -> List[Dict]:
        """
        One API call for several slots: full recipe JSON each (saves quota vs one call per meal).
        Returns [{"day", "meal_type", "recipe": {...}}, ...] in the same order as slots.
        """
        if not slots:
            return []

        goal_labels = {
            "lose_weight": "lose weight / fat loss",
            "gain_weight": "gain weight / build mass",
            "maintain": "maintain current weight",
        }
        activity_labels = {
            "sedentary": "mostly seated, little exercise",
            "light": "light exercise 1–3 days/week",
            "moderate": "moderate exercise 3–5 days/week",
            "active": "hard exercise 6–7 days/week",
            "very_active": "very hard daily exercise or physical job",
        }
        goal_txt = goal_labels.get(profile.get("goal"), profile.get("goal", ""))
        act_txt = activity_labels.get(
            profile.get("activity_level"), profile.get("activity_level", "")
        )
        restrictions = profile.get("dietary_restrictions") or "None stated"
        allergies = profile.get("allergies") or "None stated"
        notes = profile.get("extra_notes") or "None"
        slots_json = json.dumps(slots, ensure_ascii=False)

        recipe_shape = f"""{{
      "day": "<same as slot>",
      "meal_type": "<same as slot>",
      "name": "Dish title",
      "description": "Brief description",
      "instructions": "Numbered step-by-step as one string",
      "prep_time": <minutes int>,
      "cook_time": <minutes int>,
      "servings": {servings},
      "nutrition": {{
        "calories_kcal": <TOTAL for full recipe>,
        "protein_g": <TOTAL g>,
        "carbs_g": <TOTAL g>,
        "fat_g": <TOTAL g>
      }},
      "ingredients": [
        {{"name": "...", "quantity": <number>, "unit": "g or cup etc.", "category": "vegetables|dairy|..."}}
      ]
    }}"""

        prompt = f"""You are a recipe generator (not a doctor). Produce ONE complete recipe JSON object for EACH calendar slot below.

User profile:
- Age: {profile.get("age")} years, sex: {profile.get("sex")}
- Weight: {profile.get("weight_kg")} kg, height: {profile.get("height_cm")} cm
- Goal: {goal_txt}
- Activity: {act_txt}
- Dietary restrictions / preferences: {restrictions}
- Allergies / avoid: {allergies}
- Extra notes: {notes}

Slots to fill (same order in output; each recipe must match day + meal_type):
{slots_json}

Rules:
- Respect allergies and restrictions strictly.
- Snacks: simple, realistic portions.
- "instructions" must be clear steps (string). Nutrition is approximate TOTALS for the full recipe batch.
- Return ONLY valid JSON, no markdown:
{{
  "recipes": [
    {recipe_shape.strip()},
    ...
  ]
}}

The "recipes" array MUST have exactly {len(slots)} items, same order as the input slots, with matching "day" and "meal_type" for each."""

        text = self._generate_content_text(prompt)
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        text = text.strip()
        data = json.loads(text)
        recipes = data.get("recipes")
        if not isinstance(recipes, list) or len(recipes) != len(slots):
            raise ValueError(
                f"Expected {len(slots)} recipes from model, got {len(recipes) if isinstance(recipes, list) else type(recipes)}"
            )

        out: List[Dict] = []
        for i, slot in enumerate(slots):
            row = recipes[i]
            if not isinstance(row, dict):
                raise ValueError("Invalid recipe entry")
            if row.get("day") != slot["day"] or row.get("meal_type") != slot["meal_type"]:
                row["day"] = slot["day"]
                row["meal_type"] = slot["meal_type"]
            body = {k: v for k, v in row.items() if k not in ("day", "meal_type")}
            for field in ("name", "instructions", "ingredients"):
                if field not in body:
                    raise ValueError(f"Missing {field} for {slot['day']} {slot['meal_type']}")
            if not isinstance(body.get("ingredients"), list):
                raise ValueError("ingredients must be a list")
            out.append(
                {
                    "day": slot["day"],
                    "meal_type": slot["meal_type"],
                    "recipe": body,
                }
            )
        return out

    def regenerate_recipe(
        self,
        recipe_name: str,
        meal_type: str = "dinner",
        servings: int = 4,
        tweak: str = "",
    ) -> Dict:
        """Regenerate an existing shared recipe with optional user adjustments."""
        tweak_block = ""
        if tweak and tweak.strip():
            tweak_block = f"\nUser requested changes: {tweak.strip()}\n"

        prompt = f"""Regenerate an improved, complete recipe for "{recipe_name}" ({meal_type}) for {servings} servings.
{tweak_block}
Keep the dish recognizable unless the user changes require a new name.

Provide the response in the following JSON format:
{{
    "name": "{recipe_name}",
    "description": "A brief description of the dish",
    "instructions": "Step-by-step cooking instructions. Number each step clearly.",
    "prep_time": <number in minutes>,
    "cook_time": <number in minutes>,
    "servings": {servings},
    "nutrition": {{
        "calories_kcal": <approximate TOTAL calories for the entire recipe (all servings combined)>,
        "protein_g": <approximate TOTAL protein in grams for the entire recipe>,
        "carbs_g": <approximate TOTAL carbohydrates in grams for the entire recipe>,
        "fat_g": <approximate TOTAL fat in grams for the entire recipe>
    }},
    "ingredients": [
        {{
            "name": "ingredient name",
            "quantity": <number>,
            "unit": "unit (kg, g, cup, tbsp, tsp, piece, etc.)",
            "category": "category (vegetables, spices, dairy, grains, meat, fruits, etc.)"
        }}
    ]
}}

Return ONLY valid JSON, no markdown fences or extra text."""

        try:
            text = self._generate_content_text(prompt)
            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*", "", text)
            text = text.strip()
            recipe_data = json.loads(text)
            required_fields = ["name", "instructions", "ingredients"]
            for field in required_fields:
                if field not in recipe_data:
                    raise ValueError(f"Missing required field: {field}")
            recipe_data.setdefault("description", "")
            recipe_data.setdefault("prep_time", 0)
            recipe_data.setdefault("cook_time", 0)
            recipe_data.setdefault("servings", servings)
            if not isinstance(recipe_data.get("nutrition"), dict):
                recipe_data["nutrition"] = {}
            return recipe_data
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse Gemini response as JSON: {str(e)}") from e
        except Exception as e:
            raise Exception(f"Error regenerating recipe: {str(e)}") from e
