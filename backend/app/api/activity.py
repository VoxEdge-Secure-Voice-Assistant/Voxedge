"""
Activity API — retrieve interaction and device-action history.

GET /activity
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_optional_user
from app.database.session import get_db
from app.models.interaction import ActivityLog, Interaction
from app.models.user import User
from app.schemas.interaction import (
    ActivityEntry,
    ActivityResponse,
    InteractionSummary,
)

router = APIRouter(tags=["activity"])


@router.get("/activity", response_model=ActivityResponse)
def get_activity(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Retrieve recent interactions and device actions isolated to current user."""
    query = db.query(Interaction)
    if current_user:
        if current_user.username == "user":
            query = query.filter((Interaction.user_id == current_user.id) | (Interaction.user_id.is_(None)))
        else:
            query = query.filter(Interaction.user_id == current_user.id)

    interactions = (
        query
        .order_by(Interaction.created_at.desc())
        .limit(limit)
        .all()
    )
    actions = (
        db.query(ActivityLog)
        .order_by(ActivityLog.created_at.desc())
        .limit(limit)
        .all()
    )

    return ActivityResponse(
        interactions=[InteractionSummary.model_validate(i) for i in interactions],
        device_actions=[ActivityEntry.model_validate(a) for a in actions],
        total_interactions=query.count(),
        total_actions=db.query(ActivityLog).count(),
    )
