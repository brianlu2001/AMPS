"""
FastAPI dependency functions for authentication and role-based access control.

Usage in route handlers:

    # Require any authenticated user
    @router.get("/me")
    def me(current_user: User = Depends(get_current_user)):
        ...

    # Require a specific role
    @router.get("/admin/tasks")
    def admin_tasks(current_user: User = Depends(require_role(UserRole.ADMIN))):
        ...

    # Require one of several roles
    @router.get("/tasks")
    def tasks(current_user: User = Depends(require_any_role(UserRole.BUYER, UserRole.ADMIN))):
        ...

Design: two-tier access model.
  Tier 1 — Human app roles:  buyer, seller, admin
           control dashboard visibility and which routes respond.
  Tier 2 — Agent capabilities: buyer_agent, seller_agent, generalist, auditor
           control marketplace behavior (handled in agent layer, not here).

The `X-User-Id` header is accepted as a dev bypass when no Bearer token is
present — useful for curl/Postman testing without a full login flow.
Remove or gate behind a DEV_MODE flag before any production deployment.

Future: add OAuth2PasswordBearer for real token-based auth, remove X-User-Id bypass.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional, Callable

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..models.enums import UserRole
from ..models.user import User
from ..store import store
from .tokens import decode_token

# Optional bearer extractor — does not auto-raise 401 so we can handle fallback
_bearer = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Core dependency: resolve the calling user from JWT or dev header
# ---------------------------------------------------------------------------

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> User:
    """
    Resolve the authenticated user from the request.

    Resolution order:
      1. Bearer JWT in Authorization header  (production path)
      2. X-User-Id header                    (dev/demo bypass — remove in prod)

    Raises 401 if neither is present or valid.
    """
    # --- Path 1: JWT ---
    if credentials and credentials.credentials:
        try:
            payload = decode_token(credentials.credentials)
            user_id = payload.get("sub")
            user = store.get_user(user_id) if user_id else None
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token valid but user not found",
                )
            return user
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
            )

    # --- Path 2: Dev bypass via X-User-Id header ---
    # Future: gate this behind settings.dev_mode = True
    if x_user_id:
        user = store.get_user(x_user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Dev bypass: user {x_user_id} not found in store",
            )
        return user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide Authorization: Bearer <token> or X-User-Id header.",
    )


# ---------------------------------------------------------------------------
# Role guard factory
# ---------------------------------------------------------------------------

def require_role(*allowed_roles: UserRole) -> Callable[[User], User]:
    """
    Returns a FastAPI dependency that enforces the user has one of the
    specified roles. Raises 403 Forbidden otherwise.

    Usage:
        Depends(require_role(UserRole.ADMIN))
        Depends(require_role(UserRole.BUYER, UserRole.ADMIN))
    """
    allowed_set = {str(r) for r in allowed_roles}

    def _check(current_user: User = Depends(get_current_user)) -> User:
        if str(current_user.role) not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Access denied. Required role(s): {[str(r) for r in allowed_roles]}. "
                    f"Your role: {current_user.role}"
                ),
            )
        return current_user

    return _check


# ---------------------------------------------------------------------------
# Convenience aliases — used directly in route Depends()
# ---------------------------------------------------------------------------

# Any authenticated user
require_authenticated = get_current_user

# Human-facing app roles
require_buyer  = require_role(UserRole.BUYER)
require_seller = require_role(UserRole.SELLER)
require_admin  = require_role(UserRole.ADMIN)

# Admin can always act as buyer or seller for support purposes
require_buyer_or_admin  = require_role(UserRole.BUYER,  UserRole.ADMIN)
require_seller_or_admin = require_role(UserRole.SELLER, UserRole.ADMIN)

# Auditor-level access
require_auditor_or_admin = require_role(UserRole.AUDITOR, UserRole.ADMIN)
