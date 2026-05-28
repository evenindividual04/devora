from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings
from app.core.logging import RequestContextMiddleware, configure_logging
from app.db.session import close_db
from app.queue.manager import queue_manager
from app.workers.consumer import consumer

configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.app_env != "dev":
        if settings.api_key == "devora-local-admin-key" or settings.share_token_secret == "devora-local-share-secret":
            raise RuntimeError("Refusing to start with default API key/share secret outside dev")

    task = None
    if settings.run_worker_in_api:
        task = asyncio.create_task(consumer.run_forever())
    try:
        yield
    finally:
        if task is not None:
            await consumer.stop()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await queue_manager.close()
        await close_db()


app = FastAPI(title="GitHub Profile Analyzer API", version="0.5.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception):
    logger.exception("unhandled_exception", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


app.include_router(router)
