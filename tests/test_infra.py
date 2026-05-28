"""Tests for infrastructure: worker consumer, db session, queue redis, main lifespan."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.db.models import Base
from app.db.session import engine


def _reset_db() -> None:
    async def _drop_create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(_drop_create())


# ---------------------------------------------------------------------------
# db/session — db_ping and close_db
# ---------------------------------------------------------------------------

class TestDbSession:
    def setup_method(self):
        _reset_db()

    def test_db_ping_success(self):
        from app.db.session import db_ping
        result = asyncio.run(db_ping())
        assert result is True

    def test_db_ping_failure(self):
        from app.db.session import db_ping
        from sqlalchemy.ext.asyncio import create_async_engine
        with patch("app.db.session.engine") as mock_engine:
            mock_conn = AsyncMock()
            mock_conn.execute = AsyncMock(side_effect=Exception("DB down"))
            mock_engine.connect = MagicMock(return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn),
                __aexit__=AsyncMock(return_value=None),
            ))
            result = asyncio.run(db_ping())
        assert result is False

    def test_close_db(self):
        from app.db.session import close_db
        asyncio.run(close_db())  # should not raise


# ---------------------------------------------------------------------------
# queue/manager — Redis paths (mocked)
# ---------------------------------------------------------------------------

class TestQueueManagerRedis:
    def test_enqueue_uses_redis_when_configured(self):
        from app.queue.manager import QueueManager

        async def run():
            qm = QueueManager()
            mock_redis = AsyncMock()
            mock_redis.rpush = AsyncMock()
            with patch("app.queue.manager.settings") as mock_settings:
                mock_settings.use_redis_queue = True
                mock_settings.redis_url = "redis://localhost"
                with patch.object(qm, "_redis_client", AsyncMock(return_value=mock_redis)):
                    await qm.enqueue("test-id")
            mock_redis.rpush.assert_called_once()

        asyncio.run(run())

    def test_dequeue_redis_returns_item(self):
        import json
        from app.queue.manager import QueueManager

        async def run():
            qm = QueueManager()
            mock_redis = AsyncMock()
            mock_redis.blpop = AsyncMock(return_value=("analysis_jobs", json.dumps({"analysis_id": "abc"})))
            with patch("app.queue.manager.settings") as mock_settings:
                mock_settings.use_redis_queue = True
                with patch.object(qm, "_redis_client", AsyncMock(return_value=mock_redis)):
                    result = await qm.dequeue(timeout_seconds=1)
            return result

        assert asyncio.run(run()) == "abc"

    def test_dequeue_redis_returns_none_on_timeout(self):
        from app.queue.manager import QueueManager

        async def run():
            qm = QueueManager()
            mock_redis = AsyncMock()
            mock_redis.blpop = AsyncMock(return_value=None)
            with patch("app.queue.manager.settings") as mock_settings:
                mock_settings.use_redis_queue = True
                with patch.object(qm, "_redis_client", AsyncMock(return_value=mock_redis)):
                    result = await qm.dequeue(timeout_seconds=1)
            return result

        assert asyncio.run(run()) is None

    def test_ping_redis_success(self):
        from app.queue.manager import QueueManager

        async def run():
            qm = QueueManager()
            mock_redis = AsyncMock()
            mock_redis.ping = AsyncMock(return_value=True)
            with patch("app.queue.manager.settings") as mock_settings:
                mock_settings.use_redis_queue = True
                with patch.object(qm, "_redis_client", AsyncMock(return_value=mock_redis)):
                    return await qm.ping()

        assert asyncio.run(run()) is True

    def test_ping_redis_failure(self):
        from app.queue.manager import QueueManager

        async def run():
            qm = QueueManager()
            with patch("app.queue.manager.settings") as mock_settings:
                mock_settings.use_redis_queue = True
                with patch.object(qm, "_redis_client", AsyncMock(side_effect=Exception("conn refused"))):
                    return await qm.ping()

        assert asyncio.run(run()) is False

    def test_close_with_redis(self):
        from app.queue.manager import QueueManager

        async def run():
            qm = QueueManager()
            mock_redis = AsyncMock()
            mock_redis.aclose = AsyncMock()
            qm._redis = mock_redis
            await qm.close()
            assert qm._redis is None
            mock_redis.aclose.assert_called_once()

        asyncio.run(run())

    def test_redis_client_reuses_connection(self):
        from app.queue.manager import QueueManager

        async def run():
            qm = QueueManager()
            mock_redis = MagicMock()
            with patch("redis.asyncio.Redis.from_url", return_value=mock_redis) as mock_from_url, \
                 patch("app.queue.manager.settings") as mock_settings:
                mock_settings.redis_url = "redis://localhost"
                r1 = await qm._redis_client()
                r2 = await qm._redis_client()
                assert r1 is r2
                mock_from_url.assert_called_once()

        asyncio.run(run())


# ---------------------------------------------------------------------------
# WorkerConsumer
# ---------------------------------------------------------------------------

class TestWorkerConsumer:
    def setup_method(self):
        _reset_db()

    def test_run_forever_stops_when_flag_cleared(self):
        from app.workers.consumer import WorkerConsumer

        async def run():
            consumer = WorkerConsumer()
            call_count = 0

            async def fake_dequeue(timeout_seconds=2):
                nonlocal call_count
                call_count += 1
                consumer._running = False
                return None  # triggers continue, then loop exits

            with patch("app.workers.consumer.queue_manager") as mock_qm:
                mock_qm.dequeue = fake_dequeue
                await consumer.run_forever()

            return call_count

        count = asyncio.run(run())
        assert count >= 1

    def test_run_forever_skips_completed_record(self):
        from app.workers.consumer import WorkerConsumer
        from app.models.contracts import AnalysisRecord, DataScope, HonestyMode, OutputTarget

        call_count = 0

        async def run():
            consumer = WorkerConsumer()
            record = AnalysisRecord(
                username="alice", scope=DataScope.public, honesty_mode=HonestyMode.authentic,
                output_targets=[OutputTarget.readme], include_private=False, status="completed",
            )

            dequeue_calls = [0]
            async def fake_dequeue(timeout_seconds=2):
                dequeue_calls[0] += 1
                if dequeue_calls[0] == 1:
                    return str(record.analysis_id)
                consumer._running = False
                return None

            with patch("app.workers.consumer.queue_manager") as mock_qm, \
                 patch("app.workers.consumer.store") as mock_store:
                mock_qm.dequeue = fake_dequeue
                mock_store.get = AsyncMock(return_value=record)
                await consumer.run_forever()

        asyncio.run(run())

    def test_run_forever_skips_analyzing_record(self):
        from app.workers.consumer import WorkerConsumer
        from app.models.contracts import AnalysisRecord, DataScope, HonestyMode, OutputTarget

        async def run():
            consumer = WorkerConsumer()
            record = AnalysisRecord(
                username="alice", scope=DataScope.public, honesty_mode=HonestyMode.authentic,
                output_targets=[OutputTarget.readme], include_private=False, status="analyzing",
            )
            dequeue_calls = [0]

            async def fake_dequeue(timeout_seconds=2):
                dequeue_calls[0] += 1
                if dequeue_calls[0] == 1:
                    return str(record.analysis_id)
                consumer._running = False
                return None

            with patch("app.workers.consumer.queue_manager") as mock_qm, \
                 patch("app.workers.consumer.store") as mock_store:
                mock_qm.dequeue = fake_dequeue
                mock_store.get = AsyncMock(return_value=record)
                await consumer.run_forever()

        asyncio.run(run())

    def test_run_forever_exception_triggers_retry(self):
        from app.workers.consumer import WorkerConsumer
        from app.models.contracts import AnalysisRecord, DataScope, HonestyMode, OutputTarget

        async def run():
            consumer = WorkerConsumer()
            record = AnalysisRecord(
                username="alice", scope=DataScope.public, honesty_mode=HonestyMode.authentic,
                output_targets=[OutputTarget.readme], include_private=False, status="queued",
                attempts=0,
            )
            dequeue_calls = [0]

            async def fake_dequeue(timeout_seconds=2):
                dequeue_calls[0] += 1
                if dequeue_calls[0] == 1:
                    return str(record.analysis_id)
                consumer._running = False
                return None

            with patch("app.workers.consumer.queue_manager") as mock_qm, \
                 patch("app.workers.consumer.store") as mock_store, \
                 patch("app.workers.consumer.worker") as mock_worker, \
                 patch("app.workers.consumer.settings") as mock_settings, \
                 patch("asyncio.sleep", new=AsyncMock()):
                mock_qm.dequeue = fake_dequeue
                mock_qm.enqueue = AsyncMock()
                mock_store.get = AsyncMock(return_value=record)
                mock_store.update = AsyncMock()
                mock_worker.run = AsyncMock(side_effect=RuntimeError("pipeline error"))
                mock_settings.worker_max_attempts = 3
                mock_settings.worker_base_backoff_seconds = 0.1
                await consumer.run_forever()

            assert record.status == "queued"
            assert "pipeline error" in record.failure_reason

        asyncio.run(run())

    def test_run_forever_exception_permanent_failure(self):
        from app.workers.consumer import WorkerConsumer
        from app.models.contracts import AnalysisRecord, DataScope, HonestyMode, OutputTarget

        async def run():
            consumer = WorkerConsumer()
            record = AnalysisRecord(
                username="alice", scope=DataScope.public, honesty_mode=HonestyMode.authentic,
                output_targets=[OutputTarget.readme], include_private=False, status="queued",
                attempts=2,
            )
            dequeue_calls = [0]

            async def fake_dequeue(timeout_seconds=2):
                dequeue_calls[0] += 1
                if dequeue_calls[0] == 1:
                    return str(record.analysis_id)
                consumer._running = False
                return None

            with patch("app.workers.consumer.queue_manager") as mock_qm, \
                 patch("app.workers.consumer.store") as mock_store, \
                 patch("app.workers.consumer.worker") as mock_worker, \
                 patch("app.workers.consumer.settings") as mock_settings:
                mock_qm.dequeue = fake_dequeue
                mock_store.get = AsyncMock(return_value=record)
                mock_store.update = AsyncMock()
                mock_worker.run = AsyncMock(side_effect=RuntimeError("fatal error"))
                mock_settings.worker_max_attempts = 3
                mock_settings.worker_base_backoff_seconds = 0.1
                await consumer.run_forever()

            assert record.status == "failed_permanent"

        asyncio.run(run())

    def test_stop(self):
        from app.workers.consumer import WorkerConsumer

        async def run():
            consumer = WorkerConsumer()
            consumer._running = True
            await consumer.stop()
            assert consumer._running is False

        asyncio.run(run())


# ---------------------------------------------------------------------------
# workers/run.py — main() function
# ---------------------------------------------------------------------------

class TestWorkersRun:
    def test_main_calls_consumer_run_forever(self):
        from app.workers import run as run_module

        with patch("app.workers.run.consumer") as mock_consumer:
            mock_consumer.run_forever = AsyncMock()
            run_module.main()
            mock_consumer.run_forever.assert_called_once()


# ---------------------------------------------------------------------------
# main.py lifespan — prod startup guard
# ---------------------------------------------------------------------------

class TestMainLifespan:
    def test_prod_startup_refuses_default_secrets(self):
        from fastapi.testclient import TestClient
        from app.main import app
        with patch("app.main.settings") as mock_settings:
            mock_settings.app_env = "production"
            mock_settings.api_key = "devora-local-admin-key"
            mock_settings.share_token_secret = "devora-local-share-secret"
            mock_settings.run_worker_in_api = False
            with pytest.raises(RuntimeError, match="Refusing to start"):
                with TestClient(app):
                    pass

    def test_unhandled_exception_returns_500(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routes import router as app_router

        test_app = FastAPI()
        test_app.include_router(app_router)

        @test_app.exception_handler(Exception)
        async def handler(_request, exc):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=500, content={"detail": "internal server error"})

        @test_app.get("/boom")
        async def boom():
            raise RuntimeError("kaboom")

        with TestClient(test_app, raise_server_exceptions=False) as client:
            r = client.get("/boom")
            assert r.status_code == 500


# ---------------------------------------------------------------------------
# core/security — require_api_key and get_current_user edge cases
# ---------------------------------------------------------------------------

class TestSecurity:
    def setup_method(self):
        _reset_db()

    def test_require_api_key_invalid(self):
        async def run():
            from app.core.security import require_api_key
            import fastapi
            with pytest.raises(fastapi.HTTPException) as exc_info:
                await require_api_key(x_api_key="wrong-key")
            assert exc_info.value.status_code == 401

        asyncio.run(run())

    def test_require_api_key_valid(self):
        async def run():
            from app.core.security import require_api_key
            from app.core.config import settings
            await require_api_key(x_api_key=settings.api_key)  # should not raise

        asyncio.run(run())

    def test_get_current_user_invalid_token(self):
        async def run():
            from app.core.security import get_current_user
            from fastapi.security import HTTPAuthorizationCredentials
            import fastapi
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not.a.jwt")
            with pytest.raises(fastapi.HTTPException) as exc_info:
                await get_current_user(creds)
            assert exc_info.value.status_code == 401

        asyncio.run(run())

    def test_get_current_user_user_not_found(self):
        async def run():
            from app.core.security import get_current_user
            from app.services.auth_service import auth_service
            from fastapi.security import HTTPAuthorizationCredentials
            import fastapi
            token = auth_service.issue_access_token(str(uuid4()), "user")
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            with pytest.raises(fastapi.HTTPException) as exc_info:
                await get_current_user(creds)
            assert exc_info.value.status_code == 401

        asyncio.run(run())

    def test_require_admin_non_admin(self):
        async def run():
            from app.core.security import require_admin, CurrentUser
            import fastapi
            user = CurrentUser(user_id="u1", role="user", email="u@test.com")
            with pytest.raises(fastapi.HTTPException) as exc_info:
                await require_admin(user)
            assert exc_info.value.status_code == 403

        asyncio.run(run())

    def test_require_admin_success(self):
        async def run():
            from app.core.security import require_admin, CurrentUser
            admin = CurrentUser(user_id="a1", role="admin", email="admin@test.com")
            result = await require_admin(admin)
            assert result is admin

        asyncio.run(run())


# ---------------------------------------------------------------------------
# core/idempotency + core/metrics
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_build_idempotency_key(self):
        from app.core.idempotency import build_idempotency_key
        from app.models.contracts import AnalysisRunRequest, DataScope, HonestyMode, OutputTarget
        req = AnalysisRunRequest(username="alice", scope=DataScope.public, honesty_mode=HonestyMode.authentic, output_targets=[OutputTarget.readme], include_private=False)
        key = build_idempotency_key(req)
        assert isinstance(key, str)
        assert len(key) > 0
        # Same request produces same key
        assert build_idempotency_key(req) == key


class TestMetrics:
    def test_incr_and_snapshot(self):
        from app.core.metrics import InMemoryMetrics
        m = InMemoryMetrics()
        m.incr("test.counter")
        m.incr("test.counter")
        snap = m.snapshot()
        assert snap["counters"]["test.counter"] == 2

    def test_timing(self):
        from app.core.metrics import InMemoryMetrics
        m = InMemoryMetrics()
        m.timing("test.timer", 50.0)
        m.timing("test.timer", 100.0)
        snap = m.snapshot()
        assert snap["timers"]["test.timer"]["count"] == 2
        assert snap["timers"]["test.timer"]["avg_ms"] == 75.0
