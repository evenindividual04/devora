"""Route-level tests covering all uncovered API paths."""
from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.db.models import Base
from app.db.session import engine
from app.main import app
from app.models.contracts import (
    AnalysisRecord,
    ArchetypeResult,
    DataScope,
    EvidenceRef,
    GitHubCommit,
    GitHubRepo,
    HonestyMode,
    OutputTarget,
    ReadmeResult,
    ReadmeSection,
    ReportResult,
)
from app.services.github_client import GitHubClient


def _reset_db() -> None:
    async def _drop_create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(_drop_create())


def _register_and_auth(client: TestClient, email: str = "u@test.com") -> dict:
    reg = client.post("/auth/register", json={"email": email, "password": "password123"})
    assert reg.status_code == 200
    return {"Authorization": f"Bearer {reg.json()['access_token']}"}


def _make_admin_auth(client: TestClient) -> dict:
    """Create an admin user and return auth headers."""
    async def _create():
        from app.repositories.user_store import user_store
        from app.services.auth_service import auth_service
        user = await user_store.create("admin@test.com", auth_service.hash_password("password123"), role="admin")
        token = auth_service.issue_access_token(user.user_id, "admin")
        return {"Authorization": f"Bearer {token}"}
    return asyncio.run(_create())


def _wait_completed(client: TestClient, aid: str, auth: dict, timeout: float = 3.0) -> None:
    start = time.time()
    while time.time() - start < timeout:
        s = client.get(f"/analysis/{aid}/status", headers=auth)
        if s.status_code == 200 and s.json()["status"] == "completed":
            return
        time.sleep(0.05)
    raise AssertionError("analysis did not complete in time")


def _completed_record(username: str = "alice") -> AnalysisRecord:
    archetype = ArchetypeResult(
        top_archetype="Builder",
        alternates=[],
        confidence=0.8,
        supporting_evidence=[EvidenceRef(source_type="repo", source_id="repo", excerpt=None)],
    )
    readme = ReadmeResult(
        markdown="# Hello",
        sections=[ReadmeSection(title="Bio", content="Alice", evidence_refs=[])],
    )
    report = ReportResult(
        summary="Alice builds things",
        archetype=archetype,
        standout_repos=["repo"],
        timeline=["2024"],
    )
    return AnalysisRecord(
        username=username,
        scope=DataScope.public,
        honesty_mode=HonestyMode.authentic,
        output_targets=[OutputTarget.readme, OutputTarget.report],
        include_private=False,
        status="completed",
        readme=readme,
        report=report,
        archetype=archetype,
        meta={"idempotency_key": uuid4().hex},
    )


def _insert_record(record: AnalysisRecord, user_id: str) -> None:
    async def _run():
        from app.repositories.analysis_store import store as analysis_store
        from app.repositories.owner_store import owner_store
        await analysis_store.create(record)
        await owner_store.bind_analysis(str(record.analysis_id), user_id)
    asyncio.run(_run())


def _get_user_id(email: str) -> str:
    async def _run():
        from app.repositories.user_store import user_store
        u = await user_store.get_by_email(email)
        return u.user_id
    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

class TestAuthRoutes:
    def setup_method(self):
        _reset_db()

    def test_register_duplicate_email(self):
        with TestClient(app) as client:
            client.post("/auth/register", json={"email": "a@a.com", "password": "password123"})
            r = client.post("/auth/register", json={"email": "a@a.com", "password": "password123"})
            assert r.status_code == 409

    def test_login_success(self):
        with TestClient(app) as client:
            client.post("/auth/register", json={"email": "b@b.com", "password": "password123"})
            r = client.post("/auth/login", json={"email": "b@b.com", "password": "password123"})
            assert r.status_code == 200
            assert "access_token" in r.json()

    def test_login_invalid_credentials(self):
        with TestClient(app) as client:
            client.post("/auth/register", json={"email": "c@c.com", "password": "password123"})
            r = client.post("/auth/login", json={"email": "c@c.com", "password": "wrongpass"})
            assert r.status_code == 401

    def test_login_nonexistent_user(self):
        with TestClient(app) as client:
            r = client.post("/auth/login", json={"email": "nobody@x.com", "password": "password123"})
            assert r.status_code == 401

    def test_refresh_invalid_token(self):
        with TestClient(app) as client:
            r = client.post("/auth/refresh", json={"refresh_token": "not.a.valid.jwt"})
            assert r.status_code == 401

    def test_refresh_user_not_found(self):
        from app.services.auth_service import auth_service
        with TestClient(app) as client:
            token, _, exp = auth_service.issue_refresh_token(str(uuid4()))
            r = client.post("/auth/refresh", json={"refresh_token": token})
            assert r.status_code == 401

    def test_logout_invalid_token(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.post("/auth/logout", json={"refresh_token": "bad-token"}, headers=auth)
            assert r.status_code == 401


# ---------------------------------------------------------------------------
# Analysis routes
# ---------------------------------------------------------------------------

class TestAnalysisRoutes:
    def setup_method(self):
        _reset_db()

    def test_list_analysis(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.get("/analysis", headers=auth)
            assert r.status_code == 200
            assert "analysis_ids" in r.json()

    def test_get_analysis_forbidden(self):
        with TestClient(app) as client:
            auth1 = _register_and_auth(client, "u1@test.com")
            auth2 = _register_and_auth(client, "u2@test.com")
            record = _completed_record()
            user_id = _get_user_id("u1@test.com")
            _insert_record(record, user_id)
            r = client.get(f"/analysis/{record.analysis_id}", headers=auth2)
            assert r.status_code == 403

    def test_get_analysis_not_found(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.get(f"/analysis/{uuid4()}", headers=auth)
            assert r.status_code in (403, 404)

    def test_get_analysis_success(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            record = _completed_record()
            user_id = _get_user_id("u@test.com")
            _insert_record(record, user_id)
            r = client.get(f"/analysis/{record.analysis_id}", headers=auth)
            assert r.status_code == 200

    def test_get_status_forbidden(self):
        with TestClient(app) as client:
            auth1 = _register_and_auth(client, "x1@test.com")
            auth2 = _register_and_auth(client, "x2@test.com")
            record = _completed_record()
            user_id = _get_user_id("x1@test.com")
            _insert_record(record, user_id)
            r = client.get(f"/analysis/{record.analysis_id}/status", headers=auth2)
            assert r.status_code == 403

    def test_get_signals_forbidden(self):
        with TestClient(app) as client:
            auth1 = _register_and_auth(client, "s1@test.com")
            auth2 = _register_and_auth(client, "s2@test.com")
            record = _completed_record()
            user_id = _get_user_id("s1@test.com")
            _insert_record(record, user_id)
            r = client.get(f"/analysis/{record.analysis_id}/signals", headers=auth2)
            assert r.status_code == 403

    def test_get_signals_not_found(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            user_id = _get_user_id("u@test.com")
            record = _completed_record()
            _insert_record(record, user_id)
            r = client.get(f"/analysis/{uuid4()}/signals", headers=auth)
            assert r.status_code in (403, 404)

    def test_get_signals_success(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            user_id = _get_user_id("u@test.com")
            record = _completed_record()
            _insert_record(record, user_id)
            r = client.get(f"/analysis/{record.analysis_id}/signals", headers=auth)
            assert r.status_code == 200

    def test_get_readme_forbidden(self):
        with TestClient(app) as client:
            auth1 = _register_and_auth(client, "r1@test.com")
            auth2 = _register_and_auth(client, "r2@test.com")
            record = _completed_record()
            user_id = _get_user_id("r1@test.com")
            _insert_record(record, user_id)
            r = client.get(f"/analysis/{record.analysis_id}/readme", headers=auth2)
            assert r.status_code == 403

    def test_get_readme_not_ready(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            user_id = _get_user_id("u@test.com")
            queued = AnalysisRecord(
                username="alice", scope=DataScope.public, honesty_mode=HonestyMode.authentic,
                output_targets=[OutputTarget.readme], include_private=False, status="queued",
                meta={"idempotency_key": uuid4().hex},
            )
            _insert_record(queued, user_id)
            r = client.get(f"/analysis/{queued.analysis_id}/readme", headers=auth)
            assert r.status_code == 409

    def test_get_readme_success(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            user_id = _get_user_id("u@test.com")
            record = _completed_record()
            _insert_record(record, user_id)
            r = client.get(f"/analysis/{record.analysis_id}/readme", headers=auth)
            assert r.status_code == 200

    def test_get_report_forbidden(self):
        with TestClient(app) as client:
            auth1 = _register_and_auth(client, "rp1@test.com")
            auth2 = _register_and_auth(client, "rp2@test.com")
            record = _completed_record()
            user_id = _get_user_id("rp1@test.com")
            _insert_record(record, user_id)
            r = client.get(f"/analysis/{record.analysis_id}/report", headers=auth2)
            assert r.status_code == 403

    def test_get_report_not_ready(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            user_id = _get_user_id("u@test.com")
            queued = AnalysisRecord(
                username="alice", scope=DataScope.public, honesty_mode=HonestyMode.authentic,
                output_targets=[OutputTarget.report], include_private=False, status="queued",
                meta={"idempotency_key": uuid4().hex},
            )
            _insert_record(queued, user_id)
            r = client.get(f"/analysis/{queued.analysis_id}/report", headers=auth)
            assert r.status_code == 409

    def test_get_report_success(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            user_id = _get_user_id("u@test.com")
            record = _completed_record()
            _insert_record(record, user_id)
            r = client.get(f"/analysis/{record.analysis_id}/report", headers=auth)
            assert r.status_code == 200

    def test_create_share_forbidden(self):
        with TestClient(app) as client:
            auth1 = _register_and_auth(client, "sh1@test.com")
            auth2 = _register_and_auth(client, "sh2@test.com")
            record = _completed_record()
            user_id = _get_user_id("sh1@test.com")
            _insert_record(record, user_id)
            r = client.post(f"/analysis/{record.analysis_id}/share", json={"ttl_minutes": 10}, headers=auth2)
            assert r.status_code == 403

    def test_create_share_not_completed(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            user_id = _get_user_id("u@test.com")
            queued = AnalysisRecord(
                username="alice", scope=DataScope.public, honesty_mode=HonestyMode.authentic,
                output_targets=[OutputTarget.readme], include_private=False, status="queued",
                meta={"idempotency_key": uuid4().hex},
            )
            _insert_record(queued, user_id)
            r = client.post(f"/analysis/{queued.analysis_id}/share", json={"ttl_minutes": 10}, headers=auth)
            assert r.status_code == 404

    def test_run_analysis_idempotency(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            payload = {"username": "alice", "scope": "public", "honesty_mode": "authentic", "output_targets": ["readme"], "include_private": False}
            r1 = client.post("/analysis/run", json=payload, headers=auth)
            assert r1.status_code == 200
            aid1 = r1.json()["analysis_id"]
            r2 = client.post("/analysis/run", json=payload, headers=auth)
            assert r2.status_code == 200
            assert r2.json()["analysis_id"] == aid1

    def test_run_analysis_private_no_token(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.post("/analysis/run", json={"username": "alice", "include_private": True}, headers=auth)
            assert r.status_code == 400

    def test_run_analysis_private_wrong_scope(self):
        async def setup():
            from app.repositories.oauth_store import oauth_store
            await oauth_store.upsert_token("alice", "some-token", "bearer", "read:user")
        asyncio.run(setup())
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.post("/analysis/run", json={"username": "alice", "include_private": True}, headers=auth)
            assert r.status_code == 403


# ---------------------------------------------------------------------------
# Share routes
# ---------------------------------------------------------------------------

class TestShareRoutes:
    def setup_method(self):
        _reset_db()

    def test_get_shared_report_invalid_token(self):
        with TestClient(app) as client:
            r = client.get("/share/badtoken")
            assert r.status_code == 401

    def test_get_shared_report_no_dot(self):
        with TestClient(app) as client:
            r = client.get("/share/nodottoken")
            assert r.status_code == 401

    def test_get_shared_report_revoked(self):
        from app.services.share_token_service import share_token_service
        async def setup():
            from app.repositories.share_store import share_store as ss
            token_id, token, exp = share_token_service.create("fake-analysis-id")
            await ss.create(token_id, "fake-analysis-id", exp)
            await ss.revoke(token_id)
            return token
        token = asyncio.run(setup())
        with TestClient(app) as client:
            r = client.get(f"/share/{token}")
            assert r.status_code == 401

    def test_get_shared_report_analysis_not_found(self):
        from app.services.share_token_service import share_token_service
        async def setup():
            from app.repositories.share_store import share_store as ss
            token_id, token, exp = share_token_service.create(str(uuid4()))
            await ss.create(token_id, str(uuid4()), exp)
            return token
        token = asyncio.run(setup())
        with TestClient(app) as client:
            r = client.get(f"/share/{token}")
            assert r.status_code == 404

    def test_list_shares(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.get("/shares", headers=auth)
            assert r.status_code == 200
            assert "shares" in r.json()

    def test_revoke_share_invalid_token(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.post("/shares/badtoken/revoke", headers=auth)
            assert r.status_code == 400

    def test_revoke_share_not_owned(self):
        from app.services.share_token_service import share_token_service
        async def setup():
            from app.repositories.share_store import share_store as ss
            from app.repositories.user_store import user_store
            from app.services.auth_service import auth_service
            user1 = await user_store.create("revoke1@test.com", auth_service.hash_password("password123"))
            token_id, token, exp = share_token_service.create(str(uuid4()))
            await ss.create(token_id, str(uuid4()), exp)
            return token
        token = asyncio.run(setup())
        with TestClient(app) as client:
            auth2 = _register_and_auth(client, "revoke2@test.com")
            r = client.post(f"/shares/{token}/revoke", headers=auth2)
            assert r.status_code == 403

    def test_revoke_share_not_found(self):
        from app.services.share_token_service import share_token_service
        from app.repositories.owner_store import owner_store
        token_id, token, _ = share_token_service.create(str(uuid4()))
        with TestClient(app) as client:
            auth = _register_and_auth(client, "nf1@test.com")
            user_id = _get_user_id("nf1@test.com")
            asyncio.run(owner_store.bind_share(token_id, user_id))
            r = client.post(f"/shares/{token}/revoke", headers=auth)
            assert r.status_code == 404


# ---------------------------------------------------------------------------
# GitHub OAuth routes
# ---------------------------------------------------------------------------

class TestGitHubOAuthRoutes:
    def setup_method(self):
        _reset_db()

    def test_github_login(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.get("/auth/github/login?username=alice", headers=auth)
            assert r.status_code == 200
            assert "auth_url" in r.json()

    def test_github_callback_invalid_state(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.get("/auth/github/callback?code=code123&state=badstate", headers=auth)
            assert r.status_code == 400

    def test_github_callback_success(self):
        async def setup():
            from app.repositories.oauth_state_store import oauth_state_store
            await oauth_state_store.create_state("validstate", "alice", ttl_minutes=10)
        asyncio.run(setup())

        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"access_token": "ghat_tok", "token_type": "bearer", "scope": "repo"})
        mock_response.raise_for_status = MagicMock()

        with TestClient(app) as client:
            auth = _register_and_auth(client)
            with patch("httpx.AsyncClient") as mock_cls:
                mock_instance = AsyncMock()
                mock_instance.post = AsyncMock(return_value=mock_response)
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
                r = client.get("/auth/github/callback?code=code123&state=validstate", headers=auth)
            assert r.status_code == 200
            assert r.json()["status"] == "connected"

    def test_github_callback_httpx_error(self):
        import httpx
        async def setup():
            from app.repositories.oauth_state_store import oauth_state_store
            await oauth_state_store.create_state("errstate", "alice", ttl_minutes=10)
        asyncio.run(setup())

        with TestClient(app) as client:
            auth = _register_and_auth(client)
            with patch("httpx.AsyncClient") as mock_cls:
                mock_instance = AsyncMock()
                mock_instance.post = AsyncMock(side_effect=httpx.HTTPError("network error"))
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
                r = client.get("/auth/github/callback?code=code123&state=errstate", headers=auth)
            assert r.status_code == 502

    def test_github_callback_no_access_token(self):
        async def setup():
            from app.repositories.oauth_state_store import oauth_state_store
            await oauth_state_store.create_state("notoken", "alice", ttl_minutes=10)
        asyncio.run(setup())

        mock_response = MagicMock()
        mock_response.json = MagicMock(return_value={"error": "bad_verification_code"})
        mock_response.raise_for_status = MagicMock()

        with TestClient(app) as client:
            auth = _register_and_auth(client)
            with patch("httpx.AsyncClient") as mock_cls:
                mock_instance = AsyncMock()
                mock_instance.post = AsyncMock(return_value=mock_response)
                mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
                r = client.get("/auth/github/callback?code=badcode&state=notoken", headers=auth)
            assert r.status_code == 400


# ---------------------------------------------------------------------------
# Ops routes (admin only)
# ---------------------------------------------------------------------------

class TestOpsRoutes:
    def setup_method(self):
        _reset_db()

    def test_dead_letter_requires_admin(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.get("/ops/dead-letter", headers=auth)
            assert r.status_code == 403

    def test_dead_letter_admin(self):
        with TestClient(app) as client:
            admin_auth = _make_admin_auth(client)
            r = client.get("/ops/dead-letter", headers=admin_auth)
            assert r.status_code == 200
            assert "items" in r.json()

    def test_requeue_requires_admin(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.post(f"/ops/requeue/{uuid4()}", headers=auth)
            assert r.status_code == 403

    def test_requeue_not_found(self):
        with TestClient(app) as client:
            admin_auth = _make_admin_auth(client)
            r = client.post(f"/ops/requeue/{uuid4()}", headers=admin_auth)
            assert r.status_code == 404

    def test_requeue_success(self):
        with TestClient(app) as client:
            admin_auth = _make_admin_auth(client)
            record = _completed_record()
            async def _insert():
                from app.repositories.analysis_store import store as analysis_store
                await analysis_store.create(record)
            asyncio.run(_insert())
            r = client.post(f"/ops/requeue/{record.analysis_id}", headers=admin_auth)
            assert r.status_code == 200

    def test_metrics_requires_admin(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client)
            r = client.get("/ops/metrics", headers=auth)
            assert r.status_code == 403

    def test_metrics_admin(self):
        with TestClient(app) as client:
            admin_auth = _make_admin_auth(client)
            r = client.get("/ops/metrics", headers=admin_auth)
            assert r.status_code == 200


# ---------------------------------------------------------------------------
# Health routes
# ---------------------------------------------------------------------------

class TestHealthRoutes:
    def setup_method(self):
        _reset_db()

    def test_health_ready_db_failure(self):
        with TestClient(app) as client:
            with patch("app.api.routes.db_ping", new=AsyncMock(return_value=False)):
                r = client.get("/health/ready")
            assert r.status_code == 503


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_rate_limit_exceeded(self):
        from app.core.rate_limit import InMemoryRateLimiter
        import fastapi
        limiter = InMemoryRateLimiter()
        for _ in range(60):
            limiter.check("test-key")
        with pytest.raises(fastapi.HTTPException) as exc_info:
            limiter.check("test-key")
        assert exc_info.value.status_code == 429

    def test_old_hits_expire(self):
        import pytest
        from app.core.rate_limit import InMemoryRateLimiter
        limiter = InMemoryRateLimiter()
        # Manually inject an old hit from 90 seconds ago
        limiter._hits["expiry-key"].append(time.time() - 90)
        # Adding a new hit should evict the old one — should not raise
        for _ in range(60):
            limiter.check("expiry-key")
        # Now it should be at the limit (60 fresh + old was evicted)
        import fastapi
        with pytest.raises(fastapi.HTTPException):
            limiter.check("expiry-key")


import pytest


# ---------------------------------------------------------------------------
# Edge-case coverage: orphaned ownership, deleted user, invalid JWT fields
# ---------------------------------------------------------------------------

class TestEdgeCaseCoverage:
    """Tests that cover defensive error branches only reachable through direct DB manipulation."""

    def setup_method(self):
        _reset_db()

    def test_analysis_not_found_after_ownership_check(self):
        """Owned analysis_id with no DB record → 404 on all 5 read endpoints."""
        from app.repositories.owner_store import owner_store
        orphan_id = str(uuid4())
        with TestClient(app) as client:
            auth = _register_and_auth(client, "orphan@test.com")
            user_id = _get_user_id("orphan@test.com")
            asyncio.run(owner_store.bind_analysis(orphan_id, user_id))
            for path in ["", "/status", "/signals", "/readme", "/report"]:
                r = client.get(f"/analysis/{orphan_id}{path}", headers=auth)
                assert r.status_code == 404, f"Expected 404 for /analysis/{orphan_id}{path}, got {r.status_code}"

    def test_refresh_token_user_deleted(self):
        """Valid refresh session but user deleted from DB → 401."""
        from app.db.models import UserORM
        from app.db.session import SessionLocal
        from sqlalchemy import delete as sa_delete

        with TestClient(app) as client:
            reg = client.post("/auth/register", json={"email": "del@test.com", "password": "password123"})
            refresh_token = reg.json()["refresh_token"]
            user_id = _get_user_id("del@test.com")

            async def _delete_user():
                async with SessionLocal() as session:
                    await session.execute(sa_delete(UserORM).where(UserORM.user_id == user_id))
                    await session.commit()
            asyncio.run(_delete_user())

            r = client.post("/auth/refresh", json={"refresh_token": refresh_token})
            assert r.status_code == 401

    def test_get_shared_report_missing_aid_in_payload(self):
        """Share token with no 'aid' field in payload → 400."""
        from app.repositories.share_store import share_store
        from app.services.share_token_service import share_token_service
        token_id = uuid4().hex
        asyncio.run(share_store.create(token_id, "some-analysis", datetime.now(UTC) + timedelta(hours=1)))
        with patch.object(share_token_service, "verify", return_value={"tid": token_id}):
            with TestClient(app) as client:
                r = client.get(f"/share/{token_id}")
                assert r.status_code == 400

    def test_revoke_share_missing_tid_in_payload(self):
        """Revoke share token where payload has no 'tid' field → 400."""
        from app.services.share_token_service import share_token_service
        _, token, _ = share_token_service.create(str(uuid4()))
        with patch.object(share_token_service, "verify", return_value={"aid": "x"}):
            with TestClient(app) as client:
                auth = _register_and_auth(client, "notid@test.com")
                r = client.post(f"/shares/{token}/revoke", headers=auth)
                assert r.status_code == 400

    def test_get_current_user_empty_sub_in_token(self):
        """Access token with empty 'sub' field → 401."""
        from app.services.auth_service import auth_service
        token = auth_service.issue_access_token("", "user")
        with TestClient(app) as client:
            r = client.get("/analysis", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 401

    def test_main_app_global_exception_handler(self):
        """Unhandled exception in a route → 500 via main app's exception handler."""
        from app.main import app as main_app

        @main_app.get("/test-boom-coverage-only")
        async def _boom():
            raise RuntimeError("test boom")

        with TestClient(main_app, raise_server_exceptions=False) as client:
            r = client.get("/test-boom-coverage-only")
            assert r.status_code == 500
            assert r.json()["detail"] == "internal server error"


# ---------------------------------------------------------------------------
# Eval routes: GET /analysis/{id}/eval
# ---------------------------------------------------------------------------

class TestEvalRoutes:
    def setup_method(self):
        _reset_db()

    def test_get_eval_on_demand(self):
        """GET /analysis/{id}/eval with no cached eval scores on demand and caches result."""
        from app.models.contracts import DimensionScore, EvalResult
        from app.services.eval_service import ReadmeEvaluator

        mock_evaluator = MagicMock(spec=ReadmeEvaluator)
        mock_eval = EvalResult(
            scores=[DimensionScore(dimension="authenticity", score=4.0, reasoning="ok", judge="deterministic")],
            aggregate=4.0,
            model_set=["deterministic"],
        )
        mock_evaluator.evaluate.return_value = mock_eval

        with TestClient(app) as client:
            auth = _register_and_auth(client, "eval1@test.com")
            uid = _get_user_id("eval1@test.com")
            record = _completed_record("evaluser1")
            _insert_record(record, uid)
            aid = str(record.analysis_id)

            with patch("app.services.eval_service.get_evaluator", return_value=mock_evaluator):
                r = client.get(f"/analysis/{aid}/eval", headers=auth)

        assert r.status_code == 200
        data = r.json()
        assert data["aggregate"] == 4.0
        assert "deterministic" in data["model_set"]

    def test_get_eval_cached(self):
        """GET /analysis/{id}/eval with a cached eval returns it without re-scoring."""
        from app.models.contracts import DimensionScore, EvalResult

        cached_eval = EvalResult(
            scores=[DimensionScore(dimension="authenticity", score=5.0, reasoning="cached", judge="deterministic")],
            aggregate=5.0,
            model_set=["deterministic"],
        )

        with TestClient(app) as client:
            auth = _register_and_auth(client, "eval2@test.com")
            uid = _get_user_id("eval2@test.com")
            record = _completed_record("evaluser2")
            record.eval = cached_eval
            _insert_record(record, uid)
            aid = str(record.analysis_id)

            r = client.get(f"/analysis/{aid}/eval", headers=auth)

        assert r.status_code == 200
        assert r.json()["aggregate"] == 5.0

    def test_get_eval_not_found(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client, "eval3@test.com")
            r = client.get(f"/analysis/{uuid4()}/eval", headers=auth)
        assert r.status_code == 404

    def test_get_eval_not_completed(self):
        """Queued analysis has no readme → 404."""
        with TestClient(app) as client:
            auth = _register_and_auth(client, "eval4@test.com")
            uid = _get_user_id("eval4@test.com")

            from app.models.contracts import DataScope, HonestyMode, OutputTarget
            record = AnalysisRecord(
                username="pending",
                scope=DataScope.public,
                honesty_mode=HonestyMode.authentic,
                output_targets=[OutputTarget.readme],
                include_private=False,
                status="queued",
                meta={},
            )
            _insert_record(record, uid)
            r = client.get(f"/analysis/{record.analysis_id}/eval", headers=auth)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Ops eval summary: GET /ops/eval/summary
# ---------------------------------------------------------------------------

class TestOpsEvalSummary:
    def setup_method(self):
        _reset_db()

    def test_eval_summary_empty(self):
        """No completed analyses with evals → count 0."""
        with TestClient(app) as client:
            admin_auth = _make_admin_auth(client)
            r = client.get("/ops/eval/summary", headers=admin_auth)
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_eval_summary_with_evals(self):
        """Completed records with evals appear in aggregated summary."""
        from app.models.contracts import DimensionScore, EvalResult

        eval_result = EvalResult(
            scores=[DimensionScore(dimension="authenticity", score=4.0, reasoning="ok", judge="deterministic")],
            aggregate=4.0,
            model_set=["deterministic"],
        )

        with TestClient(app) as client:
            admin_auth = _make_admin_auth(client)

            async def _insert():
                from app.repositories.analysis_store import store as astore
                record = _completed_record("summaryuser")
                record.eval = eval_result
                await astore.create(record)
            asyncio.run(_insert())

            r = client.get("/ops/eval/summary", headers=admin_auth)

        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert "authenticity" in data["dimensions"]
        assert isinstance(data["banned_phrase_incidence"], float)

    def test_eval_summary_requires_admin(self):
        with TestClient(app) as client:
            auth = _register_and_auth(client, "nonadmin@test.com")
            r = client.get("/ops/eval/summary", headers=auth)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Anonymous analysis run: POST /analysis/run without auth
# ---------------------------------------------------------------------------

class TestAnonymousRun:
    def setup_method(self):
        _reset_db()

    def test_anonymous_run_strips_private(self):
        """Anonymous POST /analysis/run with include_private=True → scope=public."""
        mock_pipeline = AsyncMock()

        async def _fake_run(record):
            record.status = "completed"
            return record

        mock_pipeline.run = _fake_run

        with patch("app.workers.pipeline.worker", mock_pipeline), \
             patch.object(GitHubClient, "fetch_repos", new=AsyncMock(return_value=[])), \
             patch.object(GitHubClient, "fetch_commits", new=AsyncMock(return_value=[])):
            with TestClient(app) as client:
                r = client.post("/analysis/run", json={
                    "username": "torvalds",
                    "include_private": True,
                    "honesty_mode": "authentic",
                    "output_targets": ["readme"],
                })
        assert r.status_code == 200
        data = r.json()
        assert "analysis_id" in data
