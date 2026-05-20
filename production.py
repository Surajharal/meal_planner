"""Production helpers: health checks and security headers."""
from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify
from sqlalchemy import text

from config import Config
from models import SessionLocal

logger = logging.getLogger(__name__)


def register_production_routes(app: Flask) -> None:
    @app.get("/health")
    def health():
        """Liveness/readiness probe for Docker and load balancers."""
        checks: dict[str, Any] = {"app": "ok"}
        status_code = 200

        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            logger.warning("Health check database failed: %s", exc)
            checks["database"] = "error"
            status_code = 503
        finally:
            db.close()

        checks["gemini_configured"] = bool(Config.GEMINI_API_KEY)
        body = {"status": "ok" if status_code == 200 else "degraded", "checks": checks}
        return jsonify(body), status_code

    @app.after_request
    def security_headers(response):
        if Config.IS_PRODUCTION:
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            response.headers.setdefault(
                "Permissions-Policy",
                "geolocation=(), microphone=(), camera=()",
            )
        return response
