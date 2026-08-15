"""Minimal, real-DB verification of app.core.auth.get_current_user (§12.1/[A2]/[A6]).

Mints a self-signed RS256 JWT (no live Clerk instance needed) and feeds it
through the real get_current_user dependency, against the real `users`
table. Proves two things:

  1. A valid token resolves to an internal UUID, never the raw Clerk `sub`.
  2. Calling it a second time — with the in-process clerk_id -> UUID cache
     cleared, so the upsert SQL actually runs again — resolves to the SAME
     UUID and does not create a second row. That's the ON CONFLICT DO
     UPDATE branch firing, not just a first-time INSERT.

JWKS fetch is monkeypatched onto JWKSCache (no real Clerk network call);
everything downstream of it — RS256 verification, issuer check, the
upsert, the in-process cache — is exercised for real.
"""

import asyncio
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwk, jwt
from sqlalchemy import text

from app.core import auth
from app.core.config import settings
from app.core.database import AsyncSessionLocal


def _make_test_token(clerk_id: str) -> tuple[str, dict]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    jwk_dict = jwk.construct(public_pem, algorithm="RS256").to_dict()
    jwk_dict.update(kid="test-kid", use="sig", alg="RS256")

    claims = {
        "sub": clerk_id,
        "iss": settings.CLERK_JWT_ISSUER,
        "email": "test.user@example.com",
        "name": "Test User",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "test-kid"})
    return token, jwk_dict


async def _delete_test_row(clerk_id: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("DELETE FROM users WHERE clerk_id = :clerk_id"), {"clerk_id": clerk_id})
        await session.commit()


async def _run_upsert_then_lookup_check() -> None:
    clerk_id = f"user_test_{int(time.time())}_{id(object())}"
    token, jwk_dict = _make_test_token(clerk_id)

    async def fake_refresh(self) -> None:
        self._keys = {"test-kid": jwk_dict}

    auth.JWKSCache._refresh = fake_refresh
    auth._jwks_cache = auth.JWKSCache()
    auth._user_id_cache.clear()

    await _delete_test_row(clerk_id)  # clean slate in case of a leftover from a prior aborted run

    try:
        uid_1 = await auth.get_current_user(authorization=f"Bearer {token}")
        assert uid_1, "expected a non-empty internal UUID"
        assert uid_1 != clerk_id, "must never return the raw Clerk sub as the user id"

        auth._user_id_cache.clear()  # force the second call past the cache and back into the upsert SQL

        uid_2 = await auth.get_current_user(authorization=f"Bearer {token}")

        assert uid_1 == uid_2, "upsert-then-lookup must resolve to the SAME uuid, not insert a second row"

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT COUNT(*) FROM users WHERE clerk_id = :clerk_id"), {"clerk_id": clerk_id}
            )
            row_count = result.scalar_one()
        assert row_count == 1, f"expected exactly 1 row for clerk_id, found {row_count}"

        print(f"first call  -> internal UUID: {uid_1}")
        print(f"second call -> internal UUID: {uid_2}")
        print(f"rows in users for this clerk_id: {row_count}")
    finally:
        await _delete_test_row(clerk_id)


def test_get_current_user_resolves_stable_internal_uuid() -> None:
    asyncio.run(_run_upsert_then_lookup_check())


if __name__ == "__main__":
    asyncio.run(_run_upsert_then_lookup_check())
    print("PASS")
