"""Session-scoped async fixture infrastructure (test-only; no production code touched).

Pairs with pyproject.toml's asyncio_default_test_loop_scope = "session": all
async tests in this session run on one shared event loop, so the module-level
`engine` in app/core/database.py — created once at import time, before any
loop exists — only ever binds its asyncpg connection pool to that one loop.
Running two or more DB-touching tests in the same pytest process previously
each got their own asyncio.run() loop, and the pool from the first became
invalid ("attached to a different loop") once a second test tried to reuse it.

This fixture just disposes that shared engine cleanly once, after the whole
session's tests are done, so no connections leak past the loop closing.
"""

import pytest_asyncio

from app.core.database import engine


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def _dispose_shared_engine_at_session_end():
    yield
    await engine.dispose()
