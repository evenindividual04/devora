from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core.config import settings


class ShareTokenService:
    def __init__(self) -> None:
        self._secret = settings.share_token_secret.encode("utf-8")

    def _sign(self, payload: str) -> str:
        return hmac.new(self._secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()

    def create(self, analysis_id: str, ttl_minutes: int | None = None, version: int = 1) -> tuple[str, str, datetime]:
        token_id = uuid4().hex
        expiry = datetime.now(UTC) + timedelta(minutes=ttl_minutes or settings.share_token_ttl_minutes)
        payload = {"tid": token_id, "aid": analysis_id, "exp": int(expiry.timestamp()), "v": version}
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")
        sig = self._sign(payload_b64)
        return token_id, f"{payload_b64}.{sig}", expiry

    def verify(self, token: str) -> dict | None:
        if "." not in token:
            return None
        payload_b64, sig = token.split(".", 1)
        if not hmac.compare_digest(self._sign(payload_b64), sig):
            return None
        try:
            padded = payload_b64 + "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
        except Exception:
            return None
        if payload.get("exp", 0) < int(datetime.now(UTC).timestamp()):
            return None
        return payload


share_token_service = ShareTokenService()
