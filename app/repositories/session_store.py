from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import SessionORM
from app.db.session import SessionLocal


class SessionStore:
    async def create(self, user_id: str, refresh_jti: str, expires_at: datetime) -> SessionORM:
        async with SessionLocal() as session:
            row = SessionORM(user_id=user_id, refresh_jti=refresh_jti, expires_at=expires_at, revoked=False, created_at=datetime.now(UTC))
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def get_by_jti(self, refresh_jti: str) -> SessionORM | None:
        async with SessionLocal() as session:
            res = await session.execute(select(SessionORM).where(SessionORM.refresh_jti == refresh_jti))
            return res.scalar_one_or_none()

    async def revoke(self, refresh_jti: str) -> None:
        async with SessionLocal() as session:
            res = await session.execute(select(SessionORM).where(SessionORM.refresh_jti == refresh_jti))
            row = res.scalar_one_or_none()
            if row:
                row.revoked = True
                await session.commit()

    async def is_active(self, refresh_jti: str) -> bool:
        row = await self.get_by_jti(refresh_jti)
        if not row:
            return False
        exp = row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
        return (not row.revoked) and exp > datetime.now(UTC)


session_store = SessionStore()
