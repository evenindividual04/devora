from __future__ import annotations

import secrets
from datetime import UTC, datetime
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.idempotency import build_idempotency_key
from app.core.metrics import metrics
from app.core.rate_limit import rate_limiter
from app.core.security import CurrentUser, get_current_user, get_optional_user, require_admin
from app.db.session import db_ping
from app.models.contracts import (
    AnalysisRecord,
    AnalysisRunRequest,
    AnalysisRunResponse,
    AnalysisStatus,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthTokenResponse,
    DataScope,
    RefreshRequest,
    ShareCreateRequest,
    ShareCreateResponse,
    SharedReportResponse,
)
from app.queue.manager import queue_manager
from app.repositories.analysis_store import store
from app.repositories.audit_store import audit_store
from app.repositories.owner_store import owner_store
from app.repositories.oauth_state_store import oauth_state_store
from app.repositories.oauth_store import oauth_store
from app.repositories.session_store import session_store
from app.repositories.share_store import share_store
from app.repositories.user_store import user_store
from app.services.auth_service import auth_service
from app.services.share_token_service import share_token_service

router = APIRouter()
analysis_router = APIRouter(prefix="/analysis", tags=["analysis"])
auth_router = APIRouter(prefix="/auth", tags=["auth"])
share_router = APIRouter(prefix="/share", tags=["share"])
shares_router = APIRouter(prefix="/shares", tags=["share"])
ops_router = APIRouter(prefix="/ops", tags=["ops"])
health_router = APIRouter(prefix="/health", tags=["health"])


def _rate_key(request: Request, user_id: str | None = None) -> str:
    ip = request.client.host if request.client else "-"
    return f"{user_id or 'anon'}:{ip}:{request.url.path}"


@auth_router.post("/register", response_model=AuthTokenResponse)
async def register(payload: AuthRegisterRequest, request: Request):
    rate_limiter.check(_rate_key(request))
    existing = await user_store.get_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=409, detail="email already exists")
    user = await user_store.create(payload.email, auth_service.hash_password(payload.password), role="user")
    access = auth_service.issue_access_token(user.user_id, user.role)
    refresh, jti, exp = auth_service.issue_refresh_token(user.user_id)
    await session_store.create(user.user_id, jti, exp)
    return AuthTokenResponse(access_token=access, refresh_token=refresh)


@auth_router.post("/login", response_model=AuthTokenResponse)
async def login(payload: AuthLoginRequest, request: Request):
    rate_limiter.check(_rate_key(request))
    user = await user_store.get_by_email(payload.email)
    if not user or not auth_service.verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    access = auth_service.issue_access_token(user.user_id, user.role)
    refresh, jti, exp = auth_service.issue_refresh_token(user.user_id)
    await session_store.create(user.user_id, jti, exp)
    return AuthTokenResponse(access_token=access, refresh_token=refresh)


@auth_router.post("/refresh", response_model=AuthTokenResponse)
async def refresh(payload: RefreshRequest, request: Request):
    rate_limiter.check(_rate_key(request))
    try:
        decoded = auth_service.decode_refresh(payload.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc

    jti = decoded.get("jti", "")
    user_id = decoded.get("sub", "")
    if not jti or not user_id or not await session_store.is_active(jti):
        raise HTTPException(status_code=401, detail="refresh session invalid")

    user = await user_store.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="user not found")

    access = auth_service.issue_access_token(user.user_id, user.role)
    new_refresh, new_jti, exp = auth_service.issue_refresh_token(user.user_id)
    await session_store.revoke(jti)
    await session_store.create(user.user_id, new_jti, exp)
    return AuthTokenResponse(access_token=access, refresh_token=new_refresh)


@auth_router.post("/logout")
async def logout(payload: RefreshRequest, _user: CurrentUser = Depends(get_current_user)):
    try:
        decoded = auth_service.decode_refresh(payload.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="invalid refresh token") from exc
    jti = decoded.get("jti", "")
    if jti:
        await session_store.revoke(jti)
    return {"status": "logged_out"}


def _owns_or_public(user: CurrentUser | None, analysis_id: str) -> bool:
    """Logged-in users must own the analysis. Anonymous users access by ID (UUID is the secret)."""
    return user is None


@analysis_router.post("/run", response_model=AnalysisRunResponse)
async def run_analysis(payload: AnalysisRunRequest, request: Request, user: CurrentUser | None = Depends(get_optional_user)) -> AnalysisRunResponse:
    uid = user.user_id if user else (request.client.host if request.client else "anon")
    rate_limiter.check(_rate_key(request, uid))

    if user:
        idempotency_key = build_idempotency_key(payload)
        existing = await store.get_by_idempotency_key(idempotency_key)
        if existing and await owner_store.owns_analysis(str(existing.analysis_id), user.user_id):
            return AnalysisRunResponse(analysis_id=existing.analysis_id, status=existing.status)
    else:
        idempotency_key = ""
        payload = payload.model_copy(update={"include_private": False, "scope": DataScope.public})

    needs_private = payload.include_private or payload.scope == DataScope.private
    if needs_private:
        token = await oauth_store.get_token(payload.username)
        scope = await oauth_store.get_scope(payload.username)
        if not token:
            raise HTTPException(status_code=400, detail="private analysis requested but no OAuth token found")
        if "repo" not in scope:
            raise HTTPException(status_code=403, detail="OAuth token missing required repo scope")

    record = AnalysisRecord(
        username=payload.username,
        scope=payload.scope,
        honesty_mode=payload.honesty_mode,
        output_targets=payload.output_targets,
        include_private=needs_private,
        meta={"idempotency_key": idempotency_key},
    )

    await store.create(record)
    if user:
        await owner_store.bind_analysis(str(record.analysis_id), user.user_id)
        await audit_store.log(user.user_id, "analysis.run", "analysis", str(record.analysis_id), {"username": payload.username})
    await queue_manager.enqueue(str(record.analysis_id))
    metrics.incr("analysis.queued")
    return AnalysisRunResponse(analysis_id=record.analysis_id, status=record.status)


@analysis_router.get("")
async def list_analysis(user: CurrentUser = Depends(get_current_user)):
    ids = await owner_store.list_analysis_ids(user.user_id)
    return {"analysis_ids": ids}


@analysis_router.get("/{analysis_id}")
async def get_analysis(analysis_id: str, user: CurrentUser | None = Depends(get_optional_user)):
    if user and not await owner_store.owns_analysis(analysis_id, user.user_id) and user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    record = await store.get(UUID(analysis_id))
    if not record:
        raise HTTPException(status_code=404, detail="analysis not found")
    return record.model_dump()


@analysis_router.get("/{analysis_id}/status", response_model=AnalysisStatus)
async def get_status(analysis_id: str, user: CurrentUser | None = Depends(get_optional_user)) -> AnalysisStatus:
    if user and not await owner_store.owns_analysis(analysis_id, user.user_id) and user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    record = await store.get(UUID(analysis_id))
    if not record:
        raise HTTPException(status_code=404, detail="analysis not found")
    return AnalysisStatus(analysis_id=record.analysis_id, status=record.status, created_at=record.created_at, updated_at=record.updated_at)


@analysis_router.get("/{analysis_id}/signals")
async def get_signals(analysis_id: str, user: CurrentUser | None = Depends(get_optional_user)):
    if user and not await owner_store.owns_analysis(analysis_id, user.user_id) and user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    record = await store.get(UUID(analysis_id))
    if not record:
        raise HTTPException(status_code=404, detail="analysis not found")
    return {"analysis_id": str(record.analysis_id), "signals": [s.model_dump() for s in record.signals]}


@analysis_router.get("/{analysis_id}/readme")
async def get_readme(analysis_id: str, user: CurrentUser | None = Depends(get_optional_user)):
    if user and not await owner_store.owns_analysis(analysis_id, user.user_id) and user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    record = await store.get(UUID(analysis_id))
    if not record:
        raise HTTPException(status_code=404, detail="analysis not found")
    if not record.readme:
        raise HTTPException(status_code=409, detail="readme not ready")
    return {"analysis_id": str(record.analysis_id), **record.readme.model_dump()}


@analysis_router.get("/{analysis_id}/report")
async def get_report(analysis_id: str, user: CurrentUser | None = Depends(get_optional_user)):
    if user and not await owner_store.owns_analysis(analysis_id, user.user_id) and user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")
    record = await store.get(UUID(analysis_id))
    if not record:
        raise HTTPException(status_code=404, detail="analysis not found")
    if not record.report:
        raise HTTPException(status_code=409, detail="report not ready")
    return {"analysis_id": str(record.analysis_id), "report": record.report.model_dump(), "readme": record.readme.model_dump() if record.readme else None}


@analysis_router.post("/{analysis_id}/share", response_model=ShareCreateResponse)
async def create_share(analysis_id: str, payload: ShareCreateRequest, request: Request, user: CurrentUser = Depends(get_current_user)):
    rate_limiter.check(_rate_key(request, user.user_id))
    if not await owner_store.owns_analysis(analysis_id, user.user_id):
        raise HTTPException(status_code=403, detail="forbidden")
    record = await store.get(UUID(analysis_id))
    if not record or not record.report or not record.readme:
        raise HTTPException(status_code=404, detail="completed analysis not found")

    token_id, token, expires_at = share_token_service.create(analysis_id=analysis_id, ttl_minutes=payload.ttl_minutes)
    await share_store.create(token_id=token_id, analysis_id=analysis_id, expires_at=expires_at)
    await owner_store.bind_share(token_id, user.user_id)
    await audit_store.log(user.user_id, "share.create", "share", token_id, {"analysis_id": analysis_id})
    return ShareCreateResponse(token=token, url=f"{settings.app_base_url}/share/{token}", expires_at=expires_at)


@auth_router.get("/github/login")
async def github_login(username: str = Query(..., min_length=1), _user: CurrentUser = Depends(get_current_user)):
    state = secrets.token_urlsafe(32)
    await oauth_state_store.create_state(state=state, username=username)
    query = urlencode({"client_id": settings.github_client_id, "redirect_uri": settings.github_oauth_redirect_uri, "scope": "repo read:user", "state": state})
    return {"auth_url": f"https://github.com/login/oauth/authorize?{query}", "state": state}


@auth_router.get("/github/callback")
async def github_callback(code: str, state: str, _user: CurrentUser = Depends(get_current_user)):
    username = await oauth_state_store.consume_state(state)
    if not username:
        raise HTTPException(status_code=400, detail="invalid or expired state")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            token_res = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.github_client_id,
                    "client_secret": settings.github_client_secret,
                    "code": code,
                    "redirect_uri": settings.github_oauth_redirect_uri,
                },
            )
            token_res.raise_for_status()
            token_payload = token_res.json()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="github oauth exchange failed") from exc

    access_token = token_payload.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="oauth exchange failed")

    await oauth_store.upsert_token(username=username, access_token=access_token, token_type=token_payload.get("token_type", "bearer"), scope=token_payload.get("scope", ""))
    return {"status": "connected", "username": username, "scope": token_payload.get("scope", ""), "updated_at": datetime.now(UTC).isoformat()}


@share_router.get("/{token}", response_model=SharedReportResponse)
async def get_shared_report(token: str):
    payload = share_token_service.verify(token)
    if not payload:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    token_id = payload.get("tid")
    if not token_id or not await share_store.is_valid(token_id):
        raise HTTPException(status_code=401, detail="revoked or expired token")

    analysis_id = payload.get("aid")
    if not analysis_id:
        raise HTTPException(status_code=400, detail="invalid token payload")

    record = await store.get(UUID(analysis_id))
    if not record or not record.report or not record.readme:
        raise HTTPException(status_code=404, detail="shared report not found")

    return SharedReportResponse(analysis_id=analysis_id, report=record.report, readme=record.readme)


@shares_router.get("")
async def list_shares(user: CurrentUser = Depends(get_current_user)):
    token_ids = await owner_store.list_share_token_ids(user.user_id)
    shares = await share_store.list_by_token_ids(token_ids)
    return {"shares": shares}


@shares_router.post("/{token}/revoke")
async def revoke_share_owner(token: str, user: CurrentUser = Depends(get_current_user)):
    payload = share_token_service.verify(token)
    if not payload:
        raise HTTPException(status_code=400, detail="invalid token")
    token_id = payload.get("tid")
    if not token_id:
        raise HTTPException(status_code=400, detail="invalid token payload")

    owns = await owner_store.owns_share(token_id, user.user_id)
    if not owns and user.role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")

    ok = await share_store.revoke(token_id)
    if not ok:
        raise HTTPException(status_code=404, detail="share token not found")
    await audit_store.log(user.user_id, "share.revoke", "share", token_id, {})
    return {"status": "revoked"}


@ops_router.get("/dead-letter")
async def dead_letter(_admin: CurrentUser = Depends(require_admin), limit: int = 100):
    return {"items": await store.list_failed_permanent(limit=limit)}


@ops_router.post("/requeue/{analysis_id}")
async def requeue(analysis_id: str, admin: CurrentUser = Depends(require_admin)):
    record = await store.get(UUID(analysis_id))
    if not record:
        raise HTTPException(status_code=404, detail="analysis not found")
    record.status = "queued"
    record.failure_reason = ""
    await store.update(record)
    await queue_manager.enqueue(analysis_id)
    await audit_store.log(admin.user_id, "ops.requeue", "analysis", analysis_id, {})
    return {"status": "queued"}


@health_router.get("/live")
async def health_live():
    return {"status": "ok", "service": "github-profile-analyzer"}


@health_router.get("/ready")
async def health_ready():
    db_ok = await db_ping()
    queue_ok = await queue_manager.ping()
    if not db_ok or not queue_ok:
        raise HTTPException(status_code=503, detail={"db": db_ok, "queue": queue_ok})
    return {"status": "ready", "dependencies": {"db": db_ok, "queue": queue_ok}, "metrics": metrics.snapshot()}


@analysis_router.get("/{analysis_id}/eval")
async def get_eval(analysis_id: str, _user=Depends(get_optional_user)):
    """Return cached eval for an analysis, or score on demand."""
    record = await store.get(UUID(analysis_id))
    if not record:
        raise HTTPException(status_code=404, detail="analysis not found")
    if record.eval:
        return record.eval
    if record.status != "completed" or not record.readme:
        raise HTTPException(status_code=404, detail="analysis not yet completed or no readme")
    import asyncio
    import json
    from app.services.eval_service import get_evaluator
    evaluator = get_evaluator()
    signals_json = json.dumps({s.name: s.value for s in record.signals})
    eval_result = await asyncio.to_thread(evaluator.evaluate, record.readme.markdown, signals_json)
    eval_result.analysis_id = record.analysis_id
    record.eval = eval_result
    await store.update(record)
    return eval_result


@ops_router.get("/eval/summary")
async def eval_summary(_admin: CurrentUser = Depends(require_admin)):
    """Admin: per-dimension score distribution + banned-phrase incidence."""
    from app.services.narrative_provider import _BANNED_PHRASES
    records = await store.list_completed(limit=500)
    evals = [r.eval for r in records if r.eval]
    if not evals:
        return {"count": 0, "dimensions": {}, "banned_phrase_incidence": 0.0}

    from collections import defaultdict
    dim_scores: dict[str, list[float]] = defaultdict(list)
    for ev in evals:
        for ds in ev.scores:
            dim_scores[ds.dimension].append(ds.score)

    dimension_summary = {
        dim: {"mean": round(sum(vs) / len(vs), 3), "count": len(vs), "distribution": vs}
        for dim, vs in dim_scores.items()
    }

    # Banned phrase incidence across all readmes
    readmes = [r.readme.markdown for r in records if r.readme]
    flagged = sum(
        1 for rm in readmes
        if any(p.lower() in rm.lower() for p in _BANNED_PHRASES)
    )
    incidence = flagged / max(len(readmes), 1)

    return {
        "count": len(evals),
        "dimensions": dimension_summary,
        "banned_phrase_incidence": round(incidence, 3),
    }


@ops_router.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint(_admin: CurrentUser = Depends(require_admin)):
    snap = metrics.snapshot()
    lines = []
    for key, val in snap.get("counters", {}).items():
        lines.append(f"devora_counter{{name=\"{key}\"}} {val}")
    for key, v in snap.get("timers", {}).items():
        lines.append(f"devora_timer_count{{name=\"{key}\"}} {v.get('count', 0)}")
        lines.append(f"devora_timer_avg_ms{{name=\"{key}\"}} {v.get('avg_ms', 0.0)}")
    return "\n".join(lines) + "\n"


router.include_router(auth_router)
router.include_router(analysis_router)
router.include_router(share_router)
router.include_router(shares_router)
router.include_router(ops_router)
router.include_router(health_router)
