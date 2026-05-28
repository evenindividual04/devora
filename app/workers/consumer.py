from __future__ import annotations

import asyncio
from uuid import UUID

from app.core.config import settings
from app.core.metrics import metrics
from app.queue.manager import queue_manager
from app.repositories.analysis_store import store
from app.workers.pipeline import worker


class WorkerConsumer:
    def __init__(self) -> None:
        self._running = False

    async def run_forever(self) -> None:
        self._running = True
        while self._running:
            analysis_id = await queue_manager.dequeue(timeout_seconds=2)
            if not analysis_id:
                continue

            record = await store.get(UUID(analysis_id))
            if not record or record.status in {"completed", "failed_permanent"}:
                continue

            if record.status == "analyzing":
                # idempotency guard against concurrent duplicate processing
                continue

            try:
                record.attempts += 1
                await worker.run(record)
            except Exception as exc:
                record.failure_reason = str(exc)
                if record.attempts >= settings.worker_max_attempts:
                    record.status = "failed_permanent"
                else:
                    record.status = "queued"
                    backoff = settings.worker_base_backoff_seconds * (2 ** (record.attempts - 1))
                    await asyncio.sleep(backoff)
                    await queue_manager.enqueue(str(record.analysis_id))
                metrics.incr("analysis.failed")
                await store.update(record)

    async def stop(self) -> None:
        self._running = False
        await asyncio.sleep(0)


consumer = WorkerConsumer()
