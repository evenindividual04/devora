"""Direct asyncio.run() tests for stores not yet covered: user, session, owner, share."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.db.models import Base
from app.db.session import engine


def _reset_db() -> None:
    async def _drop_create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(_drop_create())


# ---------------------------------------------------------------------------
# UserStore
# ---------------------------------------------------------------------------

class TestUserStore:
    def setup_method(self):
        _reset_db()

    def test_create_and_get_by_email(self):
        from app.repositories.user_store import UserStore
        async def run():
            store = UserStore()
            user = await store.create("alice@example.com", "hashed", role="user")
            assert user.user_id
            assert user.email == "alice@example.com"
            fetched = await store.get_by_email("alice@example.com")
            assert fetched is not None
            assert fetched.user_id == user.user_id
        asyncio.run(run())

    def test_get_by_email_missing(self):
        from app.repositories.user_store import UserStore
        async def run():
            store = UserStore()
            return await store.get_by_email("nobody@example.com")
        assert asyncio.run(run()) is None

    def test_get_by_id(self):
        from app.repositories.user_store import UserStore
        async def run():
            store = UserStore()
            user = await store.create("bob@example.com", "hash", role="admin")
            return await store.get_by_id(user.user_id)
        fetched = asyncio.run(run())
        assert fetched is not None
        assert fetched.role == "admin"

    def test_get_by_id_missing(self):
        from app.repositories.user_store import UserStore
        async def run():
            store = UserStore()
            return await store.get_by_id(str(uuid4()))
        assert asyncio.run(run()) is None


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------

class TestSessionStore:
    def setup_method(self):
        _reset_db()

    def _create_user(self) -> str:
        from app.repositories.user_store import UserStore
        async def run():
            store = UserStore()
            user = await store.create(f"u{uuid4().hex[:6]}@x.com", "hash")
            return user.user_id
        return asyncio.run(run())

    def test_create_and_get_by_jti(self):
        from app.repositories.session_store import SessionStore
        user_id = self._create_user()
        async def run():
            store = SessionStore()
            jti = uuid4().hex
            exp = datetime.now(UTC) + timedelta(hours=1)
            row = await store.create(user_id, jti, exp)
            assert row.refresh_jti == jti
            fetched = await store.get_by_jti(jti)
            assert fetched is not None
            assert fetched.user_id == user_id
        asyncio.run(run())

    def test_get_by_jti_missing(self):
        from app.repositories.session_store import SessionStore
        async def run():
            store = SessionStore()
            return await store.get_by_jti("nonexistent")
        assert asyncio.run(run()) is None

    def test_revoke(self):
        from app.repositories.session_store import SessionStore
        user_id = self._create_user()
        async def run():
            store = SessionStore()
            jti = uuid4().hex
            await store.create(user_id, jti, datetime.now(UTC) + timedelta(hours=1))
            await store.revoke(jti)
            row = await store.get_by_jti(jti)
            assert row.revoked is True
        asyncio.run(run())

    def test_revoke_missing_is_noop(self):
        from app.repositories.session_store import SessionStore
        async def run():
            store = SessionStore()
            await store.revoke("does-not-exist")  # should not raise
        asyncio.run(run())

    def test_is_active_true(self):
        from app.repositories.session_store import SessionStore
        user_id = self._create_user()
        async def run():
            store = SessionStore()
            jti = uuid4().hex
            await store.create(user_id, jti, datetime.now(UTC) + timedelta(hours=1))
            return await store.is_active(jti)
        assert asyncio.run(run()) is True

    def test_is_active_missing_jti(self):
        from app.repositories.session_store import SessionStore
        async def run():
            store = SessionStore()
            return await store.is_active("no-such-jti")
        assert asyncio.run(run()) is False

    def test_is_active_revoked(self):
        from app.repositories.session_store import SessionStore
        user_id = self._create_user()
        async def run():
            store = SessionStore()
            jti = uuid4().hex
            await store.create(user_id, jti, datetime.now(UTC) + timedelta(hours=1))
            await store.revoke(jti)
            return await store.is_active(jti)
        assert asyncio.run(run()) is False

    def test_is_active_expired(self):
        from app.repositories.session_store import SessionStore
        from app.db.models import SessionORM
        from app.db.session import SessionLocal
        user_id = self._create_user()
        async def run():
            store = SessionStore()
            jti = uuid4().hex
            now = datetime.now(UTC)
            async with SessionLocal() as session:
                session.add(SessionORM(
                    user_id=user_id,
                    refresh_jti=jti,
                    expires_at=now - timedelta(hours=1),
                    revoked=False,
                    created_at=now,
                ))
                await session.commit()
            return await store.is_active(jti)
        assert asyncio.run(run()) is False


# ---------------------------------------------------------------------------
# OwnerStore
# ---------------------------------------------------------------------------

class TestOwnerStore:
    def setup_method(self):
        _reset_db()

    def _create_user(self) -> str:
        from app.repositories.user_store import UserStore
        async def run():
            store = UserStore()
            user = await store.create(f"u{uuid4().hex[:6]}@x.com", "hash")
            return user.user_id
        return asyncio.run(run())

    def _create_analysis(self) -> str:
        from app.repositories.analysis_store import AnalysisStore
        from app.models.contracts import AnalysisRecord, DataScope, HonestyMode, OutputTarget
        async def run():
            store = AnalysisStore()
            r = AnalysisRecord(
                username="testuser",
                scope=DataScope.public,
                honesty_mode=HonestyMode.authentic,
                output_targets=[OutputTarget.readme],
                include_private=False,
            )
            await store.create(r)
            return str(r.analysis_id)
        return asyncio.run(run())

    def test_bind_and_owns_analysis(self):
        from app.repositories.owner_store import OwnerStore
        user_id = self._create_user()
        analysis_id = self._create_analysis()
        async def run():
            store = OwnerStore()
            await store.bind_analysis(analysis_id, user_id)
            return await store.owns_analysis(analysis_id, user_id)
        assert asyncio.run(run()) is True

    def test_owns_analysis_false(self):
        from app.repositories.owner_store import OwnerStore
        analysis_id = self._create_analysis()
        async def run():
            store = OwnerStore()
            return await store.owns_analysis(analysis_id, str(uuid4()))
        assert asyncio.run(run()) is False

    def test_list_analysis_ids(self):
        from app.repositories.owner_store import OwnerStore
        user_id = self._create_user()
        a1 = self._create_analysis()
        a2 = self._create_analysis()
        async def run():
            store = OwnerStore()
            await store.bind_analysis(a1, user_id)
            await store.bind_analysis(a2, user_id)
            return await store.list_analysis_ids(user_id)
        ids = asyncio.run(run())
        assert set(ids) == {a1, a2}

    def test_list_analysis_ids_empty(self):
        from app.repositories.owner_store import OwnerStore
        async def run():
            store = OwnerStore()
            return await store.list_analysis_ids(str(uuid4()))
        assert asyncio.run(run()) == []

    def test_bind_share_and_owns_share(self):
        from app.repositories.owner_store import OwnerStore
        user_id = self._create_user()
        token_id = uuid4().hex
        async def run():
            store = OwnerStore()
            await store.bind_share(token_id, user_id)
            return await store.owns_share(token_id, user_id)
        assert asyncio.run(run()) is True

    def test_owns_share_false(self):
        from app.repositories.owner_store import OwnerStore
        async def run():
            store = OwnerStore()
            return await store.owns_share("nosuch-token", str(uuid4()))
        assert asyncio.run(run()) is False

    def test_list_share_token_ids(self):
        from app.repositories.owner_store import OwnerStore
        user_id = self._create_user()
        t1, t2 = uuid4().hex, uuid4().hex
        async def run():
            store = OwnerStore()
            await store.bind_share(t1, user_id)
            await store.bind_share(t2, user_id)
            return await store.list_share_token_ids(user_id)
        ids = asyncio.run(run())
        assert set(ids) == {t1, t2}


# ---------------------------------------------------------------------------
# ShareStore
# ---------------------------------------------------------------------------

class TestShareStore:
    def setup_method(self):
        _reset_db()

    def _future(self, minutes: int = 60) -> datetime:
        return datetime.now(UTC) + timedelta(minutes=minutes)

    def test_create_and_get(self):
        from app.repositories.share_store import ShareStore
        async def run():
            store = ShareStore()
            tid = uuid4().hex
            await store.create(tid, "analysis-123", self._future())
            row = await store.get(tid)
            assert row is not None
            assert row.token_id == tid
        asyncio.run(run())

    def test_get_missing(self):
        from app.repositories.share_store import ShareStore
        async def run():
            store = ShareStore()
            return await store.get("nosuch")
        assert asyncio.run(run()) is None

    def test_revoke_existing(self):
        from app.repositories.share_store import ShareStore
        async def run():
            store = ShareStore()
            tid = uuid4().hex
            await store.create(tid, "analysis-123", self._future())
            result = await store.revoke(tid)
            assert result is True
            row = await store.get(tid)
            assert row.revoked is True
        asyncio.run(run())

    def test_revoke_missing(self):
        from app.repositories.share_store import ShareStore
        async def run():
            store = ShareStore()
            return await store.revoke("nosuch-token")
        assert asyncio.run(run()) is False

    def test_is_valid_true(self):
        from app.repositories.share_store import ShareStore
        async def run():
            store = ShareStore()
            tid = uuid4().hex
            await store.create(tid, "analysis-123", self._future())
            return await store.is_valid(tid)
        assert asyncio.run(run()) is True

    def test_is_valid_missing(self):
        from app.repositories.share_store import ShareStore
        async def run():
            store = ShareStore()
            return await store.is_valid("nosuch")
        assert asyncio.run(run()) is False

    def test_is_valid_revoked(self):
        from app.repositories.share_store import ShareStore
        async def run():
            store = ShareStore()
            tid = uuid4().hex
            await store.create(tid, "analysis-123", self._future())
            await store.revoke(tid)
            return await store.is_valid(tid)
        assert asyncio.run(run()) is False

    def test_is_valid_expired(self):
        from app.repositories.share_store import ShareStore
        from app.db.models import ShareORM
        from app.db.session import SessionLocal
        async def run():
            store = ShareStore()
            tid = uuid4().hex
            now = datetime.now(UTC)
            async with SessionLocal() as session:
                session.add(ShareORM(
                    token_id=tid,
                    analysis_id="aid",
                    token_version=1,
                    expires_at=now - timedelta(hours=1),
                    revoked=False,
                    created_at=now,
                ))
                await session.commit()
            return await store.is_valid(tid)
        assert asyncio.run(run()) is False

    def test_list_by_token_ids_empty(self):
        from app.repositories.share_store import ShareStore
        async def run():
            store = ShareStore()
            return await store.list_by_token_ids([])
        assert asyncio.run(run()) == []

    def test_list_by_token_ids(self):
        from app.repositories.share_store import ShareStore
        async def run():
            store = ShareStore()
            t1, t2 = uuid4().hex, uuid4().hex
            await store.create(t1, "analysis-1", self._future())
            await store.create(t2, "analysis-2", self._future())
            rows = await store.list_by_token_ids([t1, t2])
            assert len(rows) == 2
            token_ids = {r["token_id"] for r in rows}
            assert token_ids == {t1, t2}
        asyncio.run(run())


# ---------------------------------------------------------------------------
# AuditStore
# ---------------------------------------------------------------------------

class TestAuditStore:
    def setup_method(self):
        _reset_db()

    def _create_user(self) -> str:
        from app.repositories.user_store import UserStore
        async def run():
            store = UserStore()
            user = await store.create(f"u{uuid4().hex[:6]}@x.com", "hash")
            return user.user_id
        return asyncio.run(run())

    def test_log_event(self):
        from app.repositories.audit_store import AuditStore
        user_id = self._create_user()
        async def run():
            store = AuditStore()
            await store.log(user_id, "test.action", "resource", "resource-id", {"key": "val"})
        asyncio.run(run())
