import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()


def _normalize_login_email(value: str) -> str:
    return (value or "").strip().lower()


def _smtp_configured_from_env() -> bool:
    return bool(
        (os.getenv("SMTP_HOST") or "").strip() and (os.getenv("SMTP_FROM") or "").strip()
    )


def _is_production_env() -> bool:
    return (
        os.getenv("FLASK_ENV", "").strip().lower() == "production"
        or os.getenv("ENV", "").strip().lower() == "production"
    )


def _normalize_database_url(url: str) -> str:
    """Neon/Vercel often provide postgres://; SQLAlchemy expects postgresql://."""
    u = url.strip()
    if u.startswith("postgres://"):
        return "postgresql://" + u[len("postgres://") :]
    return u


def _database_url_from_env() -> str:
    return (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip()


def _resolve_trust_proxy() -> bool:
    raw = (os.getenv("TRUST_PROXY") or "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    # Vercel terminates TLS at the edge
    return os.getenv("VERCEL", "").strip() == "1"


def _resolve_print_otp_to_console() -> bool:
    """
    Console / on-page OTP (never used in production — forces real SMTP).
    Non-production:
    - PRINT_OTP_TO_CONSOLE true/false: honor explicitly.
    - unset + SMTP configured: False (send real email).
    - unset + no SMTP: True (dev convenience).
    """
    if _is_production_env():
        return False
    raw = (os.getenv("PRINT_OTP_TO_CONSOLE") or "").strip().lower()
    if raw == "true":
        return True
    if raw == "false":
        return False
    if _smtp_configured_from_env():
        return False

    return True


class Config:
    # API key from .env file
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

    # Neon / Vercel Postgres: single connection string (preferred on serverless)
    DATABASE_URL = _normalize_database_url(_database_url_from_env()) if _database_url_from_env() else ''

    # PostgreSQL database configuration (when DATABASE_URL is not set)
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'meal_planner')
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')

    # Use SQLite as fallback unless Postgres is configured
    USE_POSTGRES = (
        os.getenv('USE_POSTGRES', 'false').lower() == 'true' or bool(DATABASE_URL)
    )
    DATABASE_PATH = 'meal_planner.db'  # SQLite fallback
    
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-for-local-use')

    IS_PRODUCTION = _is_production_env()

    # HTTPS: set true behind TLS (default on when ENV/FLASK_ENV=production)
    _sec_raw = (os.getenv("SESSION_COOKIE_SECURE") or "").strip().lower()
    if _sec_raw == "true":
        SESSION_COOKIE_SECURE = True
    elif _sec_raw == "false":
        SESSION_COOKIE_SECURE = False
    else:
        SESSION_COOKIE_SECURE = IS_PRODUCTION

    # flask-limiter storage (memory:// single instance; redis://... for multiple workers)
    RATE_LIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATE_LIMIT_DEFAULT = os.getenv("RATELIMIT_DEFAULT", "400 per hour")

    # Admin login (always checked against .env — not the same as user email/password in DB)
    ADMIN_USERNAME = (os.getenv('ADMIN_USERNAME') or os.getenv('AUTH_USERNAME') or 'admin').strip()
    ADMIN_PASSWORD = (os.getenv('ADMIN_PASSWORD') or os.getenv('AUTH_PASSWORD') or '').strip()

    # Optional: sign in on the main /login form with this email + ADMIN_PASSWORD (same as env admin user)
    _admin_email_raw = (os.getenv('ADMIN_EMAIL') or os.getenv('AUTH_EMAIL') or '').strip()
    ADMIN_LOGIN_EMAIL = _normalize_login_email(_admin_email_raw) if _admin_email_raw else ''

    # Legacy aliases
    AUTH_USERNAME = ADMIN_USERNAME
    AUTH_PASSWORD = ADMIN_PASSWORD

    # SMTP for signup OTP (optional if PRINT_OTP_TO_CONSOLE=true for dev)
    SMTP_HOST = os.getenv('SMTP_HOST', '').strip()
    SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
    SMTP_USER = os.getenv('SMTP_USER', '').strip()
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_FROM = os.getenv('SMTP_FROM', '').strip()
    SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
    SMTP_USE_SSL = os.getenv('SMTP_USE_SSL', 'false').lower() == 'true'
    PRINT_OTP_TO_CONSOLE = _resolve_print_otp_to_console()

    # Set true when Flask sits behind nginx/Caddy/Vercel (HTTPS at the edge).
    TRUST_PROXY = _resolve_trust_proxy()

    # Optional: auto / batch stock food photos for recipes (https://www.pexels.com/api/)
    PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()

    # Strict signup: OTP only by email (no flash, no console/log). Default true.
    # Set SIGNUP_OTP_EMAIL_ONLY=false for local dev without SMTP (not for production).
    _signup_email_only = (os.getenv("SIGNUP_OTP_EMAIL_ONLY") or "true").strip().lower()
    SIGNUP_OTP_EMAIL_ONLY = _signup_email_only not in ("0", "false", "no", "off")

    try:
        DIET_APPLY_MAX_MEALS = max(1, min(28, int(os.getenv("DIET_APPLY_MAX_MEALS", "28"))))
    except (TypeError, ValueError):
        DIET_APPLY_MAX_MEALS = 28

    @staticmethod
    def smtp_configured() -> bool:
        return bool(Config.SMTP_HOST and Config.SMTP_FROM)
    
    @staticmethod
    def get_database_url():
        """Get the database connection URL"""
        if Config.USE_POSTGRES:
            if Config.DATABASE_URL:
                return Config.DATABASE_URL

            if not Config.DB_PASSWORD:
                raise ValueError(
                    "DB_PASSWORD is required when using PostgreSQL without DATABASE_URL"
                )

            # Validate that values don't contain @ which would break the connection string
            if '@' in Config.DB_USER or '@' in Config.DB_HOST:
                raise ValueError("DB_USER and DB_HOST cannot contain '@' character")

            # URL encode username and password to handle special characters
            encoded_user = quote_plus(Config.DB_USER)
            encoded_password = quote_plus(Config.DB_PASSWORD)
            encoded_host = Config.DB_HOST  # Host shouldn't need encoding typically
            encoded_db = quote_plus(Config.DB_NAME)

            connection_url = (
                f"postgresql://{encoded_user}:{encoded_password}@"
                f"{encoded_host}:{Config.DB_PORT}/{encoded_db}"
            )

            # Debug: print connection string without password (for troubleshooting)
            debug_url = (
                f"postgresql://{encoded_user}:***@{encoded_host}:"
                f"{Config.DB_PORT}/{encoded_db}"
            )
            print(f"Connecting to PostgreSQL: {debug_url}")

            return connection_url
        else:
            return f"sqlite:///{Config.DATABASE_PATH}"
    
    @staticmethod
    def validate():
        """Validate that required configuration is present"""
        if not Config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in .env file. Please add your Gemini API key to .env file.")
        
        if Config.USE_POSTGRES:
            if not Config.DATABASE_URL and not Config.DB_PASSWORD:
                raise ValueError(
                    "Set DATABASE_URL (Neon) or DB_PASSWORD when USE_POSTGRES=true"
                )

        return True
