#!/usr/bin/env python3
"""One-off CLI: seed starter recipes if the library is empty."""
from models import SessionLocal, init_db
from models import Recipe
from recipe_thumbnail_service import backfill_all_missing_thumbnails
from sqlalchemy import or_
from starter_recipes import ensure_starter_recipes, starter_recipe_summary


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        n = ensure_starter_recipes(db)
        if n:
            print(f"Seeded {n} starter recipes.")
            for label, count in sorted(starter_recipe_summary().items()):
                print(f"  {label}: {count}")
        else:
            print("No recipes added (library already has recipes).")
        missing = (
            db.query(Recipe)
            .filter(or_(Recipe.image_url.is_(None), Recipe.image_url == ""))
            .count()
        )
        if missing:
            ok, fail = backfill_all_missing_thumbnails(db)
            print(f"Assigned images: {ok} updated, {fail} failed ({missing} were missing).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
