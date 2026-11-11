"""System status API route."""

import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_optional_user
from app.core.config import settings
from app.database.session import get_db
from app.models.device import Device
from app.models.emergency import EmergencyEvent
from app.models.interaction import Interaction
from app.models.user import User
from app.schemas.system import SystemStatusResponse
from app.services.user_service import UserService

router = APIRouter(tags=["system"])


@router.get("/system/status", response_model=SystemStatusResponse)
def system_status(
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Retrieve system health and user-specific status information."""
    from app.main import get_start_time
    from app.services.voice_auth_service import VoiceAuthService

    start_time = get_start_time()
    vosk_path = settings.get_vosk_model_path()

    if current_user and current_user.username != "user":
        is_enrolled = UserService.is_voice_enrolled(current_user)
        total_interactions = db.query(Interaction).filter(Interaction.user_id == current_user.id).count()
        active_emergencies = (
            db.query(EmergencyEvent)
            .filter(EmergencyEvent.user_id == current_user.id, EmergencyEvent.status == "ACTIVE")
            .count()
        )
    else:
        is_enrolled = VoiceAuthService().is_enrolled()
        total_interactions = db.query(Interaction).count()
        active_emergencies = (
            db.query(EmergencyEvent)
            .filter(EmergencyEvent.status == "ACTIVE")
            .count()
        )

    total_devices = db.query(Device).count()
    active_devices = db.query(Device).filter(Device.is_active.is_(True)).count()

    return SystemStatusResponse(
        status="healthy",
        version="2.0.0",
        vosk_model_loaded=vosk_path.is_dir(),
        voice_enrolled=is_enrolled,
        total_devices=total_devices,
        active_devices=active_devices,
        total_interactions=total_interactions,
        active_emergencies=active_emergencies,
        uptime_seconds=round(time.time() - start_time, 2) if start_time else 0,
        timestamp=datetime.now(timezone.utc),
    )
