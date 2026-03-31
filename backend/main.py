"""
AMPS FastAPI application entrypoint.

Startup sequence:
  1. Create FastAPI app with metadata.
  2. Configure CORS.
  3. Seed the agent registry with mock agents.
  4. Seed demo users, profiles, and tasks.
  5. Register all API routers (auth, buyer, seller, audit, admin).
  6. Expose health check and metadata endpoints.

Run locally:
    uvicorn backend.main:app --reload --port 8000

Demo credentials (seeded at startup):
  buyer@amps.dev      / buyer123
  seller1@amps.dev    / seller123
  seller2@amps.dev    / seller123
  generalist@amps.dev / gen123
  auditor@amps.dev    / audit123
  admin@amps.dev      / admin123
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agents.registry import registry
from .api.routes import admin, audit, buyer, seller
from .api.routes import auth as auth_routes
from .config import settings
from .seed import seed_all, seed_marketplace_for_pending_tasks

# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Agent-to-agent marketplace for structured professional services. "
        "MVP — mock agent execution, in-memory store, polling-based observability.\n\n"
        "**Demo login:** POST /auth/login with {email, password}.\n"
        "Pass the returned token as `Authorization: Bearer <token>` or "
        "use `X-User-Id: <user_id>` for dev-only bypass."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Startup: seed agents + demo data
# ---------------------------------------------------------------------------

@app.on_event("startup")
def on_startup():
    """
    Startup sequence:
      1. seed_all()              — populate store with demo users, profiles, tasks
      2. registry.seed_mock_agents() — populate registry using the store profiles as source
                                      (ensures registry and store share the same objects)

    Order matters: store must be seeded before the registry reads from it.
    seed_all() is idempotent — safe on hot-reload.

    Future: replace with database-backed agent loading + Alembic migration seed.
    """
    seed_all()                          # 1. Populate store with users, profiles, tasks
    registry.seed_mock_agents()         # 2. Build registry agent instances
    seed_marketplace_for_pending_tasks()  # 3. Generate quotes for PENDING tasks


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

# Auth (no role guard — login is public)
app.include_router(auth_routes.router)

# Marketplace routes (role-guarded inside each file)
app.include_router(buyer.router)
app.include_router(seller.router)
app.include_router(audit.router)
app.include_router(admin.router)

# ---------------------------------------------------------------------------
# Health check + metadata (public)
# ---------------------------------------------------------------------------

@app.get("/", tags=["meta"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "polling_interval_seconds": settings.polling_interval_seconds,
        "demo_login": "POST /auth/login  {email, password}",
    }


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}


@app.get("/agents/summary", tags=["meta"])
def agents_summary():
    """
    Returns a summary of all registered agents.
    Useful for the observability console's agent status panel.
    Public endpoint — no auth required for marketplace transparency.
    """
    gen = registry.get_generalist()
    aud = registry.get_auditor()
    return {
        "sellers": [a.describe() for a in registry.list_sellers()],
        "generalist": gen.describe() if gen else None,
        "auditor": aud.describe() if aud else None,
    }
