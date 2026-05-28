from __future__ import annotations

import hashlib

from app.models.contracts import AnalysisRunRequest


def build_idempotency_key(payload: AnalysisRunRequest, window: str = "30d") -> str:
    raw = f"{payload.username}|{payload.scope.value}|{payload.honesty_mode.value}|{payload.include_private}|{window}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
