"""Pydantic schemas for voice processing API."""

from pydantic import BaseModel, Field

from app.schemas.emergency import EmergencyDetectionResponse


class EnrollmentStatusResponse(BaseModel):
    """Voice enrollment status response."""

    is_enrolled: bool
    similarity_threshold: float
    message: str


class VoiceEnrollResponse(BaseModel):
    """Response after voice enrollment."""

    success: bool
    is_enrolled: bool
    message: str
    dimensions: int | None = None
    similarity_threshold: float | None = None
    auth_token: str | None = None


class VoiceProcessRequest(BaseModel):
    """Request to process a voice command (text mode for Phase 2)."""

    text: str = Field(..., min_length=1, description="Transcribed or typed command text")
    input_mode: str = Field(
        default="text",
        description="'voice' if from microphone, 'text' if typed",
    )
    session_id: str | None = Field(
        default=None,
        description="Session ID for context continuity; auto-generated if omitted",
    )


class StructuredIntent(BaseModel):
    """Structured representation of recognized natural language intent."""

    raw_text: str = Field(..., description="Original transcribed or typed text")
    intent: str = Field(..., description="Intent category: CONTROL_DEVICE, STATUS_CHECK, EMERGENCY, HELP, CANCEL, CONFIRM, UNKNOWN")
    device: str | None = Field(default=None, description="Identified target device ID or device category")
    device_type: str | None = Field(default=None, description="Category of device (light, fan, etc.)")
    location: str | None = Field(default=None, description="Location of device (bedroom, living_room, etc.)")
    action: str | None = Field(default=None, description="Requested action: ON, OFF, etc.")
    is_ambiguous: bool = Field(default=False, description="Whether the command or device is ambiguous")
    requires_clarification: bool = Field(default=False, description="Whether clarification is required before action")
    clarification_prompt: str | None = Field(default=None, description="Suggested clarification question")
    confidence: float = Field(default=0.0, description="Confidence score 0.0 - 1.0")
    reason: str = Field(default="", description="Reason for the decision or interpretation")
    is_indirect: bool = Field(default=False, description="Whether this was an indirect natural-language statement")
    suggested_action: str | None = Field(default=None, description="Suggested action for indirect statements")
    suggested_device: str | None = Field(default=None, description="Suggested device for indirect statements")


class IntentResult(BaseModel):
    """Parsed intent with entities."""

    intent: str
    confidence: float
    entities: dict
    raw_text: str


class VoiceProcessResponse(BaseModel):
    """Full response from voice command processing."""

    interaction_id: int
    session_id: str

    # What was understood
    recognized_text: str
    intent: str | None = None
    intent_confidence: float | None = None
    entities: dict = {}
    structured_intent: StructuredIntent | None = None
    slm_proposal: dict | None = None
    is_ambiguous: bool = False
    requires_clarification: bool = False

    # Speaker verification
    speaker_verified: bool | None = None
    speaker_similarity: float | None = None
    similarity_threshold: float | None = None
    auth_token: str | None = None

    # Decision
    decision: str  # EXECUTE, CLARIFY, REJECT, ESCALATE
    decision_reason: str

    # Execution result (if EXECUTE)
    target_device: str | None = None
    requested_action: str | None = None
    execution_status: str | None = None
    new_device_state: str | None = None

    # Clarification (if CLARIFY)
    clarification_question: str | None = None
    requires_confirmation: bool = False

    # System message to display
    message: str

    # Emergency detection (populated when emergency detector runs)
    emergency_detection: EmergencyDetectionResponse | None = None
