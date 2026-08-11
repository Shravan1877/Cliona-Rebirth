"""Clerk JWKS validation + clerk_id -> internal UUID resolution.

Mechanism per CLAUDE.md §12.1 — implement literally in a later phase:
  1. Read the Authorization: Bearer <token> header. Missing/malformed -> 401.
  2. Fetch + cache Clerk's JWKS from settings.CLERK_JWKS_URL (refresh on kid miss).
     Verify RS256 against the JWKS public key, checking issuer == settings.CLERK_JWT_ISSUER.
     settings.CLERK_SECRET_KEY is NOT a verification key and must never reach jwt.decode.
  3. Extract `sub` (the Clerk ID string) — never used directly as user_id.
  4. Upsert into users on clerk_id, RETURNING id, to resolve the internal UUID.
  5. Cache clerk_id -> UUID in-process.
"""

from typing import Optional

from fastapi import Header
from jose import jwt  # python-jose[cryptography]


class JWKSCache:
    """In-memory cache for Clerk's JWKS, refreshed on kid miss."""

    def __init__(self) -> None:
        raise NotImplementedError("Phase 1")

    async def get_key(self, kid: str) -> dict:
        raise NotImplementedError("Phase 1")


async def verify_token(token: str) -> dict:
    """Verify a Clerk RS256 JWT against the JWKS public key. Returns decoded claims."""
    raise NotImplementedError("Phase 1")


async def resolve_user_id(
    clerk_id: str,
    email: Optional[str],
    name: Optional[str],
    avatar_url: Optional[str],
) -> str:
    """Upsert the users row by clerk_id and return the internal UUID."""
    raise NotImplementedError("Phase 1")


async def get_current_user(authorization: str = Header(...)) -> str:
    """FastAPI dependency. Returns the resolved internal user UUID (never the Clerk sub)."""
    raise NotImplementedError("Phase 1")
