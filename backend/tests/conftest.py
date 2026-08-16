"""Shared pytest fixtures.

Loop scope: pytest.ini sets asyncio_default_fixture_loop_scope=session and
asyncio_default_test_loop_scope=session. This is required, not cosmetic —
our app uses one module-level async SQLAlchemy engine
(app.datastore.session.engine), and asyncpg connections are bound to
whatever event loop was running when they were created. Without a shared
session-scoped loop, the second DB-touching test in a run fails with
"Event loop is closed" — the same failure mode Starlette's synchronous
TestClient hits (it spins up a fresh loop per request via a thread
portal), which is why API tests use httpx.AsyncClient + ASGITransport
instead.

Database: tests run against the same Postgres used for local dev (see
CLAUDE.md — real Postgres, not sqlite, since the schema uses jsonb and
native enums). API-level tests create real rows and don't clean them up;
fine for solo Phase 1 development, but worth knowing if the dev DB
accumulates test data.
"""
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
