from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import OAuthTokenORM
from app.db.session import SessionLocal
from app.services.crypto_service import decrypt_text, encrypt_text


class OAuthStore:
    async def upsert_token(self, username: str, access_token: str, token_type: str, scope: str) -> None:
        async with SessionLocal() as session:
            res = await session.execute(select(OAuthTokenORM).where(OAuthTokenORM.username == username))
            row = res.scalar_one_or_none()
            enc = encrypt_text(access_token)
            if row:
                row.access_token = enc
                row.token_type = token_type
                row.scope = scope
                row.updated_at = datetime.now(UTC)
            else:
                session.add(
                    OAuthTokenORM(
                        username=username,
                        access_token=enc,
                        token_type=token_type,
                        scope=scope,
                        updated_at=datetime.now(UTC),
                    )
                )
            await session.commit()

    async def get_token(self, username: str) -> str | None:
        async with SessionLocal() as session:
            res = await session.execute(select(OAuthTokenORM).where(OAuthTokenORM.username == username))
            row = res.scalar_one_or_none()
            return decrypt_text(row.access_token) if row else None

    async def get_scope(self, username: str) -> str:
        async with SessionLocal() as session:
            res = await session.execute(select(OAuthTokenORM).where(OAuthTokenORM.username == username))
            row = res.scalar_one_or_none()
            return row.scope if row else ""


oauth_store = OAuthStore()
