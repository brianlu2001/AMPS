"""
Application configuration.

Uses environment variables with sensible MVP defaults.
Future: load from .env file via pydantic-settings BaseSettings.
"""

from __future__ import annotations

import os


class Settings:
    app_name: str = "AMPS — Agent Marketplace for Professional Services"
    app_version: str = "0.1.0-mvp"

    # API
    api_host: str = os.getenv("API_HOST", "0.0.0.0")
    api_port: int = int(os.getenv("API_PORT", "8000"))

    # CORS — allow frontend dev server
    # Future: lock down to specific origins in production
    cors_origins: list = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

    # Auth
    # Future: integrate JWT secret / Clerk publishable key here
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-in-production")

    # Quality threshold for audit pass/fail
    # Matches the constant in agents/auditor.py — keep in sync
    audit_quality_threshold: float = float(os.getenv("AUDIT_QUALITY_THRESHOLD", "0.70"))

    # Polling interval hint (seconds) — returned in API metadata for frontend
    polling_interval_seconds: int = int(os.getenv("POLLING_INTERVAL_SECONDS", "5"))


settings = Settings()
