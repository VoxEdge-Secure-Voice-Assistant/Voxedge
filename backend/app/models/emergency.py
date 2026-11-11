"""EmergencyEvent ORM model."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmergencyEvent(Base):
    """A triggered emergency assistance event."""

    __tablename__ = "emergency_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Optional link to the interaction that triggered this emergency
    interaction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("interactions.id"), nullable=True
    )

    # Optional user ownership for multi-user isolation
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )

    trigger_text: Mapped[str] = mapped_column(Text, nullable=False)

    # ACTIVE → ACKNOWLEDGED → COMPLETED  or  ACTIVE → CANCELLED
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ACTIVE"
    )

    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default="HIGH"
    )  # LOW, MEDIUM, HIGH, CRITICAL

    # Emergency category: FALL, BREATHING, PAIN, GENERAL_DISTRESS, CALL_FOR_HELP, UNKNOWN
    category: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None
    )

    # JSON list of simulated contacts, e.g. '[{"name": "Dr. Sharma", ...}]'
    contacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<EmergencyEvent {self.id} status={self.status}>"
