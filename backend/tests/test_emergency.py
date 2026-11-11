"""
Test suite for Dedicated Emergency Detection and Response Module.

Covers all 12 required test cases:
  1. "Help me." -> Emergency detected, classified, escalated.
  2. "I've fallen and can't get up." -> Emergency detected (FALL category), escalated.
  3. "I can't breathe." -> Emergency detected (BREATHING category, CRITICAL severity).
  4. Hypothetical question about falling ("What happens if I fall?") -> Filtered, not an emergency.
  5. Negated statement ("I haven't fallen.") -> Filtered, not an emergency.
  6. Ordinary device command ("Turn on the fan.") -> Not an emergency, routes to device control.
  7. Empty or unintelligible transcript -> Handled safely, not an emergency.
  8. Repeated emergency input and duplicate prevention -> Returns existing active event, no duplicate records.
  9. Alert cancellation -> Active emergency event transitioned to CANCELLED.
  10. Storage or response failures -> Handled without falsely reporting success.
  11. Emergency detection when speaker verification fails -> Detected and escalated without modifying authentication.
  12. Regression tests -> Normal authenticated device commands still execute properly.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from app.database.session import Base, get_db
from app.main import app
from app.models.device import Device
from app.models.emergency import EmergencyEvent
from app.services.decision_engine import DecisionEngine, ESCALATE, EXECUTE, REJECT
from app.services.emergency_detector import (
    EmergencyCategory,
    EmergencyDetectionResult,
    EmergencyDetector,
)
from app.services.emergency_service import EmergencyService
from app.services.intent_service import EMERGENCY, CONTROL_DEVICE, IntentService
from app.services.voice_auth_service import VoiceAuthService


# ── Helpers ───────────────────────────────────────────────────────────────────

def create_synthetic_wav(frequency: float = 440.0, duration: float = 1.0, sample_rate: int = 16000) -> bytes:
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    waveform = (0.5 * np.sin(2 * np.pi * frequency * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, waveform, sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_voice_profile(tmp_path):
    profile_path = tmp_path / "test_enrolled_voice.npy"
    original_path = settings.enrolled_voice_path
    settings.enrolled_voice_path = str(profile_path)
    yield profile_path
    settings.enrolled_voice_path = original_path
    if profile_path.exists():
        profile_path.unlink()


@pytest.fixture
def db_session():
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
    voice_auth = VoiceAuthService()
    dummy_embedding = np.ones(256, dtype=np.float32)
    dummy_embedding = dummy_embedding / np.linalg.norm(dummy_embedding)
    voice_auth.save_enrolled_embedding(dummy_embedding)

    token = voice_auth.create_session_token("test-session-emergency", 0.95)
    return {
        "voice_auth": voice_auth,
        "token": token,
        "session_id": "test-session-emergency",
        "headers": {"Authorization": f"Bearer {token}"},
    }


# ── TEST CASES ───────────────────────────────────────────────────────────────

def test_1_help_me_detection():
    """1. 'Help me.' -> Emergency detected, classified, and escalated."""
    detector = EmergencyDetector()
    result = detector.detect("Help me.")

    assert result.is_emergency is True
    assert result.category == EmergencyCategory.GENERAL_DISTRESS.value
    assert result.severity in ("MEDIUM", "HIGH")
    assert "Help requested" in result.detection_reason or "help me" in result.matched_pattern.lower()
    assert result.recommended_response != ""


def test_2_fallen_and_cant_get_up():
    """2. 'I've fallen and can't get up.' -> Emergency detected, FALL category."""
    detector = EmergencyDetector()
    result = detector.detect("I've fallen and can't get up.")

    assert result.is_emergency is True
    assert result.category == EmergencyCategory.FALL.value
    assert result.severity == "HIGH"
    assert result.is_negated is False
    assert result.is_hypothetical is False


def test_3_cant_breathe():
    """3. 'I can't breathe.' -> Emergency detected, BREATHING category, CRITICAL severity."""
    detector = EmergencyDetector()
    result = detector.detect("I can't breathe.")

    assert result.is_emergency is True
    assert result.category == EmergencyCategory.BREATHING.value
    assert result.severity == "CRITICAL"
    assert "breathing" in result.recommended_response.lower()


def test_4_hypothetical_question_about_falling():
    """4. A hypothetical question about falling -> Filtered, not an emergency."""
    detector = EmergencyDetector()

    # Test several hypothetical variants
    variants = [
        "What happens if I fall?",
        "What if I fell down?",
        "How do you handle if someone falls?",
        "Can you detect if I fall down?",
        "Suppose I fall down on the floor?",
    ]
    for text in variants:
        result = detector.detect(text)
        assert result.is_emergency is False, f"Failed for hypothetical: '{text}'"
        assert result.is_hypothetical is True


def test_5_negated_statement_not_fallen():
    """5. A negated statement such as 'I haven't fallen.' -> Filtered, not an emergency."""
    detector = EmergencyDetector()

    negated_statements = [
        "I haven't fallen.",
        "I have not fallen down.",
        "I didn't fall.",
        "I am not hurt.",
        "I don't need help.",
        "No emergency here.",
        "False alarm, I'm fine.",
    ]
    for text in negated_statements:
        result = detector.detect(text)
        assert result.is_emergency is False, f"Failed for negated: '{text}'"
        assert result.is_negated is True


def test_6_ordinary_device_command():
    """6. An ordinary device command -> Not an emergency."""
    detector = EmergencyDetector()
    result = detector.detect("Turn on the fan.")

    assert result.is_emergency is False
    assert result.is_negated is False
    assert result.is_hypothetical is False


def test_7_empty_or_unintelligible_transcript():
    """7. An empty or unintelligible transcript -> Handled safely."""
    detector = EmergencyDetector()

    for empty_val in ["", "   ", "...", "hmm"]:
        result = detector.detect(empty_val)
        assert result.is_emergency is False


def test_8_duplicate_prevention(db_session):
    """8. Repeated emergency input -> Returns existing active event, prevents duplicate records."""
    emergency_service = EmergencyService(db_session)

    # First trigger creates an active event
    event1 = emergency_service.trigger(
        trigger_text="Help me, I fell down.",
        severity="HIGH",
        category="FALL",
    )
    assert event1 is not None
    assert event1.status == "ACTIVE"

    # Second trigger with active event present should return the same event
    event2 = emergency_service.trigger(
        trigger_text="Help me, I fell down.",
        severity="HIGH",
        category="FALL",
    )
    assert event2.id == event1.id

    # Count total records in DB - should be exactly 1
    total_events = db_session.query(EmergencyEvent).count()
    assert total_events == 1


def test_9_alert_cancellation(db_session, client, enrolled_auth):
    """9. Alert cancellation -> Active emergency event transitioned to CANCELLED."""
    emergency_service = EmergencyService(db_session)

    # Create active emergency
    event = emergency_service.trigger(
        trigger_text="Please call for help.",
        severity="HIGH",
        category="CALL_FOR_HELP",
    )
    assert event.status == "ACTIVE"

    # Cancel via EmergencyService
    updated = emergency_service.update_status(event.id, "CANCELLED", notes="User cancelled")
    assert updated is not None
    assert updated.status == "CANCELLED"
    assert updated.resolved_at is not None

    # Cancel via voice command 'cancel'
    # Trigger another event
    event2 = emergency_service.trigger(
        trigger_text="Help me.",
        severity="HIGH",
        category="GENERAL_DISTRESS",
    )
    assert event2.status == "ACTIVE"

    resp = client.post(
        "/voice/process",
        headers=enrolled_auth["headers"],
        json={"text": "Cancel.", "session_id": enrolled_auth["session_id"]},
    )
    assert resp.status_code == 200
    db_session.expire_all()
    reloaded = db_session.query(EmergencyEvent).filter_by(id=event2.id).first()
    assert reloaded.status == "CANCELLED"


def test_10_storage_or_response_failures(db_session):
    """10. Storage or response failures -> Handled without falsely reporting success."""
    emergency_service = EmergencyService(db_session)

    # Simulate DB commit failure
    with patch.object(db_session, "commit", side_effect=Exception("Database connection lost")):
        with pytest.raises(RuntimeError, match="Storage failure"):
            emergency_service.trigger(
                trigger_text="Help me.",
                severity="HIGH",
            )


def test_11_emergency_detection_when_speaker_verification_fails(client, temp_voice_profile):
    """
    11. Emergency detection when speaker verification fails.
    A failed speaker verification must NOT suppress detection of emergency speech.
    Device control must remain protected.
    """
    voice_auth = VoiceAuthService()
    # Enroll a dummy profile
    dummy_embedding = np.ones(256, dtype=np.float32)
    dummy_embedding = dummy_embedding / np.linalg.norm(dummy_embedding)
    voice_auth.save_enrolled_embedding(dummy_embedding)

    # Mock verify_speaker to FAIL (different speaker or failed similarity)
    # Mock transcribe_audio to return emergency speech
    with patch.object(VoiceAuthService, "verify_speaker", return_value=(False, 0.20, "Voice authentication failed.", "Score 0.20 < threshold 0.75")):
        with patch.object(VoiceAuthService, "transcribe_audio", return_value="Help me, I've fallen and can't get up."):
            wav_bytes = create_synthetic_wav(frequency=300.0, duration=1.0)
            response = client.post(
                "/voice/process-audio",
                files={"file": ("command.wav", wav_bytes, "audio/wav")},
            )

            assert response.status_code == 200
            data = response.json()

            # Emergency MUST be detected and escalated
            assert data["decision"] == "ESCALATE"
            assert data["intent"] == "EMERGENCY"
            # Speaker verification remains marked as failed (truthful security reporting)
            assert data["speaker_verified"] is False
            assert "emergency" in data["message"].lower() or "fall" in data["message"].lower()

            # Check structured emergency detection
            assert data["emergency_detection"] is not None
            assert data["emergency_detection"]["is_emergency"] is True
            assert data["emergency_detection"]["category"] == "FALL"


def test_11b_unauthenticated_device_command_still_rejected(client, temp_voice_profile, db_session):
    """
    Complementary to test 11:
    Non-emergency commands spoken by an unverified speaker are STILL rejected.
    """
    voice_auth = VoiceAuthService()
    dummy_embedding = np.ones(256, dtype=np.float32)
    dummy_embedding = dummy_embedding / np.linalg.norm(dummy_embedding)
    voice_auth.save_enrolled_embedding(dummy_embedding)

    fan_before = db_session.query(Device).filter_by(id="fan").first().state

    with patch.object(VoiceAuthService, "verify_speaker", return_value=(False, 0.20, "Voice authentication failed.", "Score 0.20 < threshold 0.75")):
        with patch.object(VoiceAuthService, "transcribe_audio", return_value="Turn on the fan."):
            wav_bytes = create_synthetic_wav(frequency=300.0, duration=1.0)
            response = client.post(
                "/voice/process-audio",
                files={"file": ("command.wav", wav_bytes, "audio/wav")},
            )

            assert response.status_code == 200
            data = response.json()

            # Must be REJECTED
            assert data["decision"] == "REJECT"
            assert data["speaker_verified"] is False

            # Fan state MUST NOT change
            db_session.expire_all()
            assert db_session.query(Device).filter_by(id="fan").first().state == fan_before


def test_12_regression_authenticated_commands_still_work(client, enrolled_auth, db_session):
    """12. Regression test: Normal authenticated device commands still work properly."""
    fan_before = db_session.query(Device).filter_by(id="fan").first().state
    assert fan_before == "OFF"

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

    db_session.expire_all()
    fan_after = db_session.query(Device).filter_by(id="fan").first().state
    assert fan_after == "ON"

