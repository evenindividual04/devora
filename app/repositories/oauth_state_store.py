from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from app.db.models import OAuthStateORM
from app.db.session import SessionLocal


class OAuthStateStore:
    async def create_state(self, state: str, username: str, ttl_minutes: int = 10) -> None:
        now = datetime.now(UTC)
        async with SessionLocal() as session:
            session.add(
                OAuthStateORM(
                    state=state,
                    username=username,
                    created_at=now,
                    expires_at=now + timedelta(minutes=ttl_minutes),
                )
            )
            await session.commit()

    async def consume_state(self, state: str) -> str | None:
        now = datetime.now(UTC)
        async with SessionLocal() as session:
            res = await session.execute(select(OAuthStateORM).where(OAuthStateORM.state == state))
            row = res.scalar_one_or_none()
            if not row:
                return None
            expires_at = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
            if expires_at < now:
                await session.execute(delete(OAuthStateORM).where(OAuthStateORM.state == state))
                await session.commit()
                return None

            username = row.username
            await session.execute(delete(OAuthStateORM).where(OAuthStateORM.state == state))
            await session.commit()
            return username


oauth_state_store = OAuthStateStore()
