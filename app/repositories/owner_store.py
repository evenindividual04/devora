from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import AnalysisOwnerORM, ShareOwnerORM
from app.db.session import SessionLocal


class OwnerStore:
    async def bind_analysis(self, analysis_id: str, user_id: str) -> None:
        async with SessionLocal() as session:
            session.add(AnalysisOwnerORM(analysis_id=analysis_id, user_id=user_id, created_at=datetime.now(UTC)))
            await session.commit()

    async def owns_analysis(self, analysis_id: str, user_id: str) -> bool:
        async with SessionLocal() as session:
            res = await session.execute(select(AnalysisOwnerORM).where(AnalysisOwnerORM.analysis_id == analysis_id, AnalysisOwnerORM.user_id == user_id))
            return res.scalar_one_or_none() is not None

    async def list_analysis_ids(self, user_id: str) -> list[str]:
        async with SessionLocal() as session:
            res = await session.execute(select(AnalysisOwnerORM.analysis_id).where(AnalysisOwnerORM.user_id == user_id))
            return [row[0] for row in res.all()]

    async def bind_share(self, token_id: str, user_id: str) -> None:
        async with SessionLocal() as session:
            session.add(ShareOwnerORM(token_id=token_id, user_id=user_id, created_at=datetime.now(UTC)))
            await session.commit()

    async def owns_share(self, token_id: str, user_id: str) -> bool:
        async with SessionLocal() as session:
            res = await session.execute(select(ShareOwnerORM).where(ShareOwnerORM.token_id == token_id, ShareOwnerORM.user_id == user_id))
            return res.scalar_one_or_none() is not None

    async def list_share_token_ids(self, user_id: str) -> list[str]:
        async with SessionLocal() as session:
            res = await session.execute(select(ShareOwnerORM.token_id).where(ShareOwnerORM.user_id == user_id))
            return [row[0] for row in res.all()]


owner_store = OwnerStore()
