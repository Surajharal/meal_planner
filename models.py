from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Text,
    ForeignKey,
    Date,
    Boolean,
    DateTime,
    UniqueConstraint,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime, date
from config import Config

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    # Admin: env username. Standard users: username is normalized email for uniqueness.
    username = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    # Standard users sign up with email; admin account typically has email NULL
    email = Column(String(255), unique=True, nullable=True)
    # admin: user management | gyama: standard account (meal planner, AI diet, etc.)
    role = Column(String(20), nullable=False, default="gyama")


class SignupVerification(Base):
    """Pending email verification during self-service signup."""
    __tablename__ = "signup_verifications"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, index=True)
    otp_hash = Column(String(256), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AiDietPlan(Base):
    """Personal profile + AI-generated diet guidance (not medical advice)."""
    __tablename__ = "ai_diet_plans"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    weight_kg = Column(Float, nullable=False)
    height_cm = Column(Float, nullable=False)
    age = Column(Integer, nullable=False)
    sex = Column(String(24), nullable=False)
    goal = Column(String(32), nullable=False)
    activity_level = Column(String(32), nullable=False)
    dietary_restrictions = Column(Text)
    allergies = Column(Text)
    extra_notes = Column(Text)
    generated_plan = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="ai_diet_plans")


class UserRecipeFavorite(Base):
    """Per-user starred recipes. The recipe rows themselves are shared by everyone on this app."""

    __tablename__ = "user_recipe_favorites"
    __table_args__ = (UniqueConstraint("user_id", "recipe_id", name="uq_user_recipe_favorite"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id", ondelete="CASCADE"), nullable=False, index=True)


class Meal(Base):
    __tablename__ = 'meals'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day = Column(String(20), nullable=False)  # Monday, Tuesday, etc.
    meal_type = Column(String(20), nullable=False)  # Breakfast, Lunch, Dinner, Snack
    recipe_id = Column(Integer, ForeignKey('recipes.id'), nullable=True)
    servings = Column(Integer, default=4)
    week_start_date = Column(Date, nullable=False)
    
    user = relationship("User", backref="planned_meals")
    recipe = relationship("Recipe", back_populates="meals")

class Recipe(Base):
    __tablename__ = 'recipes'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    instructions = Column(Text, nullable=False)
    prep_time = Column(Integer, default=0)  # in minutes
    cook_time = Column(Integer, default=0)  # in minutes
    servings = Column(Integer, default=4)
    created_at = Column(Date, default=date.today)
    is_favorite = Column(Boolean, default=False)  # Legacy; use UserRecipeFavorite for per-user stars
    # Approximate totals for the full recipe as written (recipe.servings); from AI or manual
    calories_kcal = Column(Float, nullable=True)
    protein_g = Column(Float, nullable=True)
    carbs_g = Column(Float, nullable=True)
    fat_g = Column(Float, nullable=True)
    # Optional cover image (HTTPS URL); shown on recipe cards and detail page
    image_url = Column(String(512), nullable=True)

    user = relationship("User", backref="private_recipes")
    meals = relationship("Meal", back_populates="recipe")
    ingredients = relationship("RecipeIngredient", back_populates="recipe", cascade="all, delete-orphan")

class Ingredient(Base):
    __tablename__ = 'ingredients'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    category = Column(String(50), nullable=False)  # vegetables, spices, dairy, grains, etc.
    default_unit = Column(String(20), default='unit')  # kg, g, cup, tbsp, etc.
    
    recipe_ingredients = relationship("RecipeIngredient", back_populates="ingredient")
    inventory = relationship("Inventory", back_populates="ingredient", uselist=False)

class RecipeIngredient(Base):
    __tablename__ = 'recipe_ingredients'
    
    id = Column(Integer, primary_key=True)
    recipe_id = Column(Integer, ForeignKey('recipes.id'), nullable=False)
    ingredient_id = Column(Integer, ForeignKey('ingredients.id'), nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)
    
    recipe = relationship("Recipe", back_populates="ingredients")
    ingredient = relationship("Ingredient", back_populates="recipe_ingredients")

class Inventory(Base):
    __tablename__ = 'inventory'
    
    id = Column(Integer, primary_key=True)
    ingredient_id = Column(Integer, ForeignKey('ingredients.id'), nullable=False, unique=True)
    quantity = Column(Float, default=0.0)
    unit = Column(String(20), nullable=False)
    available = Column(Boolean, default=True)
    week_start_date = Column(Date, nullable=False)
    
    ingredient = relationship("Ingredient", back_populates="inventory")


class ManualShoppingItem(Base):
    __tablename__ = 'manual_shopping_items'

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    quantity = Column(Float, default=1.0)
    unit = Column(String(20), nullable=False)
    category = Column(String(50), nullable=False, default="other")
    week_start_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="manual_shopping_items")

# Database setup
database_url = Config.get_database_url()
engine = create_engine(database_url, echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    """Initialize the database with all tables"""
    Base.metadata.create_all(engine)
    # Run migration to add is_favorite if needed
    try:
        from migrate_db import (
            migrate_add_is_favorite,
            migrate_user_role_column,
            migrate_user_email_column,
            migrate_recipe_nutrition_columns,
            migrate_user_recipe_favorites_table,
            migrate_legacy_recipe_favorites_to_per_user,
            ensure_at_least_one_admin,
            migrate_alpha_to_gyama,
            migrate_drop_legacy_nutrition_tables,
            migrate_recipe_image_url_column,
            migrate_recipe_user_id_column,
        )
        migrate_add_is_favorite()
        migrate_user_role_column()
        migrate_user_email_column()
        migrate_recipe_nutrition_columns()
        migrate_user_recipe_favorites_table()
        migrate_legacy_recipe_favorites_to_per_user()
        migrate_alpha_to_gyama()
        migrate_drop_legacy_nutrition_tables()
        migrate_recipe_image_url_column()
        migrate_recipe_user_id_column()
        db = SessionLocal()
        try:
            ensure_at_least_one_admin(db)
            from starter_recipes import ensure_starter_recipes

            seeded = ensure_starter_recipes(db)
            if seeded:
                import logging

                logging.getLogger(__name__).info(
                    "Starter recipe library ready (%s recipes)", seeded
                )
        finally:
            db.close()
    except ImportError:
        # migrate_db might not be available, that's okay
        pass
    except Exception as e:
        # Log but don't fail - migration can be run manually
        import logging
        logging.warning(f"Auto-migration failed: {e}. Run migrate_db.py manually if needed.")

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
