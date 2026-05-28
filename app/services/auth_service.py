from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def hash_password(self, password: str) -> str:
        return pwd.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        return pwd.verify(password, password_hash)

    def issue_access_token(self, user_id: str, role: str) -> str:
        exp = datetime.now(UTC) + timedelta(minutes=settings.access_token_ttl_minutes)
        payload = {"sub": user_id, "role": role, "exp": int(exp.timestamp()), "typ": "access"}
        return jwt.encode(payload, settings.access_token_secret, algorithm="HS256")

    def issue_refresh_token(self, user_id: str) -> tuple[str, str, datetime]:
        jti = hashlib.sha256(f"{user_id}:{uuid4().hex}".encode("utf-8")).hexdigest()
        exp = datetime.now(UTC) + timedelta(minutes=settings.refresh_token_ttl_minutes)
        payload = {"sub": user_id, "jti": jti, "exp": int(exp.timestamp()), "typ": "refresh"}
        token = jwt.encode(payload, settings.refresh_token_secret, algorithm="HS256")
        return token, jti, exp

    def decode_access(self, token: str) -> dict:
        return jwt.decode(token, settings.access_token_secret, algorithms=["HS256"])

    def decode_refresh(self, token: str) -> dict:
        return jwt.decode(token, settings.refresh_token_secret, algorithms=["HS256"])


auth_service = AuthService()
