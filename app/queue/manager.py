from __future__ import annotations

import asyncio
import json

from redis.asyncio import Redis

from app.core.config import settings


class QueueManager:
    def __init__(self) -> None:
        self._redis: Redis | None = None
        self._local_queue: asyncio.Queue[str] | None = None
        self._local_loop: asyncio.AbstractEventLoop | None = None

    def _ensure_local_queue(self) -> asyncio.Queue[str]:
        loop = asyncio.get_running_loop()
        if self._local_queue is None or self._local_loop is not loop:
            self._local_queue = asyncio.Queue()
            self._local_loop = loop
        return self._local_queue

    async def _redis_client(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def ping(self) -> bool:
        if not settings.use_redis_queue:
            return True
        try:
            redis = await self._redis_client()
            pong = await redis.ping()
            return bool(pong)
        except Exception:
            return False

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def enqueue(self, analysis_id: str) -> None:
        if settings.use_redis_queue:
            redis = await self._redis_client()
            await redis.rpush("analysis_jobs", json.dumps({"analysis_id": analysis_id}))
            return
        queue = self._ensure_local_queue()
        await queue.put(analysis_id)

    async def dequeue(self, timeout_seconds: int = 2) -> str | None:
        if settings.use_redis_queue:
            redis = await self._redis_client()
            item = await redis.blpop("analysis_jobs", timeout=timeout_seconds)
            if not item:
                return None
            _, payload = item
            return json.loads(payload)["analysis_id"]

        queue = self._ensure_local_queue()
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
        except TimeoutError:
            return None


queue_manager = QueueManager()
