"""
Token issuance and verification for AMPS MVP.

Implementation: signed JWT using HS256 with the SECRET_KEY from config.
No external auth provider required — tokens are self-contained.

Token payload:
  sub   : user_id (str)
  role  : UserRole value (str)
  email : user email (str)
  exp   : expiry timestamp

Design note: this is intentionally simple. The interface (issue_token,
decode_token) stays stable if you swap to Clerk, Auth0, or Cognito later —
only this module changes.

Future: add refresh tokens, token revocation list, scopes per endpoint.
"""

from __future__ import annotations

import time
from typing import Any, Dict

import jwt  # PyJWT

from ..config import settings
from ..models.enums import UserRole

# Token lifetime in seconds
ACCESS_TOKEN_TTL = 60 * 60 * 8  # 8 hours — sufficient for a dev/demo session

ALGORITHM = "HS256"


def issue_token(user_id: str, email: str, role: UserRole) -> str:
    """
    Create a signed JWT for the given user.

    Called after successful login. The token is returned to the client
    and must be sent as `Authorization: Bearer <token>` on every request.
    """
    payload: Dict[str, Any] = {
        "sub": user_id,
        "email": email,
        "role": str(role),
        "iat": int(time.time()),
        "exp": int(time.time()) + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """
    Verify and decode a JWT. Raises jwt.ExpiredSignatureError or
    jwt.InvalidTokenError if invalid.

    Returns the full payload dict on success.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
