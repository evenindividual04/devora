from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.repositories.user_store import user_store
from app.services.auth_service import auth_service


@dataclass
class CurrentUser:
    user_id: str
    role: str
    email: str


bearer = HTTPBearer(auto_error=False)


async def require_api_key(x_api_key: str = Header(default="")) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid api key")


async def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> CurrentUser:
    if not credentials:
        raise HTTPException(status_code=401, detail="authentication required")
    try:
        payload = auth_service.decode_access(credentials.credentials)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid access token") from exc

    user_id = payload.get("sub", "")
    role = payload.get("role", "user")
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid access token")

    user = await user_store.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="user not found")
    return CurrentUser(user_id=user.user_id, role=role, email=user.email)


async def get_optional_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> CurrentUser | None:
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


async def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="admin access required")
    return user
