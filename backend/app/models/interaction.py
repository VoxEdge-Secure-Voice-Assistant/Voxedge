"""Interaction and ActivityLog ORM models."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Interaction(Base):
    """
    One voice/text interaction — everything from raw input to final decision.

    Each row captures the complete lifecycle:
      raw_text → intent → decision → execution result
    """

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Group related interactions (e.g. a command + its clarification response)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Optional user ownership for multi-user isolation
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True, index=True
    )

    # ── Input ──────────────────────────────────────────────────────────────
    # raw_text: what the user typed (text mode) or the original audio transcription
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    recognized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="text"
    )  # "voice" or "text"

    # ── Intent ─────────────────────────────────────────────────────────────
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    speech_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Speaker verification ───────────────────────────────────────────────
    speaker_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    speaker_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ── Decision ───────────────────────────────────────────────────────────
    decision_outcome: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # EXECUTE, CLARIFY, REJECT, ESCALATE
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_device_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("devices.id"), nullable=True
    )
    requested_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    requires_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    clarification_question: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Execution ──────────────────────────────────────────────────────────
    execution_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # SUCCESS, FAILED, PENDING, SKIPPED
    execution_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Context links ──────────────────────────────────────────────────────
    is_follow_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    parent_interaction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("interactions.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<Interaction {self.id} intent={self.intent} "
            f"decision={self.decision_outcome}>"
        )


class ActivityLog(Base):
    """Log of device state changes — one row per action executed."""

    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    interaction_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("interactions.id"), nullable=True
    )
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.id"), nullable=False
    )

    action: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_state: Mapped[str] = mapped_column(String(16), nullable=False)
    new_state: Mapped[str] = mapped_column(String(16), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<ActivityLog {self.id} device={self.device_id} "
            f"{self.previous_state}→{self.new_state}>"
        )
