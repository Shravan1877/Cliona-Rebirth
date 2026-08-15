"""Clerk JWKS validation + clerk_id -> internal UUID resolution.

Mechanism per CLAUDE.md §12.1, implemented literally:
  1. Read the Authorization: Bearer <token> header. Missing/malformed -> 401.
  2. Fetch + cache Clerk's JWKS from settings.CLERK_JWKS_URL (refresh on kid miss).
     Verify RS256 against the JWKS public key, checking issuer == settings.CLERK_JWT_ISSUER.
     settings.CLERK_SECRET_KEY is NOT a verification key and must never reach jwt.decode.
  3. Extract `sub` (the Clerk ID string) — never used directly as user_id.
  4. Upsert into users on clerk_id, RETURNING id, to resolve the internal UUID.
  5. Cache clerk_id -> UUID in-process.
"""

from typing import Optional

import httpx
from fastapi import Header, HTTPException
from jose import JWTError, jwt
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal


class JWKSCache:
    """In-memory cache for Clerk's JWKS, refreshed on kid miss."""

    def __init__(self) -> None:
        self._keys: dict[str, dict] = {}

    async def _refresh(self) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(settings.CLERK_JWKS_URL)
            response.raise_for_status()
        self._keys = {jwk["kid"]: jwk for jwk in response.json().get("keys", [])}

    async def get_key(self, kid: str) -> dict:
        if kid not in self._keys:
            await self._refresh()
        if kid not in self._keys:
            raise HTTPException(status_code=401, detail="Unknown signing key")
        return self._keys[kid]


_jwks_cache = JWKSCache()
_user_id_cache: dict[str, str] = {}  # clerk_id -> internal UUID, avoids a DB round trip per request


async def verify_token(token: str) -> dict:
    """Verify a Clerk RS256 JWT against the JWKS public key. Returns decoded claims."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Malformed token") from exc

    kid = header.get("kid")
    if not kid:
        raise HTTPException(status_code=401, detail="Malformed token")

    key = await _jwks_cache.get_key(kid)

    try:
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.CLERK_JWT_ISSUER,
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


async def resolve_user_id(
    clerk_id: str,
    email: Optional[str],
    name: Optional[str],
    avatar_url: Optional[str],
) -> str:
    """Upsert the users row by clerk_id and return the internal UUID."""
    if clerk_id in _user_id_cache:
        return _user_id_cache[clerk_id]

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                INSERT INTO users (clerk_id, email, name, avatar_url)
                VALUES (:clerk_id, :email, :name, :avatar_url)
                ON CONFLICT (clerk_id) DO UPDATE SET updated_at = NOW()
                RETURNING id
                """
            ),
            {"clerk_id": clerk_id, "email": email, "name": name, "avatar_url": avatar_url},
        )
        user_id = str(result.scalar_one())
        await session.commit()

    _user_id_cache[clerk_id] = user_id
    return user_id


async def get_current_user(authorization: str = Header(default=None)) -> str:
    """FastAPI dependency. Returns the resolved internal user UUID (never the Clerk sub)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    claims = await verify_token(token)

    clerk_id = claims.get("sub")
    if not clerk_id:
        raise HTTPException(status_code=401, detail="Token missing sub claim")

    email = claims.get("email") or claims.get("email_address")
    name = claims.get("name") or claims.get("full_name")
    avatar_url = claims.get("avatar_url") or claims.get("image_url") or claims.get("picture")

    return await resolve_user_id(clerk_id, email, name, avatar_url)
