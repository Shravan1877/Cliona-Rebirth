"""Live integration check against the real Clerk JWKS endpoint (§12.1/[A6]).

Unlike tests/test_auth.py (which monkeypatches JWKSCache._refresh to avoid a
network call), this test hits the real settings.CLERK_JWKS_URL through the
actual JWKSCache class. It proves:

  1. The real JWKS endpoint is reachable and returns the expected signing key.
  2. An unknown kid is rejected with 401 only after a real refresh attempt
     (the refresh-on-miss path actually executes against the live endpoint).
  3. A token whose header *claims* the real Clerk kid, but is signed by some
     other private key, is rejected — proving verification checks the actual
     RS256 signature against Clerk's real public key, not just the kid.

We cannot mint a genuinely Clerk-signed token here (that requires Clerk's
private key, which only Clerk holds), so this cannot exercise the full
happy path end-to-end. That requires a real signed-in user's session JWT —
see the note printed at the end of this file.
"""

import asyncio
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt
from fastapi import HTTPException

from app.core import auth
from app.core.config import settings


async def _check_real_jwks_reachable_and_key_returned() -> str:
    cache = auth.JWKSCache()
    await cache._refresh()
    assert cache._keys, "expected at least one signing key from the live JWKS endpoint"
    kid = next(iter(cache._keys))
    key = await cache.get_key(kid)
    assert key["kty"] == "RSA"
    assert key["alg"] == "RS256"
    print(f"live JWKS fetch OK -> kid={kid}, kty={key['kty']}, alg={key['alg']}")
    return kid


async def _check_unknown_kid_rejected_after_real_refresh() -> None:
    cache = auth.JWKSCache()
    try:
        await cache.get_key("definitely-not-a-real-kid")
        raise AssertionError("expected HTTPException for unknown kid")
    except HTTPException as exc:
        assert exc.status_code == 401
        print("unknown kid correctly rejected (401) after live refresh-on-miss")


async def _check_forged_signature_with_real_kid_is_rejected(real_kid: str) -> None:
    forger_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forger_pem = forger_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    claims = {
        "sub": "user_forged_identity",
        "iss": settings.CLERK_JWT_ISSUER,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    # header claims the REAL Clerk kid, but the signature is from an unrelated key
    forged_token = jwt.encode(claims, forger_pem, algorithm="RS256", headers={"kid": real_kid})

    try:
        await auth.get_current_user(authorization=f"Bearer {forged_token}")
        raise AssertionError("expected HTTPException: forged signature must not verify")
    except HTTPException as exc:
        assert exc.status_code == 401
        print("forged signature (real kid, wrong key) correctly rejected (401)")


async def _run_all() -> None:
    assert "clerk.accounts.dev" in settings.CLERK_JWKS_URL or settings.CLERK_JWKS_URL.startswith("https://")
    print(f"CLERK_JWKS_URL   = {settings.CLERK_JWKS_URL}")
    print(f"CLERK_JWT_ISSUER = {settings.CLERK_JWT_ISSUER}")

    real_kid = await _check_real_jwks_reachable_and_key_returned()
    await _check_unknown_kid_rejected_after_real_refresh()
    await _check_forged_signature_with_real_kid_is_rejected(real_kid)


@pytest.mark.integration
def test_live_clerk_jwks_integration() -> None:
    asyncio.run(_run_all())


if __name__ == "__main__":
    asyncio.run(_run_all())
    print("PASS")
    print()
    print("Note: this only exercises the rejection paths against the real endpoint —")
    print("a genuinely Clerk-signed token requires a real signed-in user's session JWT,")
    print("which only exists once the frontend is wired up and someone signs in.")
