"""
Database migration script to add is_favorite column to recipes table
Run this script to update your database schema
"""
from sqlalchemy import text, inspect
from models import engine, Recipe, Base, User
from config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_add_is_favorite():
    """Add is_favorite column to recipes table if it doesn't exist"""
    try:
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('recipes')]
        
        if 'is_favorite' in columns:
            logger.info("Column 'is_favorite' already exists in recipes table")
            return True
        
        logger.info("Adding 'is_favorite' column to recipes table...")
        
        with engine.begin() as conn:  # Use begin() for automatic transaction management
            # Check if using PostgreSQL or SQLite
            if Config.USE_POSTGRES:
                # PostgreSQL - check if column exists first
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='recipes' AND column_name='is_favorite'
                """))
                if result.fetchone():
                    logger.info("Column already exists (checked via information_schema)")
                    return True
                
                # Add column for PostgreSQL
                conn.execute(text("ALTER TABLE recipes ADD COLUMN is_favorite BOOLEAN DEFAULT FALSE"))
                logger.info("Successfully added 'is_favorite' column to PostgreSQL")
            else:
                # SQLite
                try:
                    conn.execute(text("ALTER TABLE recipes ADD COLUMN is_favorite BOOLEAN DEFAULT 0"))
                    logger.info("Successfully added 'is_favorite' column to SQLite")
                except Exception as sqlite_error:
                    # SQLite might not support ALTER TABLE in older versions
                    logger.warning(f"SQLite ALTER TABLE failed: {sqlite_error}")
                    logger.info("Trying to recreate table...")
                    # For SQLite, we might need to recreate, but that's risky with data
                    # Just log the issue
                    raise
        
        return True
    except Exception as e:
        logger.error(f"Error adding column: {str(e)}")
        # Check if column was actually added (race condition)
        try:
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('recipes')]
            if 'is_favorite' in columns:
                logger.info("Column exists after all - migration successful")
                return True
        except:
            pass
        return False


def migrate_user_role_column():
    """Add users.role (admin | gyama) when missing."""
    try:
        inspector = inspect(engine)
        if not inspector.has_table("users"):
            return True
        columns = [c["name"] for c in inspector.get_columns("users")]
        if "role" in columns:
            logger.info("Column 'role' already exists on users")
            return True
        logger.info("Adding 'role' column to users...")
        with engine.begin() as conn:
            if Config.USE_POSTGRES:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'gyama'"
                    )
                )
            else:
                conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'gyama'"))
                conn.execute(text("UPDATE users SET role = 'gyama' WHERE role IS NULL"))
        logger.info("Added users.role")
        return True
    except Exception as e:
        logger.error("migrate_user_role_column: %s", e)
        return False


def migrate_recipe_image_url_column():
    """Add recipes.image_url for optional thumbnail (HTTPS URL)."""
    try:
        inspector = inspect(engine)
        if not inspector.has_table("recipes"):
            return True
        columns = {c["name"] for c in inspector.get_columns("recipes")}
        if "image_url" in columns:
            logger.info("Column recipes.image_url already exists")
            return True
        with engine.begin() as conn:
            col_type = "VARCHAR(512)" if Config.USE_POSTGRES else "VARCHAR(512)"
            conn.execute(text(f"ALTER TABLE recipes ADD COLUMN image_url {col_type} NULL"))
        logger.info("Added recipes.image_url")
        return True
    except Exception as e:
        logger.error("migrate_recipe_image_url_column: %s", e)
        return False


def migrate_recipe_user_id_column():
    """Add recipes.user_id for private per-user regenerated recipes."""
    try:
        inspector = inspect(engine)
        if not inspector.has_table("recipes"):
            return True
        columns = {c["name"] for c in inspector.get_columns("recipes")}
        if "user_id" in columns:
            logger.info("Column recipes.user_id already exists")
            return True
        with engine.begin() as conn:
            col_type = "INTEGER"
            conn.execute(text(f"ALTER TABLE recipes ADD COLUMN user_id {col_type} NULL"))
            if Config.USE_POSTGRES:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_recipes_user_id ON recipes (user_id)"))
            else:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_recipes_user_id ON recipes (user_id)"))
        logger.info("Added recipes.user_id")
        return True
    except Exception as e:
        logger.error("migrate_recipe_user_id_column: %s", e)
        return False


def migrate_recipe_nutrition_columns():
    """Add optional nutrition columns to recipes (AI estimates, totals for full batch)."""
    try:
        inspector = inspect(engine)
        if not inspector.has_table("recipes"):
            return True
        columns = {c["name"] for c in inspector.get_columns("recipes")}
        with engine.begin() as conn:
            specs = [
                ("calories_kcal", "DOUBLE PRECISION" if Config.USE_POSTGRES else "REAL"),
                ("protein_g", "DOUBLE PRECISION" if Config.USE_POSTGRES else "REAL"),
                ("carbs_g", "DOUBLE PRECISION" if Config.USE_POSTGRES else "REAL"),
                ("fat_g", "DOUBLE PRECISION" if Config.USE_POSTGRES else "REAL"),
            ]
            for col_name, col_type in specs:
                if col_name not in columns:
                    conn.execute(
                        text(f"ALTER TABLE recipes ADD COLUMN {col_name} {col_type} NULL")
                    )
                    logger.info("Added recipes.%s", col_name)
        return True
    except Exception as e:
        logger.error("migrate_recipe_nutrition_columns: %s", e)
        return False


def migrate_user_email_column():
    """Add users.email for email-based accounts; widen username for email-as-login on PostgreSQL."""
    try:
        inspector = inspect(engine)
        if not inspector.has_table("users"):
            return True
        columns = {c["name"] for c in inspector.get_columns("users")}
        with engine.begin() as conn:
            if "email" not in columns:
                if Config.USE_POSTGRES:
                    conn.execute(
                        text(
                            "ALTER TABLE users ADD COLUMN email VARCHAR(255) NULL UNIQUE"
                        )
                    )
                else:
                    conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255)"))
                logger.info("Added users.email")
            if Config.USE_POSTGRES:
                try:
                    conn.execute(
                        text("ALTER TABLE users ALTER COLUMN username TYPE VARCHAR(255)")
                    )
                except Exception as ex:
                    logger.debug("username widen (may already be ok): %s", ex)
        return True
    except Exception as e:
        logger.error("migrate_user_email_column: %s", e)
        return False


def migrate_alpha_to_gyama():
    """Former 'alpha' nutritionist accounts become standard gyama users."""
    try:
        inspector = inspect(engine)
        if not inspector.has_table("users"):
            return True
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET role = 'gyama' WHERE role = 'alpha'"))
        logger.info("Updated alpha users to gyama where applicable")
        return True
    except Exception as e:
        logger.warning("migrate_alpha_to_gyama: %s", e)
        return False


def migrate_drop_legacy_nutrition_tables():
    """Remove human-nutritionist connection tables (replaced by AI diet plans)."""
    try:
        inspector = inspect(engine)
        with engine.begin() as conn:
            if Config.USE_POSTGRES:
                if inspector.has_table("diet_plans"):
                    conn.execute(text("DROP TABLE IF EXISTS diet_plans CASCADE"))
                if inspector.has_table("nutrition_connections"):
                    conn.execute(text("DROP TABLE IF EXISTS nutrition_connections CASCADE"))
            else:
                if inspector.has_table("diet_plans"):
                    conn.execute(text("DROP TABLE IF EXISTS diet_plans"))
                if inspector.has_table("nutrition_connections"):
                    conn.execute(text("DROP TABLE IF EXISTS nutrition_connections"))
        return True
    except Exception as e:
        logger.warning("migrate_drop_legacy_nutrition_tables: %s", e)
        return False


def migrate_user_recipe_favorites_table():
    """Create per-user recipe favorites (shared recipe library, private stars)."""
    try:
        from models import UserRecipeFavorite

        inspector = inspect(engine)
        if inspector.has_table("user_recipe_favorites"):
            logger.info("Table user_recipe_favorites already exists")
            return True
        UserRecipeFavorite.__table__.create(bind=engine)
        logger.info("Created user_recipe_favorites table")
        return True
    except Exception as e:
        logger.error("migrate_user_recipe_favorites_table: %s", e)
        return False


def migrate_legacy_recipe_favorites_to_per_user():
    """One-time: copy global recipes.is_favorite into user_recipe_favorites for every user."""
    try:
        from models import SessionLocal, User, Recipe, UserRecipeFavorite

        db = SessionLocal()
        try:
            if db.query(UserRecipeFavorite).count() > 0:
                return True
            legacy_ids = [
                r.id
                for r in db.query(Recipe).filter(Recipe.is_favorite.is_(True)).all()
            ]
            if not legacy_ids:
                return True
            uids = [u.id for u in db.query(User).all()]
            for uid in uids:
                for rid in legacy_ids:
                    db.add(UserRecipeFavorite(user_id=uid, recipe_id=rid))
            db.commit()
            logger.info(
                "Seeded per-user favorites from legacy recipe.is_favorite (%s recipes)",
                len(legacy_ids),
            )
            return True
        finally:
            db.close()
    except Exception as e:
        logger.warning("migrate_legacy_recipe_favorites_to_per_user: %s", e)
        return False


def ensure_at_least_one_admin(db_session):
    """If no admin exists, promote the oldest user (e.g. after adding role column)."""
    try:
        admins = db_session.query(User).filter(User.role == "admin").count()
        if admins > 0:
            return
        first = db_session.query(User).order_by(User.id).first()
        if first:
            first.role = "admin"
            db_session.commit()
            logger.info("Promoted user id=%s to admin (no admin was present)", first.id)
    except Exception as e:
        logger.warning("ensure_at_least_one_admin: %s", e)
        db_session.rollback()


if __name__ == '__main__':
    print("=" * 50)
    print("Database Migration: Adding is_favorite column")
    print("=" * 50)
    
    try:
        from config import Config
        Config.validate()
    except ValueError as e:
        print(f"Configuration Error: {e}")
        exit(1)
    
    success = migrate_add_is_favorite()
    
    if success:
        print("\n✅ Migration completed successfully!")
        print("You can now use the favorites feature.")
    else:
        print("\n❌ Migration failed. Please check the error messages above.")
        print("You may need to manually add the column or recreate the database.")
        exit(1)
