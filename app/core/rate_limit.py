from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.core.config import settings


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.time()
        window_start = now - 60
        q = self._hits[key]
        while q and q[0] < window_start:
            q.popleft()
        if len(q) >= settings.rate_limit_per_minute:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        q.append(now)


rate_limiter = InMemoryRateLimiter()
