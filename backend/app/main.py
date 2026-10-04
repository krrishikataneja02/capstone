"""
FastAPI application entry point for the Digital Twin of a University.

- CORS for the Next.js frontend
- Background telemetry simulator (opt-in via SIMULATOR_ENABLED)
- Router registration
- WebSocket /ws/live endpoint with JWT auth
- /health endpoint with database + Redis status
- Redis init / shutdown in lifespan
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import get_db
from app.models import User
from app.security import decode_access_token
from app.ws import manager

logger = logging.getLogger("digital_twin")

# ---------------------------------------------------------------------------
# Background simulator
# ---------------------------------------------------------------------------

_simulator_task: asyncio.Task | None = None


async def _simulator_loop() -> None:
    """Periodically fire a telemetry tick when SIMULATOR_ENABLED is True."""
    from app.routers.ingestion import _perform_tick  # deferred to avoid circular

    while True:
        try:
            await asyncio.to_thread(_perform_tick)
        except Exception:
            logger.exception("Simulator tick failed")
        await asyncio.sleep(settings.SIMULATOR_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _simulator_task

    # --- Redis init (non-blocking, optional) ---
    from app.redis_client import init_redis, close_redis
    init_redis()

    if settings.SIMULATOR_ENABLED:
        _simulator_task = asyncio.create_task(_simulator_loop())
        logger.info("Background simulator started (interval=%ds)", settings.SIMULATOR_INTERVAL_SECONDS)

    yield

    if _simulator_task is not None:
        _simulator_task.cancel()
        with suppress(asyncio.CancelledError):
            await _simulator_task
        _simulator_task = None

    # --- Redis shutdown ---
    await close_redis()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Digital Twin of a University",
    version="1.0.0",
    description="Real-time monitoring, predictive analytics, simulation and optimization of campus operations.",
    lifespan=lifespan,
)

# CORS
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
_allow_credentials = "*" not in _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from app.routers.auth import router as auth_router        # noqa: E402
from app.routers.crud import router as crud_router        # noqa: E402
from app.routers.twin import router as twin_router        # noqa: E402
from app.routers.ingestion import router as ingestion_router  # noqa: E402
from app.routers.analytics import router as analytics_router  # noqa: E402

app.include_router(auth_router)
app.include_router(crud_router)
app.include_router(twin_router)
app.include_router(ingestion_router)
app.include_router(analytics_router)


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws/live")
async def websocket_live(
    ws: WebSocket,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    WebSocket endpoint for real-time broadcasts.
    Requires a valid JWT token as a query parameter.
    """
    import jwt as pyjwt

    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        if sub is None:
            await ws.close(code=4001, reason="Invalid token")
            return
        try:
            user_id = int(sub)
        except (ValueError, TypeError):
            await ws.close(code=4001, reason="Invalid token")
            return
        active_user = db.query(User).filter(User.id == user_id, User.is_active.is_(True)).first()
        if active_user is None:
            await ws.close(code=4001, reason="Invalid or inactive user")
            return
    except pyjwt.ExpiredSignatureError:
        await ws.close(code=4001, reason="Token expired")
        return
    except pyjwt.InvalidTokenError:
        await ws.close(code=4001, reason="Invalid or expired token")
        return

    await manager.connect(ws)
    try:
        while True:
            # Keep connection alive; we only broadcast, not receive
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
async def health_check(db: Session = Depends(get_db)):
    from app.redis_client import redis_health

    app_status = "ok"
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unavailable"

    redis_status = redis_health()["status"]
    overall = "ok" if db_status == "ok" else "unhealthy"

    return {
        "status": overall,
        "application": app_status,
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "database": db_status,
        "redis": redis_status,
    }
