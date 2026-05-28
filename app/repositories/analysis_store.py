from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.db.models import AnalysisORM
from app.db.session import SessionLocal
from app.models.contracts import AnalysisRecord


class AnalysisStore:
    async def create(self, record: AnalysisRecord) -> AnalysisRecord:
        async with SessionLocal() as session:
            orm = AnalysisORM(
                analysis_id=str(record.analysis_id),
                username=record.username,
                scope=record.scope.value,
                honesty_mode=record.honesty_mode.value,
                output_targets=json.dumps([t.value for t in record.output_targets]),
                include_private=record.include_private,
                status=record.status,
                attempts=record.attempts,
                failure_reason=record.failure_reason,
                last_duration_ms=record.last_duration_ms,
                next_attempt_at=None,
                created_at=record.created_at,
                updated_at=record.updated_at,
                payload_json=record.model_dump_json(),
                idempotency_key=record.meta.get("idempotency_key", ""),
            )
            session.add(orm)
            await session.commit()
        return record

    async def get(self, analysis_id: UUID) -> AnalysisRecord | None:
        async with SessionLocal() as session:
            res = await session.execute(select(AnalysisORM).where(AnalysisORM.analysis_id == str(analysis_id)))
            orm = res.scalar_one_or_none()
            if not orm:
                return None
            return AnalysisRecord.model_validate_json(orm.payload_json)

    async def update(self, record: AnalysisRecord) -> AnalysisRecord:
        record.updated_at = datetime.now(UTC)
        async with SessionLocal() as session:
            res = await session.execute(select(AnalysisORM).where(AnalysisORM.analysis_id == str(record.analysis_id)))
            orm = res.scalar_one_or_none()
            if not orm:
                raise ValueError("analysis record not found")
            orm.status = record.status
            orm.attempts = record.attempts
            orm.failure_reason = record.failure_reason
            orm.last_duration_ms = record.last_duration_ms
            orm.updated_at = record.updated_at
            orm.payload_json = record.model_dump_json()
            await session.commit()
        return record

    async def get_by_idempotency_key(self, key: str) -> AnalysisRecord | None:
        async with SessionLocal() as session:
            res = await session.execute(select(AnalysisORM).where(AnalysisORM.idempotency_key == key))
            orm = res.scalar_one_or_none()
            if not orm:
                return None
            return AnalysisRecord.model_validate_json(orm.payload_json)

    async def list_completed(self, limit: int = 500) -> list[AnalysisRecord]:
        async with SessionLocal() as session:
            res = await session.execute(
                select(AnalysisORM)
                .where(AnalysisORM.status == "completed")
                .order_by(AnalysisORM.updated_at.desc())
                .limit(limit)
            )
            rows = res.scalars().all()
            return [AnalysisRecord.model_validate_json(row.payload_json) for row in rows]

    async def list_failed_permanent(self, limit: int = 100) -> list[dict]:
        async with SessionLocal() as session:
            res = await session.execute(
                select(AnalysisORM)
                .where(AnalysisORM.status == "failed_permanent")
                .order_by(AnalysisORM.updated_at.desc())
                .limit(limit)
            )
            rows = res.scalars().all()
            return [
                {
                    "analysis_id": row.analysis_id,
                    "username": row.username,
                    "status": row.status,
                    "attempts": row.attempts,
                    "failure_reason": row.failure_reason,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ]


store = AnalysisStore()
