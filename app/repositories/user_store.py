from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import UserORM
from app.db.session import SessionLocal


class UserStore:
    async def create(self, email: str, password_hash: str, role: str = "user") -> UserORM:
        async with SessionLocal() as session:
            user = UserORM(email=email, password_hash=password_hash, role=role, created_at=datetime.now(UTC))
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def get_by_email(self, email: str) -> UserORM | None:
        async with SessionLocal() as session:
            res = await session.execute(select(UserORM).where(UserORM.email == email))
            return res.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> UserORM | None:
        async with SessionLocal() as session:
            res = await session.execute(select(UserORM).where(UserORM.user_id == user_id))
            return res.scalar_one_or_none()


user_store = UserStore()
