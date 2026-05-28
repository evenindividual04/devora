from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import ShareORM
from app.db.session import SessionLocal


class ShareStore:
    async def create(self, token_id: str, analysis_id: str, expires_at: datetime, token_version: int = 1) -> None:
        async with SessionLocal() as session:
            session.add(
                ShareORM(
                    token_id=token_id,
                    analysis_id=analysis_id,
                    token_version=token_version,
                    expires_at=expires_at,
                    revoked=False,
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()

    async def get(self, token_id: str) -> ShareORM | None:
        async with SessionLocal() as session:
            res = await session.execute(select(ShareORM).where(ShareORM.token_id == token_id))
            return res.scalar_one_or_none()

    async def revoke(self, token_id: str) -> bool:
        async with SessionLocal() as session:
            res = await session.execute(select(ShareORM).where(ShareORM.token_id == token_id))
            row = res.scalar_one_or_none()
            if not row:
                return False
            row.revoked = True
            await session.commit()
            return True

    async def is_valid(self, token_id: str) -> bool:
        row = await self.get(token_id)
        if not row:
            return False
        expires_ts = row.expires_at.replace(tzinfo=UTC).timestamp() if row.expires_at.tzinfo is None else row.expires_at.timestamp()
        return (not row.revoked) and expires_ts > datetime.now(UTC).timestamp()

    async def list_by_token_ids(self, token_ids: list[str]) -> list[dict]:
        if not token_ids:
            return []
        async with SessionLocal() as session:
            res = await session.execute(select(ShareORM).where(ShareORM.token_id.in_(token_ids)).order_by(ShareORM.created_at.desc()))
            rows = res.scalars().all()
            return [
                {
                    "token_id": r.token_id,
                    "analysis_id": r.analysis_id,
                    "token_version": r.token_version,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                    "revoked": r.revoked,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]


share_store = ShareStore()
