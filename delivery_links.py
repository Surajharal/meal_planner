"""Search URLs for grocery / delivery sites.

Live prices are not available without retailer APIs. These links open each app's
search for an ingredient so the user can compare cost and order there.
"""
from __future__ import annotations

import urllib.parse
from typing import Dict, List, Tuple

# (label, URL template with {q} = encoded search query)
# Zepto / Blinkit: India quick-commerce; catalog depends on delivery pin. URLs may change — adjust if search stops working.
# Zepto: use www.zepto.com (canonical) and param name "query", not "q" — "q" often opens search UI without product results.
_PROVIDER_TEMPLATES: Tuple[Tuple[str, str], ...] = (
    ("Zepto", "https://www.zepto.com/search?query={q}"),
    ("Blinkit", "https://blinkit.com/s/?q={q}"),
    ("Instacart", "https://www.instacart.com/store/products?q={q}"),
    ("Walmart", "https://www.walmart.com/search?q={q}"),
    ("Target", "https://www.target.com/s?searchTerm={q}"),
    ("Amazon", "https://www.amazon.com/s?k={q}"),
    ("DoorDash", "https://www.doordash.com/search/store/?query={q}"),
)


def delivery_search_links(ingredient_name: str) -> List[Dict[str, str]]:
    """Per-item links: search this product name on each service."""
    raw = (ingredient_name or "").strip()
    if not raw:
        return []
    q = urllib.parse.quote_plus(raw)
    return [{"label": label, "url": tpl.format(q=q)} for label, tpl in _PROVIDER_TEMPLATES]


def delivery_app_home_links() -> List[Dict[str, str]]:
    """Home / shop entry points when you want to browse without a search term."""
    return [
        {"label": "Zepto", "url": "https://www.zepto.com/"},
        {"label": "Blinkit", "url": "https://blinkit.com/"},
        {"label": "Instacart", "url": "https://www.instacart.com/"},
        {"label": "Walmart", "url": "https://www.walmart.com/"},
        {"label": "Target", "url": "https://www.target.com/"},
        {"label": "Amazon", "url": "https://www.amazon.com/"},
        {"label": "DoorDash", "url": "https://www.doordash.com/"},
    ]
