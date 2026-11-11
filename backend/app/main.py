"""
VoxEdge Phase 2 — FastAPI application entry point.

Run with:
    cd backend
    uvicorn app.main:app --reload
"""

import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.database.session import SessionLocal, init_db
from app.models.device import Device

# ── Import routers (added as they are implemented) ────────────────────────────
from app.api import activity as activity_router
from app.api import auth as auth_router
from app.api import decisions as decisions_router
from app.api import devices as devices_router
from app.api import emergency as emergency_router
from app.api import evaluation as evaluation_router
from app.api import system as system_router
from app.api import voice as voice_router

# ── Startup timestamp (for uptime calculation) ────────────────────────────────
_start_time: float = 0.0

# ── Default devices to seed on first run ──────────────────────────────────────
DEFAULT_DEVICES = [
    {
        "id": "bedroom_light",
        "name": "Bedroom Light",
        "device_type": "light",
        "location": "bedroom",
        "state": "OFF",
        "supported_actions": '["ON", "OFF"]',
    },
    {
        "id": "living_room_light",
        "name": "Living Room Light",
        "device_type": "light",
        "location": "living_room",
        "state": "OFF",
        "supported_actions": '["ON", "OFF"]',
    },
    {
        "id": "fan",
        "name": "Fan",
        "device_type": "fan",
        "location": "bedroom",
        "state": "OFF",
        "supported_actions": '["ON", "OFF"]',
    },
]


def _seed_devices() -> None:
    """Insert default devices if the table is empty."""
    db = SessionLocal()
    try:
        if db.query(Device).count() == 0:
            for dev_data in DEFAULT_DEVICES:
                db.add(Device(**dev_data))
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    global _start_time
    _start_time = time.time()

    # Create tables + seed defaults
    init_db()
    _seed_devices()

    yield  # ← application runs here

    # Shutdown cleanup (if needed in future)


def get_start_time() -> float:
    return _start_time


# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="VoxEdge — Reliability-Aware Voice Assistant",
    description=(
        "Phase 2 backend for VoxEdge: a reliability-aware, voice-based "
        "assistive system for elderly and bedridden users."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register routers ─────────────────────────────────────────────────────────
# Mount directly for internal routes & tests
app.include_router(auth_router.router)
app.include_router(voice_router.router)
app.include_router(devices_router.router)
app.include_router(decisions_router.router)
app.include_router(activity_router.router)
app.include_router(emergency_router.router)
app.include_router(evaluation_router.router)
app.include_router(system_router.router)

# Mount also under /api prefix for direct API callers
api_router_list = [
    auth_router.router,
    voice_router.router,
    devices_router.router,
    decisions_router.router,
    activity_router.router,
    emergency_router.router,
    evaluation_router.router,
    system_router.router,
]
for r in api_router_list:
    app.include_router(r, prefix="/api")


@app.get("/", tags=["root"])
async def root():
    """Health-check root."""
    return {
        "name": "VoxEdge",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
    }
