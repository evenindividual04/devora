"""Integration tests for DB-backed stores (analysis, oauth, oauth-state)."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.db.models import Base
from app.db.session import engine
from app.models.contracts import (
    AnalysisRecord,
    DataScope,
    HonestyMode,
    OutputTarget,
)


# ---------------------------------------------------------------------------
# DB reset (shared with test_api.py)
# ---------------------------------------------------------------------------

def _reset_db() -> None:
    async def _drop_create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_drop_create())


def _make_record(**kwargs) -> AnalysisRecord:
    defaults = dict(
        username="testuser",
        scope=DataScope.public,
        honesty_mode=HonestyMode.authentic,
        output_targets=[OutputTarget.readme],
        include_private=False,
    )
    defaults.update(kwargs)
    return AnalysisRecord(**defaults)


# ---------------------------------------------------------------------------
# AnalysisStore
# ---------------------------------------------------------------------------

class TestAnalysisStore:
    def setup_method(self):
        _reset_db()

    def test_create_and_get(self):
        from app.repositories.analysis_store import AnalysisStore

        async def run():
            store = AnalysisStore()
            record = _make_record()
            created = await store.create(record)
            fetched = await store.get(record.analysis_id)
            return created, fetched

        created, fetched = asyncio.run(run())
        assert fetched is not None
        assert fetched.analysis_id == created.analysis_id
        assert fetched.username == "testuser"

    def test_get_missing_returns_none(self):
        from app.repositories.analysis_store import AnalysisStore

        async def run():
            store = AnalysisStore()
            return await store.get(uuid4())

        assert asyncio.run(run()) is None

    def test_update_status(self):
        from app.repositories.analysis_store import AnalysisStore

        async def run():
            store = AnalysisStore()
            record = _make_record()
            await store.create(record)
            record.status = "completed"
            record.attempts = 1
            await store.update(record)
            return await store.get(record.analysis_id)

        fetched = asyncio.run(run())
        assert fetched.status == "completed"
        assert fetched.attempts == 1

    def test_update_missing_raises(self):
        from app.repositories.analysis_store import AnalysisStore

        async def run():
            store = AnalysisStore()
            record = _make_record()
            await store.update(record)

        with pytest.raises(ValueError, match="not found"):
            asyncio.run(run())

    def test_get_by_idempotency_key(self):
        from app.repositories.analysis_store import AnalysisStore

        async def run():
            store = AnalysisStore()
            idem_key = str(uuid4())
            record = _make_record(meta={"idempotency_key": idem_key})
            await store.create(record)
            return await store.get_by_idempotency_key(idem_key)

        fetched = asyncio.run(run())
        assert fetched is not None
        assert fetched.meta["idempotency_key"] is not None

    def test_get_by_idempotency_key_missing(self):
        from app.repositories.analysis_store import AnalysisStore

        async def run():
            store = AnalysisStore()
            return await store.get_by_idempotency_key("nonexistent-key")

        assert asyncio.run(run()) is None

    def test_list_failed_permanent(self):
        from app.repositories.analysis_store import AnalysisStore

        async def run():
            store = AnalysisStore()
            r1 = _make_record(username="alice")
            r2 = _make_record(username="bob")
            await store.create(r1)
            await store.create(r2)
            r1.status = "failed_permanent"
            r1.failure_reason = "timeout"
            await store.update(r1)
            return await store.list_failed_permanent()

        results = asyncio.run(run())
        assert len(results) == 1
        assert results[0]["username"] == "alice"
        assert results[0]["status"] == "failed_permanent"
        assert results[0]["failure_reason"] == "timeout"

    def test_list_failed_permanent_empty(self):
        from app.repositories.analysis_store import AnalysisStore

        async def run():
            store = AnalysisStore()
            return await store.list_failed_permanent()

        assert asyncio.run(run()) == []


# ---------------------------------------------------------------------------
# OAuthStore
# ---------------------------------------------------------------------------

class TestOAuthStore:
    def setup_method(self):
        _reset_db()

    def test_upsert_and_get_token(self):
        from app.repositories.oauth_store import OAuthStore

        async def run():
            store = OAuthStore()
            await store.upsert_token("alice", "tok123", "bearer", "repo")
            return await store.get_token("alice")

        token = asyncio.run(run())
        assert token == "tok123"

    def test_get_token_missing_returns_none(self):
        from app.repositories.oauth_store import OAuthStore

        async def run():
            store = OAuthStore()
            return await store.get_token("nobody")

        assert asyncio.run(run()) is None

    def test_upsert_updates_existing_token(self):
        from app.repositories.oauth_store import OAuthStore

        async def run():
            store = OAuthStore()
            await store.upsert_token("alice", "old-tok", "bearer", "repo")
            await store.upsert_token("alice", "new-tok", "bearer", "repo:write")
            return await store.get_token("alice"), await store.get_scope("alice")

        token, scope = asyncio.run(run())
        assert token == "new-tok"
        assert scope == "repo:write"

    def test_get_scope_returns_empty_for_missing(self):
        from app.repositories.oauth_store import OAuthStore

        async def run():
            store = OAuthStore()
            return await store.get_scope("nobody")

        assert asyncio.run(run()) == ""

    def test_get_scope_returns_stored_scope(self):
        from app.repositories.oauth_store import OAuthStore

        async def run():
            store = OAuthStore()
            await store.upsert_token("bob", "tok", "bearer", "read:user")
            return await store.get_scope("bob")

        assert asyncio.run(run()) == "read:user"


# ---------------------------------------------------------------------------
# OAuthStateStore
# ---------------------------------------------------------------------------

class TestOAuthStateStore:
    def setup_method(self):
        _reset_db()

    def test_create_and_consume_state(self):
        from app.repositories.oauth_state_store import OAuthStateStore

        async def run():
            store = OAuthStateStore()
            state = str(uuid4())
            await store.create_state(state, "alice", ttl_minutes=10)
            return await store.consume_state(state)

        username = asyncio.run(run())
        assert username == "alice"

    def test_consume_state_deleted_after_use(self):
        from app.repositories.oauth_state_store import OAuthStateStore

        async def run():
            store = OAuthStateStore()
            state = str(uuid4())
            await store.create_state(state, "alice", ttl_minutes=10)
            await store.consume_state(state)
            return await store.consume_state(state)

        assert asyncio.run(run()) is None

    def test_consume_missing_state_returns_none(self):
        from app.repositories.oauth_state_store import OAuthStateStore

        async def run():
            store = OAuthStateStore()
            return await store.consume_state("does-not-exist")

        assert asyncio.run(run()) is None

    def test_consume_expired_state_returns_none(self):
        from app.repositories.oauth_state_store import OAuthStateStore
        from app.db.models import OAuthStateORM
        from app.db.session import SessionLocal

        async def run():
            store = OAuthStateStore()
            state = str(uuid4())
            now = datetime.now(UTC)
            # Insert a state that is already expired
            async with SessionLocal() as session:
                session.add(OAuthStateORM(
                    state=state,
                    username="alice",
                    created_at=now - timedelta(minutes=20),
                    expires_at=now - timedelta(minutes=10),
                ))
                await session.commit()
            return await store.consume_state(state)

        assert asyncio.run(run()) is None
