#!/usr/bin/env python3
"""One-off CLI: seed starter recipes if the library is empty (no cover images by default)."""
import argparse

from models import SessionLocal, init_db
from starter_recipes import ensure_starter_recipes, starter_recipe_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed starter recipes when the library is empty.")
    parser.add_argument(
        "--with-images",
        action="store_true",
        help="Assign Pexels/cuisine cover images during seed (slow; needs PEXELS_API_KEY for search).",
    )
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        n = ensure_starter_recipes(db, assign_thumbnails=args.with_images)
        if n:
            print(f"Seeded {n} starter recipes.")
            for label, count in sorted(starter_recipe_summary().items()):
                print(f"  {label}: {count}")
            if not args.with_images:
                print("Cover images skipped. Later: python backfill_recipe_images.py")
        else:
            print("No recipes added (library already has recipes).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
