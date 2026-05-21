# Meal Planner

A full-stack weekly meal planning app with AI recipe generation (Google Gemini), shared recipe library, per-user meal plans, inventory tracking, shopping lists, and personalized diet plans. Runs as a responsive web app with optional PWA install and Docker deployment.

**Default URL:** `http://localhost:5010` (port 5010 avoids macOS AirPlay conflicts on 5000).

---

## Features

### Weekly meal plan
- Calendar for Monday–Sunday with Breakfast, Lunch, Dinner, and Snack slots
- Week navigation, copy last week into empty slots
- Per-user meals; recipes are shared across all users
- Add meals via AI-generated recipes, existing recipes, or pantry-only AI

### Recipe library
- **80 starter recipes** (8 cuisines × 5 veg + 5 non-veg) seeded when the library is empty
- Search, filter by cuisine, diet (veg/non-veg), ingredient category, favorites
- Optional cover images via Pexels API or cuisine fallbacks
- Regenerate recipe with AI, stock thumbnail backfill

### AI (Gemini)
- Generate full recipes from a dish name
- Pantry-based recipe generation from weekly inventory
- Personalized **AI diet plan** (profile + goals) with apply-to-week (batched slot fill)
- Meal suggestions API

### Inventory & shopping
- Mark ingredients available for the current week
- Shopping list excludes what you already have; category grouping

### Accounts & security
- Email signup with OTP verification (SMTP)
- Roles: **gyama** (standard user), **admin** (user management)
- Admin login at `/login/admin` (credentials from `.env`)
- CSRF protection, rate limiting, secure session cookies (HTTPS/production)

### UX & production
- Design tokens, dark mode, mobile nav, PWA manifest
- Health check at `GET /health` for Docker
- Optional HTTPS via Caddy (`docker compose --profile https up`)

---

## Technology stack

| Layer | Technology |
|--------|------------|
| Backend | Python 3.13, Flask 3 |
| ORM | SQLAlchemy 2 |
| Database | PostgreSQL 16 (Docker) or SQLite (local dev) |
| AI | `google-generativeai` (Gemini) |
| Auth | Flask sessions, Werkzeug password hashing, email OTP |
| Security | Flask-WTF (CSRF), Flask-Limiter |
| Frontend | Jinja2 templates, vanilla CSS/JS |
| Deploy | Docker Compose, optional Caddy reverse proxy |

---

## Quick start (Docker — recommended)

### Prerequisites
- Docker & Docker Compose
- [Google Gemini API key](https://aistudio.google.com/apikey)
- Copy env template: `cp .env.docker.example .env` and fill in values

### Run

```bash
docker compose up --build
```

Open **http://localhost:5010**

- **PostgreSQL** service: `db` (credentials from `.env`, `DB_HOST` overridden to `db` in Compose)
- **Web** service: Flask on port `5010`

### HTTPS (optional)

```bash
docker compose --profile https up --build
```

In `.env` set `TRUST_PROXY=true` and `SESSION_COOKIE_SECURE=true`, then open **https://localhost** (self-signed cert via Caddy). See `Caddyfile` for production hostnames.

### Useful commands

```bash
# DB shell (default DB name/user from .env)
docker compose exec db psql -U meal_planer -d meal_planer

# Re-seed starter recipes (only if recipe table is empty; fast, no images)
docker compose exec web python seed_starter_recipes.py

# Optional: assign cover images later (needs PEXELS_API_KEY for search)
docker compose exec web python backfill_recipe_images.py
```

---

## Local development (without Docker)

```bash
cd "Meal Planner"
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # pytest
cp .env.docker.example .env           # edit GEMINI_API_KEY, etc.
```

**SQLite (simplest):** in `.env` set `USE_POSTGRES=false` (or omit PostgreSQL vars).

**PostgreSQL:** set `USE_POSTGRES=true` and connection vars, create the database, then:

```bash
python app.py
```

Tables and migrations run on startup via `init_db()` in `models.py`.

### Tests

```bash
USE_POSTGRES=false pytest tests/ -v
```

---

## Configuration

Copy `.env.docker.example` to `.env`. Never commit `.env`.

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | **Required** for AI features |
| `SECRET_KEY` | Flask session signing (long random string in production) |
| `USE_POSTGRES` | `true` for PostgreSQL, `false` for SQLite |
| `DATABASE_URL` | Full Postgres URL (Neon / Vercel); auto-enables Postgres |
| `DB_*` | PostgreSQL connection when `DATABASE_URL` is not set |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Admin account (`/login/admin`) |
| `SMTP_*` | Signup OTP email |
| `SIGNUP_OTP_EMAIL_ONLY` | `false` + `PRINT_OTP_TO_CONSOLE=true` for dev OTP on screen |
| `SESSION_COOKIE_SECURE` | `false` for phone testing over `http://LAN_IP:5010` |
| `TRUST_PROXY` | `true` behind Caddy/HTTPS |
| `PEXELS_API_KEY` | Optional recipe thumbnails |
| `DIET_APPLY_MAX_MEALS` | Max empty slots filled per diet apply (default `28`) |
| `ENV` / `FLASK_ENV` | `production` enables stricter cookies and security headers |

---

## Project structure

```
Meal Planner/
├── app.py                      # Flask app, core routes (plan, meals, recipes, inventory)
├── auth.py                     # Login, signup OTP, logout, change password
├── role_routes.py              # Admin users, AI diet plan routes
├── production.py               # /health, security headers
├── config.py                   # Env-based Config
├── extensions.py               # CSRF + rate limiter instances
├── models.py                   # SQLAlchemy models, init_db(), migrations hook
├── database.py                 # CRUD: recipes, meals, favorites, filters
├── meal_planner.py             # Weekly plan logic, AI apply diet to week
├── gemini_service.py           # Gemini prompts (recipes, diet, batched slots)
├── ingredient_manager.py       # Weekly inventory availability
├── shopping_list.py            # Aggregated shopping list
├── recipe_thumbnail_service.py # Pexels + cuisine fallback images
├── nutrition.py                # Macro scaling for meals/recipes
├── validators.py               # Input validation helpers
├── email_service.py            # SMTP OTP emails
├── rbac.py                     # Role constants (admin, gyama)
├── delivery_links.py           # Optional delivery URL helpers
│
├── starter_recipes.py          # 40 base starter recipes
├── starter_recipes_more.py     # 40 additional cuisines/recipes
├── seed_starter_recipes.py     # CLI: seed if library empty
├── backfill_recipe_images.py   # CLI: assign missing image_url
├── migrate_db.py               # Schema migrations (run manually if needed)
│
├── docker-compose.yml          # db + web (+ optional caddy profile)
├── Dockerfile                  # Python 3.13 slim image
├── Caddyfile                   # TLS reverse proxy config
├── requirements.txt            # Runtime dependencies
├── requirements-dev.txt        # pytest, etc.
│
├── templates/                  # Jinja2 HTML
│   ├── base.html               # App shell, navbar (brand | links | account)
│   ├── auth_base.html          # Login/signup layout
│   ├── _macros.html            # Shared template macros
│   ├── _diet_apply_fields.html # Diet → week form partial
│   ├── index.html              # Weekly calendar
│   ├── add_meal.html           # Generate / existing / pantry tabs
│   ├── meal_details.html
│   ├── recipe_details.html
│   ├── recipes.html
│   ├── inventory.html
│   ├── shopping_list.html
│   ├── login.html
│   ├── admin_login.html
│   ├── admin_users.html
│   ├── change_password.html
│   ├── ai_diet_plan.html
│   ├── ai_diet_detail.html
│   └── ai_diet_history.html
│
├── static/
│   ├── css/
│   │   ├── tokens.css          # Design variables
│   │   ├── style.css           # Components & pages
│   │   ├── layout.css          # Navbar, headers, responsive layout
│   │   └── theme-overrides.css # Dark mode
│   ├── js/
│   │   ├── main.js             # Nav, theme, favorites, CSRF helpers
│   │   ├── ai-loading.js       # Full-screen AI progress overlay
│   │   └── shopping-list.js    # Checkbox persistence
│   ├── icons/icon.svg
│   └── manifest.json           # PWA manifest
│
└── tests/
    ├── conftest.py
    ├── test_health.py
    ├── test_validators.py
    ├── test_starter_recipes.py
    ├── test_recipe_cuisine.py
    ├── test_recipe_thumbnails.py
    ├── test_add_meal_query.py
    └── test_diet_apply_week.py
```

### Module responsibilities

| Module | Role |
|--------|------|
| `app.py` | Registers blueprints/modules; weekly plan, meals, recipes, inventory, shopping, APIs |
| `auth.py` | Session auth, email OTP signup, admin vs user login |
| `role_routes.py` | `/admin/users`, `/ai-diet-plan/*` |
| `meal_planner.py` | `get_weekly_plan`, AI add meal, apply diet profile to empty slots |
| `database.py` | Low-level DB operations and recipe/meal queries |
| `gemini_service.py` | All Gemini API calls and JSON parsing |
| `starter_recipes*.py` | Catalog + `ensure_starter_recipes()` on empty DB |

---

## Database schema

| Table | Description |
|-------|-------------|
| `users` | Accounts (`username`, `email`, `password_hash`, `role`) |
| `signup_verifications` | Pending signup OTP hashes |
| `recipes` | Shared recipe catalog (macros, `image_url`, instructions) |
| `ingredients` | Master ingredient list with category |
| `recipe_ingredients` | Quantities per recipe |
| `meals` | User + week + day + meal_type → recipe + servings |
| `inventory` | Per-week ingredient availability |
| `user_recipe_favorites` | Per-user starred recipes |
| `ai_diet_plans` | Saved AI diet profiles and generated text |

Relationships: `meals.user_id` → `users`; `meals.recipe_id` → `recipes`; inventory keyed by `ingredient_id` and `week_start_date`.

---

## HTTP routes (overview)

### Public / auth
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/login` | User sign-in / signup tabs |
| GET/POST | `/login/admin` | Admin sign-in |
| POST | `/register/send-otp`, `/register/verify-otp`, `/register/complete` | Email signup |
| GET/POST | `/account/change-password` | Change password |
| GET | `/logout` | End session |
| GET | `/health` | Health probe (DB + config) |

### Meal plan & meals
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Weekly plan (`?week_start=YYYY-MM-DD`) |
| GET/POST | `/add_meal` | Add meal (generate / existing / pantry) |
| POST | `/add_meal_from_pantry` | Pantry AI flow |
| POST | `/add_existing_recipe` | Attach library recipe to slot |
| GET | `/meal/<id>` | Meal detail |
| POST | `/delete_meal/<id>` | Remove meal |
| POST | `/copy_week` | Copy previous week into empty slots |

### Recipes
| Method | Path | Description |
|--------|------|-------------|
| GET | `/recipes` | Library (search, cuisine, diet, favorites) |
| GET | `/recipe/<id>` | Recipe detail |
| POST | `/recipe/<id>/regenerate` | AI regenerate recipe |
| POST | `/recipe/<id>/image`, `/stock-thumbnail` | Set cover image |
| POST | `/recipes/backfill-thumbnails` | Batch thumbnails |
| POST | `/toggle_favorite/<id>` | Star recipe |
| GET | `/api/recipes`, `/api/pantry-ingredients` | JSON helpers |

### Inventory & shopping
| Method | Path | Description |
|--------|------|-------------|
| GET | `/inventory` | Weekly inventory UI |
| POST | `/update_inventory` | Update availability |
| GET | `/shopping_list` | Shopping list |

### AI diet & admin
| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/ai-diet-plan` | Create diet plan |
| GET | `/ai-diet-plan/history` | Past plans |
| GET | `/ai-diet-plan/<id>` | Plan detail + apply to week |
| POST | `/ai-diet-plan/<id>/apply-week` | Fill empty calendar slots |
| GET/POST | `/admin/users` | User management (admin) |

---

## Install on phone (PWA)

1. Serve the app over **HTTPS** (or use `SESSION_COOKIE_SECURE=false` for local `http://192.168.x.x:5010` testing).
2. Open the site in the phone browser.
3. **iOS Safari:** Share → **Add to Home Screen**.
4. **Android Chrome:** Menu → **Install app** / **Add to Home screen**.

See `static/manifest.json` for app name and standalone display mode.

---

## Deploy on Vercel (Neon PostgreSQL)

The app runs as a [Flask backend on Vercel](https://vercel.com/docs/frameworks/backend/flask). Static assets are copied to `public/static/` during the build (`scripts/sync_static.py`). Use **Neon** (or any hosted Postgres) — SQLite does not work on Vercel.

### 1. Neon database

1. Create a project at [neon.tech](https://neon.tech).
2. Copy the connection string (Dashboard → **Connect**). Prefer the string with `?sslmode=require`.
3. Run migrations once from your machine (replace the URL):

```bash
cd "Meal Planner"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql://USER:PASS@ep-xxx.region.aws.neon.tech/neondb?sslmode=require"
export GEMINI_API_KEY="your-gemini-key"

python migrate_db.py
python seed_starter_recipes.py   # optional; no cover images unless you pass --with-images
```

### 2. Vercel project

1. Push the repo to GitHub and import it at [vercel.com/new](https://vercel.com/new).
2. Framework: detected as Flask (`app.py`). Root directory: repo root.
3. Build command is set in `pyproject.toml` (`python scripts/sync_static.py`). Do not add `functions.app.py` to `vercel.json` (Flask is zero-config).

### 3. Environment variables (Production)

| Variable | Example / notes |
|----------|-----------------|
| `ENV` | `production` |
| `DATABASE_URL` | Neon connection string (`postgresql://...?sslmode=require`) |
| `GEMINI_API_KEY` | Required |
| `SECRET_KEY` | Long random string (`openssl rand -hex 32`) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Admin login at `/login/admin` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Signup OTP |
| `SMTP_USE_TLS` | `true` |
| `SIGNUP_OTP_EMAIL_ONLY` | `true` |

Optional: `PEXELS_API_KEY`, `ADMIN_EMAIL`, `RATELIMIT_STORAGE_URI` (Redis/Upstash at scale).

`TRUST_PROXY` defaults to **true** on Vercel (`VERCEL=1`). `USE_POSTGRES` is inferred when `DATABASE_URL` is set.

Do not commit `.env`; set values only in the Vercel dashboard.

### 4. Deploy

```bash
cd "Meal Planner"
npm i -g vercel
vercel login
vercel --prod
```

Or push to `main` for automatic deploys.

### 5. Verify

```bash
curl -sS "https://YOUR-PROJECT.vercel.app/health"
```

Open the site, test `/login/admin`, signup OTP, and one AI recipe. For longer AI runs, raise **Function Max Duration** in Vercel → Project → Settings → Functions (Flask does not use `api/` routes in `vercel.json`).

### Local Vercel preview

```bash
python scripts/sync_static.py
export DATABASE_URL="your-neon-url"
export GEMINI_API_KEY="your-key"
export ENV=production
vercel dev
```

---

## Troubleshooting

| Issue | What to try |
|-------|-------------|
| `GEMINI_API_KEY` errors | Set key in `.env`, restart containers |
| Signup OTP not received | Configure `SMTP_*`, or dev: `SIGNUP_OTP_EMAIL_ONLY=false` + `PRINT_OTP_TO_CONSOLE=true` |
| Login/signup fails on phone over HTTP | `SESSION_COOKIE_SECURE=false` in `.env` |
| Empty recipe library | `docker compose exec web python seed_starter_recipes.py` (only if no recipes exist) |
| Diet apply slow / partial week | Normal for many slots; use “Fill remaining”; check Gemini quota flashes |
| DB connection in Docker | Ensure `db` is healthy; `DB_HOST=db` is set in Compose for `web` |
| Vercel 500 / DB errors | Set `DATABASE_URL` to Neon URL with `sslmode=require`; run `migrate_db.py` once |
| Vercel missing CSS | Re-deploy (build runs `scripts/sync_static.py`); check `public/static/` exists after build |
| AI timeout on Vercel | Vercel → Settings → Functions → increase max duration; or reduce `DIET_APPLY_MAX_MEALS` |
| `unmatched-function-pattern` for `app.py` | Remove `vercel.json` `functions` block; ensure Vercel imports **`Surajharal/meal_planner`** (same repo you `git push` to) |

---

## License

Open source for personal use.

---

**Happy meal planning.**
