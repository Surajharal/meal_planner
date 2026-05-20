"""Stock food photos for recipe thumbnails via Pexels with relevance scoring."""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from contextvars import ContextVar
from typing import TYPE_CHECKING, Iterable, Optional

from config import Config
from database import recipe_cuisine

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Stable Pexels CDN URLs (no API) used when search fails or PEXELS_API_KEY is unset.
CUISINE_FALLBACK_IMAGE_URLS: dict[str, str] = {
    "Indian": "https://images.pexels.com/photos/2474661/pexels-photo-2474661.jpeg?auto=compress&cs=tinysrgb&w=600",
    "Italian": "https://images.pexels.com/photos/1279330/pexels-photo-1279330.jpeg?auto=compress&cs=tinysrgb&w=600",
    "Mexican": "https://images.pexels.com/photos/2087740/pexels-photo-2087740.jpeg?auto=compress&cs=tinysrgb&w=600",
    "Japanese": "https://images.pexels.com/photos/357756/pexels-photo-357756.jpeg?auto=compress&cs=tinysrgb&w=600",
    "Chinese": "https://images.pexels.com/photos/1907244/pexels-photo-1907244.jpeg?auto=compress&cs=tinysrgb&w=600",
    "Thai": "https://images.pexels.com/photos/2233348/pexels-photo-2233348.jpeg?auto=compress&cs=tinysrgb&w=600",
    "Mediterranean": "https://images.pexels.com/photos/1640777/pexels-photo-1640777.jpeg?auto=compress&cs=tinysrgb&w=600",
    "American": "https://images.pexels.com/photos/1639562/pexels-photo-1639562.jpeg?auto=compress&cs=tinysrgb&w=600",
}
_GENERIC_FOOD_FALLBACK_URL = (
    "https://images.pexels.com/photos/1640774/pexels-photo-1640774.jpeg"
    "?auto=compress&cs=tinysrgb&w=600"
)

logger = logging.getLogger(__name__)
_LAST_PEXELS_ERROR: ContextVar[Optional[str]] = ContextVar(
    "last_pexels_error", default=None
)
_NO_MATCH_ERROR = "No confident stock photo match found for this recipe."
_MIN_MATCH_SCORE = 2.6
_MAX_RESULTS = 12
_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "without",
    "style",
    "recipe",
    "dish",
    "meal",
    "fresh",
    "healthy",
    "quick",
    "easy",
    "small",
    "large",
    "mixed",
}


def _set_last_pexels_error(message: Optional[str]) -> None:
    _LAST_PEXELS_ERROR.set(message)


def get_last_pexels_error() -> Optional[str]:
    return _LAST_PEXELS_ERROR.get()


def pexels_configured() -> bool:
    return bool(getattr(Config, "PEXELS_API_KEY", "") or "")


def _meaningful_tokens(text: str) -> list[str]:
    toks = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]*", (text or "").lower())
    return [t for t in toks if len(t) > 2 and t not in _STOPWORDS]


def _first_unique(tokens: Iterable[str], limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in tokens:
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _recipe_context(recipe) -> tuple[str, set[str], set[str]]:
    name = (getattr(recipe, "name", "") or "").strip()
    name_tokens = set(_first_unique(_meaningful_tokens(name), 8))
    cuisine = recipe_cuisine(recipe) or ""
    cuisine_tokens = _meaningful_tokens(cuisine) if cuisine else []
    ingredient_tokens: list[str] = []
    for ri in list(getattr(recipe, "ingredients", []) or []):
        ing = getattr(ri, "ingredient", None)
        ing_name = getattr(ing, "name", "") if ing else ""
        ingredient_tokens.extend(_meaningful_tokens(ing_name))
    ing_set = set(_first_unique(ingredient_tokens, 8))
    query_tokens = _first_unique(cuisine_tokens + list(name_tokens) + list(ing_set), 8)
    query = " ".join(query_tokens + ["food", "dish"]) if query_tokens else f"{name} food dish"
    if cuisine and cuisine.lower() not in query.lower():
        query = f"{cuisine} {query}"
    return query, name_tokens, ing_set


def _photo_score(photo: dict, name_tokens: set[str], ingredient_tokens: set[str]) -> float:
    alt = (photo.get("alt") or "").lower()
    url = (photo.get("url") or "").lower()
    text_tokens = set(_meaningful_tokens(alt) + _meaningful_tokens(url))
    if not text_tokens:
        return 0.0

    score = 0.0
    name_overlap = len(text_tokens.intersection(name_tokens))
    ingredient_overlap = len(text_tokens.intersection(ingredient_tokens))
    score += name_overlap * 1.6
    score += ingredient_overlap * 0.75
    if name_tokens and name_overlap >= min(2, len(name_tokens)):
        score += 1.2

    mismatch_penalties = {"sandwich", "burger", "pizza", "fries", "dessert", "cake"}
    if text_tokens.intersection(mismatch_penalties) and not name_tokens.intersection(
        mismatch_penalties
    ):
        score -= 1.0
    return score


def fetch_pexels_food_photo_url(recipe) -> Optional[str]:
    """Return best-match CDN image URL for a recipe using Pexels result scoring."""
    key = getattr(Config, "PEXELS_API_KEY", "") or ""
    name = (getattr(recipe, "name", "") or "").strip()
    if not key or not name:
        _set_last_pexels_error("Missing Pexels API key or recipe name.")
        return None

    query, name_tokens, ingredient_tokens = _recipe_context(recipe)
    encoded = urllib.parse.quote_plus(query)
    api_url = f"https://api.pexels.com/v1/search?query={encoded}&per_page={_MAX_RESULTS}&orientation=landscape"
    req = urllib.request.Request(
        api_url,
        headers={
            "Authorization": key,
            "User-Agent": "Mozilla/5.0 (MealPlanner/1.0)",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=18) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")
        except Exception:
            body = ""
        body_l = body.lower()
        if e.code == 403 and "1010" in body_l:
            err_msg = "Pexels blocked this request (Cloudflare 1010). Try again later or use a different network."
        elif e.code == 401:
            err_msg = "Pexels rejected the API key (401 Unauthorized). Check PEXELS_API_KEY."
        else:
            err_msg = f"Pexels API request failed ({e.code} {e.reason})."
        _set_last_pexels_error(err_msg)
        return None
    except Exception as e:
        _set_last_pexels_error(f"Pexels request failed: {e}")
        logger.warning("Pexels request failed for %r: %s", name, e)
        return None

    photos = payload.get("photos") or []
    if not photos:
        _set_last_pexels_error("No matching stock photo found for this recipe name.")
        return None

    best_photo = None
    best_score = -999.0
    for p in photos:
        score = _photo_score(p, name_tokens, ingredient_tokens)
        if score > best_score:
            best_score = score
            best_photo = p

    if not best_photo or best_score < _MIN_MATCH_SCORE:
        logger.info(
            "Stock image skipped for %r: low confidence (score=%.2f, query=%r)",
            name,
            best_score,
            query,
        )
        _set_last_pexels_error(_NO_MATCH_ERROR)
        return None

    src = best_photo.get("src") or {}
    _set_last_pexels_error(None)
    return src.get("medium") or src.get("small") or src.get("large")


def cuisine_fallback_image_url(recipe) -> Optional[str]:
    """Best-effort cover image from cuisine (starter catalog) or a generic food photo."""
    cuisine = recipe_cuisine(recipe)
    if cuisine and cuisine in CUISINE_FALLBACK_IMAGE_URLS:
        return CUISINE_FALLBACK_IMAGE_URLS[cuisine]
    return _GENERIC_FOOD_FALLBACK_URL


def try_set_cuisine_fallback_thumbnail(db: "Session", recipe) -> bool:
    """Set image_url from cuisine-matched stock art when Pexels search is unavailable."""
    if getattr(recipe, "image_url", None):
        return False
    url = cuisine_fallback_image_url(recipe)
    if not url:
        return False
    from database import update_recipe_image_url

    update_recipe_image_url(db, recipe.id, url)
    recipe.image_url = url
    return True


def assign_recipe_thumbnail(db: "Session", recipe) -> bool:
    """
    Set recipe.image_url: Pexels search by dish + cuisine, else cuisine fallback image.
    Returns True if a URL was saved.
    """
    if getattr(recipe, "image_url", None):
        return True
    if try_set_recipe_thumbnail_from_stock(db, recipe):
        return True
    return try_set_cuisine_fallback_thumbnail(db, recipe)


def try_set_recipe_thumbnail_from_stock(db: "Session", recipe) -> bool:
    """
    If recipe has no image_url and Pexels is configured, set image_url from search.
    Returns True if a URL was saved.
    """
    if getattr(recipe, "image_url", None):
        return False
    if not pexels_configured():
        return False

    from database import update_recipe_image_url

    img_url = fetch_pexels_food_photo_url(recipe)
    if not img_url:
        return False
    update_recipe_image_url(db, recipe.id, img_url)
    recipe.image_url = img_url
    return True


def _load_recipe_with_ingredients(db: "Session", recipe_id: int):
    from models import Recipe, RecipeIngredient
    from sqlalchemy.orm import joinedload

    return (
        db.query(Recipe)
        .options(
            joinedload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient)
        )
        .filter(Recipe.id == recipe_id)
        .one()
    )


def backfill_missing_thumbnails(db: "Session", limit: int = 15) -> tuple[int, int]:
    """
    For recipes with no image_url, assign Pexels or cuisine fallback.
    Returns (updated_count, skipped_or_failed_count).
    """
    import time
    from models import Recipe
    from sqlalchemy import or_

    cap = max(1, min(100, int(limit)))
    rows = (
        db.query(Recipe)
        .filter(or_(Recipe.image_url.is_(None), Recipe.image_url == ""))
        .order_by(Recipe.id)
        .limit(cap)
        .all()
    )
    ok = 0
    fail = 0
    for r in rows:
        full = _load_recipe_with_ingredients(db, r.id)
        if assign_recipe_thumbnail(db, full):
            ok += 1
        else:
            fail += 1
        if pexels_configured():
            time.sleep(0.2)
    return (ok, fail)


def backfill_all_missing_thumbnails(
    db: "Session", *, batch_size: int = 25, max_batches: int = 20
) -> tuple[int, int]:
    """Process every recipe missing image_url in batches. Returns (total_updated, total_failed)."""
    total_ok = 0
    total_fail = 0
    for _ in range(max(1, max_batches)):
        ok, fail = backfill_missing_thumbnails(db, batch_size)
        total_ok += ok
        total_fail += fail
        if ok == 0 and fail == 0:
            break
        if fail > 0 and ok == 0:
            break
    return (total_ok, total_fail)
