"""Pydantic schemas for emergency workflow."""

from datetime import datetime

from pydantic import BaseModel, Field


class EmergencyContact(BaseModel):
    """A simulated emergency contact."""

    name: str
    relationship: str
    phone: str
    notified: bool = False
    notified_at: datetime | None = None


class EmergencyTriggerRequest(BaseModel):
    """Request to trigger the emergency workflow."""

    trigger_text: str = Field(
        default="Emergency assistance requested",
        description="What triggered the emergency (voice text or manual button)",
    )
    severity: str = Field(
        default="HIGH",
        description="Severity level: LOW, MEDIUM, HIGH, CRITICAL",
    )


class EmergencyEventResponse(BaseModel):
    """Public representation of an emergency event."""

    id: int
    trigger_text: str
    status: str
    severity: str
    category: str | None = None
    contacts: list[EmergencyContact]
    notes: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}


class EmergencyUpdateRequest(BaseModel):
    """Request to update an emergency event status."""

    status: str = Field(
        ..., description="New status: ACKNOWLEDGED, CANCELLED, COMPLETED"
    )
    notes: str | None = None


class EmergencyDetectionResponse(BaseModel):
    """Structured output from the emergency detector."""

    is_emergency: bool = Field(default=False, description="Whether an emergency was detected")
    category: str = Field(default="UNKNOWN", description="Emergency category: FALL, BREATHING, PAIN, GENERAL_DISTRESS, CALL_FOR_HELP")
    severity: str = Field(default="MEDIUM", description="Severity: LOW, MEDIUM, HIGH, CRITICAL")
    matched_pattern: str = Field(default="", description="The phrase that triggered detection")
    detection_reason: str = Field(default="", description="Explanation of why this was or was not classified as emergency")
    recommended_response: str = Field(default="", description="Suggested response message")
    requires_clarification: bool = Field(default=False, description="Whether the system should ask for confirmation")
    clarification_prompt: str | None = Field(default=None, description="Clarification question if applicable")
    is_negated: bool = Field(default=False, description="Whether the emergency phrase was negated")
    is_hypothetical: bool = Field(default=False, description="Whether the statement was hypothetical/question")
