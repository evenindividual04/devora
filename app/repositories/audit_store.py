from __future__ import annotations

import json
from datetime import UTC, datetime

from app.db.models import AuditEventORM
from app.db.session import SessionLocal


class AuditStore:
    async def log(self, actor_user_id: str, action: str, resource_type: str, resource_id: str, metadata: dict | None = None) -> None:
        async with SessionLocal() as session:
            session.add(
                AuditEventORM(
                    actor_user_id=actor_user_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    metadata_json=json.dumps(metadata or {}),
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()


audit_store = AuditStore()
