import importlib
import os

import pytest


def _reload_config(monkeypatch, **env):
    for key in (
        "DATABASE_URL",
        "POSTGRES_URL",
        "USE_POSTGRES",
        "DB_PASSWORD",
        "VERCEL",
        "TRUST_PROXY",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    import config

    importlib.reload(config)
    return config


def test_database_url_enables_postgres_and_normalizes_scheme(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        DATABASE_URL="postgres://user:secret@ep-neon.aws.neon.tech/neondb?sslmode=require",
        USE_POSTGRES="false",
    )
    assert cfg.Config.USE_POSTGRES is True
    url = cfg.Config.get_database_url()
    assert url.startswith("postgresql://")
    assert "ep-neon.aws.neon.tech" in url
    assert "sslmode=require" in url


def test_postgres_url_alias(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        POSTGRES_URL="postgresql://u:p@host/db",
        USE_POSTGRES="false",
    )
    assert cfg.Config.DATABASE_URL == "postgresql://u:p@host/db"


def test_trust_proxy_defaults_true_on_vercel(monkeypatch):
    cfg = _reload_config(monkeypatch, VERCEL="1")
    assert cfg.Config.TRUST_PROXY is True


def test_trust_proxy_explicit_false_overrides_vercel(monkeypatch):
    cfg = _reload_config(monkeypatch, VERCEL="1", TRUST_PROXY="false")
    assert cfg.Config.TRUST_PROXY is False


def test_validate_accepts_database_url_without_db_password(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        GEMINI_API_KEY="test-key",
        DATABASE_URL="postgresql://u:p@host/db",
    )
    cfg.Config.validate()


def test_validate_requires_password_without_database_url(monkeypatch):
    cfg = _reload_config(
        monkeypatch,
        GEMINI_API_KEY="test-key",
        USE_POSTGRES="true",
        DB_PASSWORD="",
    )
    with pytest.raises(ValueError, match="DATABASE_URL"):
        cfg.Config.validate()
