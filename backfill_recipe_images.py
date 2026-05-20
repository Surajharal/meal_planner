#!/usr/bin/env python3
"""CLI: assign cover images to all recipes missing image_url."""
from models import Recipe, SessionLocal, init_db
from recipe_thumbnail_service import backfill_all_missing_thumbnails
from sqlalchemy import or_


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        missing = (
            db.query(Recipe)
            .filter(or_(Recipe.image_url.is_(None), Recipe.image_url == ""))
            .count()
        )
        if missing == 0:
            print("All recipes already have cover images.")
            return
        print(f"Assigning images for {missing} recipe(s)…")
        ok, fail = backfill_all_missing_thumbnails(db)
        remaining = (
            db.query(Recipe)
            .filter(or_(Recipe.image_url.is_(None), Recipe.image_url == ""))
            .count()
        )
        print(f"Updated {ok}, could not assign {fail}, still missing {remaining}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
