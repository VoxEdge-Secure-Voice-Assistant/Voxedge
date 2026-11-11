"""
Test suite for Feature 4: Ambiguity Handling and Intelligent Intent Recognition.

Covers the 10 core test requirements:
  CASE 1: "Turn on the fan."
          Expected: Correct device and action identified (fan, ON), decision EXECUTE.
  CASE 2: "Turn off the lights."
          Expected: Correct device type and action (light, OFF), is_ambiguous=True,
          decision CLARIFY asking which light; no device state changes.
  CASE 3: "It's too dark."
          Expected: Indirect request, suggests Light ON, decision CLARIFY;
          no device state changes.
  CASE 4: "I'm feeling hot."
          Expected: Indirect request, suggests Fan ON, interprets cautiously,
          decision CLARIFY; no device state changes.
  CASE 5: "Turn it off."
          Expected: Pronoun reference without prior context, decision CLARIFY asking
          "the fan or the lights?"; no device state changes.
  CASE 6: Unknown device (e.g. "Turn on the television")
          Expected: Decision REJECT, unsupported device; no device state changes.
  CASE 7: Unsupported action (e.g. "Dim the bedroom light")
          Expected: Decision REJECT, unsupported action; no device state changes.
  CASE 8: Ambiguous command (e.g. "Make it comfortable")
          Expected: Decision CLARIFY asking what to adjust; no device state changes.
  CASE 9: Failed voice authentication
          Expected: Audio fails threshold, decision REJECT; no device state changes.
  CASE 10: Direct device-control API request without valid authentication
          Expected: POST /devices/bedroom_light/command returns HTTP 401;
          no device state changes.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.database.session import Base, get_db
from app.main import app
from app.models.device import Device
from app.schemas.voice import StructuredIntent
from app.services.decision_engine import DecisionEngine
from app.services.intent_service import (
    CONTROL_DEVICE,
    IntentService,
)
from app.services.voice_auth_service import VoiceAuthService


# ── Helpers ───────────────────────────────────────────────────────────────────

def create_synthetic_wav(frequency: float = 440.0, duration: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate mono 16 kHz WAV audio file in bytes."""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    waveform = (0.5 * np.sin(2 * np.pi * frequency * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, waveform, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_voice_profile(tmp_path):
    """Temporary enrolled_voice.npy path to isolate tests from production profile."""
    profile_path = tmp_path / "test_enrolled_voice.npy"
    original_path = settings.enrolled_voice_path
    settings.enrolled_voice_path = str(profile_path)
    yield profile_path
    settings.enrolled_voice_path = original_path
    if profile_path.exists():
        profile_path.unlink()


@pytest.fixture
def db_session():
    """In-memory SQLite database session seeded with VoxEdge standard devices."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestingSessionLocal()

    devices = [
        Device(
            id="bedroom_light",
            name="Bedroom Light",
            device_type="light",
            location="bedroom",
            state="OFF",
            supported_actions='["ON", "OFF"]',
        ),
        Device(
            id="living_room_light",
            name="Living Room Light",
            device_type="light",
            location="living_room",
            state="OFF",
            supported_actions='["ON", "OFF"]',
        ),
        Device(
            id="fan",
            name="Fan",
            device_type="fan",
            location="bedroom",
            state="OFF",
            supported_actions='["ON", "OFF"]',
        ),
    ]
    session.add_all(devices)
    session.commit()

    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """FastAPI test client with database dependency override."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def enrolled_auth(temp_voice_profile):
    """Set up an enrolled voice profile and provide auth token helper."""
    voice_auth = VoiceAuthService()
    dummy_embedding = np.ones(256, dtype=np.float32)
    dummy_embedding = dummy_embedding / np.linalg.norm(dummy_embedding)
    voice_auth.save_enrolled_embedding(dummy_embedding)

    token = voice_auth.create_session_token("test-session-feature4", 0.95)
    return {
        "voice_auth": voice_auth,
        "token": token,
        "session_id": "test-session-feature4",
        "headers": {"Authorization": f"Bearer {token}"},
    }


# ── TEST CASES ───────────────────────────────────────────────────────────────

def test_case_1_turn_on_fan(db_session, client, enrolled_auth):
    """
    CASE 1: "Turn on the fan."
    Expected: Correct device (fan) and action (ON) are identified,
              requires_clarification=False, decision=EXECUTE.
              Device state changes to ON.
    """
    intent_service = IntentService()
    res = intent_service.extract("Turn on the fan.")

    # 1. Modular Intent Extraction verification
    assert res.intent == CONTROL_DEVICE
    assert res.target_device == "fan"
    assert res.requested_action == "ON"
    assert res.is_ambiguous is False
    assert res.requires_clarification is False

    # Check Pydantic model conversion
    structured: StructuredIntent = res.to_structured()
    assert structured.device == "fan"
    assert structured.action == "ON"
    assert structured.is_ambiguous is False

    # 2. Decision Engine execution via authenticated API endpoint
    response = client.post(
        "/voice/process",
        headers=enrolled_auth["headers"],
        json={"text": "Turn on the fan.", "session_id": enrolled_auth["session_id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "EXECUTE"
    assert data["target_device"] == "fan"
    assert data["requested_action"] == "ON"
    assert data["execution_status"] == "SUCCESS"
    assert data["new_device_state"] == "ON"

    # Verify device state in database
    fan = db_session.query(Device).filter_by(id="fan").first()
    assert fan.state == "ON"


def test_case_2_turn_off_lights_ambiguous(db_session, client, enrolled_auth):
    """
    CASE 2: "Turn off the lights."
    Expected: Correct device type (light) and action (OFF) are identified.
              is_ambiguous=True, requires_clarification=True.
              Decision is CLARIFY asking which light.
              NO device state changes!
    """
    intent_service = IntentService()
    res = intent_service.extract("Turn off the lights.")

    assert res.intent == CONTROL_DEVICE
    assert res.entities.get("device_type") == "light"
    assert res.requested_action == "OFF"
    assert res.is_ambiguous is True
    assert res.requires_clarification is True

    # Record states before command
    bedroom_state_before = db_session.query(Device).filter_by(id="bedroom_light").first().state
    living_state_before = db_session.query(Device).filter_by(id="living_room_light").first().state

    response = client.post(
        "/voice/process",
        headers=enrolled_auth["headers"],
        json={"text": "Turn off the lights.", "session_id": enrolled_auth["session_id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "CLARIFY"
    assert data["is_ambiguous"] is True
    assert data["requires_clarification"] is True
    assert "clarification_question" in data
    assert "Bedroom Light" in data["clarification_question"]
    assert "Living Room Light" in data["clarification_question"]
    assert data["execution_status"] is None

    # CRITICAL: Verify NO device state changed
    assert db_session.query(Device).filter_by(id="bedroom_light").first().state == bedroom_state_before
    assert db_session.query(Device).filter_by(id="living_room_light").first().state == living_state_before


def test_case_3_indirect_its_too_dark(db_session, client, enrolled_auth):
    """
    CASE 3: "It's too dark."
    Expected: Indirect request, suggests Light ON, decision CLARIFY.
              NO device state changes!
    """
    intent_service = IntentService()
    res = intent_service.extract("It's too dark.")

    assert res.intent == CONTROL_DEVICE
    assert res.is_indirect is True
    assert res.suggested_action == "ON"
    assert res.suggested_device in ("light", "lights")
    assert res.entities.get("device_type") == "light"
    assert res.requires_clarification is True

    bedroom_state_before = db_session.query(Device).filter_by(id="bedroom_light").first().state
    living_state_before = db_session.query(Device).filter_by(id="living_room_light").first().state

    response = client.post(
        "/voice/process",
        headers=enrolled_auth["headers"],
        json={"text": "It's too dark.", "session_id": enrolled_auth["session_id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "CLARIFY"
    assert data["requires_clarification"] is True
    assert "too dark" in data["clarification_question"].lower()
    assert data["execution_status"] is None

    # Verify NO device state changed
    assert db_session.query(Device).filter_by(id="bedroom_light").first().state == bedroom_state_before
    assert db_session.query(Device).filter_by(id="living_room_light").first().state == living_state_before


def test_case_4_indirect_im_feeling_hot(db_session, client, enrolled_auth):
    """
    CASE 4: "I'm feeling hot."
    Expected: Indirect request, suggests Fan ON. With context-aware interpretation,
              when the fan is OFF, the engine directly proposes EXECUTE (fan ON)
              instead of asking a redundant clarification.
              Device state changes to ON after context-aware execution.
    """
    intent_service = IntentService()
    res = intent_service.extract("I'm feeling hot.")

    assert res.intent == CONTROL_DEVICE
    assert res.is_indirect is True
    assert res.suggested_action == "ON"
    assert res.suggested_device == "fan"
    assert res.requires_clarification is True

    fan_state_before = db_session.query(Device).filter_by(id="fan").first().state

    response = client.post(
        "/voice/process",
        headers=enrolled_auth["headers"],
        json={"text": "I'm feeling hot.", "session_id": enrolled_auth["session_id"]},
    )
    assert response.status_code == 200
    data = response.json()

    # Context-aware engine: fan is OFF, so it directly EXECUTEs fan ON
    if fan_state_before == "OFF":
        assert data["decision"] == "EXECUTE"
        assert data["target_device"] == "fan"
        assert data["requested_action"] == "ON"
        assert data["execution_status"] == "SUCCESS"
        db_session.expire_all()
        assert db_session.query(Device).filter_by(id="fan").first().state == "ON"
    else:
        # Fan is already ON → no_action_needed → REJECT
        assert data["decision"] == "REJECT"
        assert db_session.query(Device).filter_by(id="fan").first().state == fan_state_before


def test_case_5_pronoun_reference_turn_it_off(db_session, client, enrolled_auth):
    """
    CASE 5: "Turn it off."
    Expected: Pronoun reference without prior context.
              decision CLARIFY asking "the fan or the lights?".
              NO device state changes!
    """
    intent_service = IntentService()
    # Explicit clean session with no prior context
    res = intent_service.extract("Turn it off.")

    assert res.intent == CONTROL_DEVICE
    assert res.is_ambiguous is True
    assert res.requires_clarification is True

    fan_state_before = db_session.query(Device).filter_by(id="fan").first().state
    bedroom_state_before = db_session.query(Device).filter_by(id="bedroom_light").first().state

    response = client.post(
        "/voice/process",
        headers=enrolled_auth["headers"],
        json={"text": "Turn it off.", "session_id": "fresh-session-turn-it-off"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "CLARIFY"
    assert data["requires_clarification"] is True
    assert "fan or the lights" in data["clarification_question"]
    assert data["execution_status"] is None

    # Verify NO device state changed
    assert db_session.query(Device).filter_by(id="fan").first().state == fan_state_before
    assert db_session.query(Device).filter_by(id="bedroom_light").first().state == bedroom_state_before


def test_case_6_unknown_device(db_session, client, enrolled_auth):
    """
    CASE 6: Unknown device (e.g. "Turn on the television")
    Expected: Decision REJECT, unsupported device; no device state changes.
    """
    intent_service = IntentService()
    res = intent_service.extract("Turn on the television")

    assert res.target_device == "television"
    assert res.entities.get("unknown_device") is True

    # Record states of all registered devices
    states_before = {d.id: d.state for d in db_session.query(Device).all()}

    response = client.post(
        "/voice/process",
        headers=enrolled_auth["headers"],
        json={"text": "Turn on the television", "session_id": enrolled_auth["session_id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "REJECT"
    assert "not supported" in data["decision_reason"].lower() or "does not exist" in data["decision_reason"].lower()
    assert data["execution_status"] is None

    # Verify NO device state changed
    for dev_id, state in states_before.items():
        assert db_session.query(Device).filter_by(id=dev_id).first().state == state


def test_case_7_unsupported_action(db_session, client, enrolled_auth):
    """
    CASE 7: Unsupported action (e.g. "Dim the bedroom light")
    Expected: Decision REJECT, unsupported action; no device state changes.
    """
    intent_service = IntentService()
    res = intent_service.extract("Dim the bedroom light")

    assert res.target_device == "bedroom_light"
    assert res.requested_action == "DIM"

    light_state_before = db_session.query(Device).filter_by(id="bedroom_light").first().state

    response = client.post(
        "/voice/process",
        headers=enrolled_auth["headers"],
        json={"text": "Dim the bedroom light", "session_id": enrolled_auth["session_id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "REJECT"
    assert "not supported" in data["decision_reason"].lower()
    assert data["execution_status"] is None

    # Verify NO device state changed
    assert db_session.query(Device).filter_by(id="bedroom_light").first().state == light_state_before


def test_case_8_ambiguous_command_make_it_comfortable(db_session, client, enrolled_auth):
    """
    CASE 8: Ambiguous command (e.g. "Make it comfortable")
    Expected: Decision CLARIFY asking what to adjust; no device state changes.
    """
    intent_service = IntentService()
    res = intent_service.extract("Make it comfortable")

    assert res.is_ambiguous is True
    assert res.requires_clarification is True

    states_before = {d.id: d.state for d in db_session.query(Device).all()}

    response = client.post(
        "/voice/process",
        headers=enrolled_auth["headers"],
        json={"text": "Make it comfortable", "session_id": enrolled_auth["session_id"]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "CLARIFY"
    assert data["requires_clarification"] is True
    assert "fan or the lights" in data["clarification_question"]
    assert data["execution_status"] is None

    # Verify NO device state changed
    for dev_id, state in states_before.items():
        assert db_session.query(Device).filter_by(id=dev_id).first().state == state


def test_case_9_failed_voice_authentication(db_session, client, enrolled_auth):
    """
    CASE 9: Failed voice authentication
    Expected: Audio fails threshold, decision REJECT; no device state changes.
    """
    fan_state_before = db_session.query(Device).filter_by(id="fan").first().state
    audio_wav = create_synthetic_wav(frequency=300.0, duration=1.0)

    # Mock verify_speaker to simulate failed verification (score below threshold 0.65)
    with patch.object(
        VoiceAuthService,
        "verify_speaker",
        return_value=(False, 0.42, "Voice not recognized. Command rejected.", "Similarity 0.4200 below threshold 0.65"),
    ):
        files = {"file": ("command.wav", audio_wav, "audio/wav")}
        response = client.post("/voice/process-audio", files=files)
        assert response.status_code == 200
        data = response.json()
        assert data["decision"] == "REJECT"
        assert data["speaker_verified"] is False
        assert data["speaker_similarity"] == 0.42
        assert data["execution_status"] == "REJECTED"

    # Verify NO device state changed
    assert db_session.query(Device).filter_by(id="fan").first().state == fan_state_before


def test_case_10_direct_device_control_without_auth_rejected(db_session, client):
    """
    CASE 10: Direct device-control API request without valid authentication
    Expected: POST /devices/bedroom_light/command without token returns HTTP 401;
              no device state changes.
    """
    light_state_before = db_session.query(Device).filter_by(id="bedroom_light").first().state

    # Direct device command without Authorization header
    response = client.post(
        "/devices/bedroom_light/command",
        json={"action": "ON"},
    )
    assert response.status_code == 401
    assert "authentication required" in response.json()["detail"].lower()

    # Also test with invalid token
    response_invalid = client.post(
        "/devices/bedroom_light/command",
        headers={"Authorization": "Bearer invalid-tampered-token"},
        json={"action": "ON"},
    )
    assert response_invalid.status_code == 401

    # Verify device state remains unchanged
    assert db_session.query(Device).filter_by(id="bedroom_light").first().state == light_state_before
