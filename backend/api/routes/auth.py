"""
Auth API routes.

Endpoints:
  POST /auth/login   — Exchange email + password for a JWT access token
  GET  /auth/me      — Return the current user's identity and role
  GET  /auth/whoami  — Alias for /auth/me, useful for quick debugging

Design:
  Passwords are stored as plain strings for MVP (no bcrypt hashing yet).
  The login check is a simple equality comparison against the seeded demo users.

  This is intentionally minimal. The interface (email/password → token) is
  standard and compatible with any future upgrade path:
    - Add bcrypt hashing: only password_matches() changes
    - Add OAuth/Clerk: replace this route file entirely; deps.py stays the same
    - Add MFA: add a second factor check inside the login handler

Future: hash passwords with bcrypt, add rate limiting, add refresh token endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...auth.deps import get_current_user
from ...auth.tokens import issue_token
from ...models.user import User
from ...store import store

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    display_name: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """
    Authenticate with email + password and receive a JWT access token.

    MVP: passwords are stored in plain text on the User model (see seed_demo_users).
    Future: replace with bcrypt hash comparison.

    Demo credentials (seeded at startup):
      buyer@amps.dev     / buyer123
      seller1@amps.dev   / seller123
      seller2@amps.dev   / seller123
      generalist@amps.dev/ gen123
      auditor@amps.dev   / audit123
      admin@amps.dev     / admin123
    """
    user = store.get_user_by_email(req.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Password check — plain text for MVP
    # Future: bcrypt.checkpw(req.password.encode(), user.hashed_password)
    stored_password = getattr(user, "password", None)
    if stored_password != req.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    token = issue_token(user_id=user.id, email=user.email, role=user.role)
    store.log(
        event_type="user.login",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        actor_role=str(user.role),
        message=f"User logged in: {user.email} [{user.role}]",
    )

    return TokenResponse(
        access_token=token,
        user_id=user.id,
        role=str(user.role),
        display_name=user.display_name,
    )


@router.get("/me", response_model=Dict[str, Any])
def me(current_user: User = Depends(get_current_user)):
    """
    Return identity and role of the currently authenticated user.
    Also returns the linked profile ID (buyer_profile_id or seller_profile_id)
    so the frontend knows which scoped ID to use in subsequent requests.
    """
    response: Dict[str, Any] = {
        "user_id": current_user.id,
        "email": current_user.email,
        "display_name": current_user.display_name,
        "role": str(current_user.role),
        "is_active": current_user.is_active,
    }

    # Attach role-specific profile ID for convenience
    role = str(current_user.role)
    if role == "buyer":
        profile = next(
            (b for b in store.buyers.values() if b.user_id == current_user.id), None
        )
        response["buyer_profile_id"] = profile.id if profile else None

    elif role == "seller":
        profile = next(
            (s for s in store.sellers.values() if s.user_id == current_user.id), None
        )
        response["seller_profile_id"] = profile.id if profile else None

    return response


@router.get("/whoami", response_model=Dict[str, Any])
def whoami(current_user: User = Depends(get_current_user)):
    """Alias for /auth/me. Useful for quick debugging in curl / Postman."""
    return {
        "user_id": current_user.id,
        "email": current_user.email,
        "role": str(current_user.role),
        "display_name": current_user.display_name,
    }
