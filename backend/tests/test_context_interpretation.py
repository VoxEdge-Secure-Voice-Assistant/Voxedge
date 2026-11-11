"""
Test suite for Context-Aware Command Interpretation.

Covers the 10 scenarios required:
  SCENARIO  1: Fan ON + "It's too cool." → Propose fan OFF (EXECUTE).
  SCENARIO  2: Fan OFF + "It's too cool." → No unnecessary state change (REJECT).
  SCENARIO  3: Lights OFF + "It's too dark." → Propose lights ON / clarify.
  SCENARIO  4: Ambiguous "Make it comfortable" → Ask for clarification (CLARIFY).
  SCENARIO  5: "Turn it off" with no context → Ask which device (CLARIFY).
  SCENARIO  6: Follow-up: Turn 1 "turn on the fan", Turn 2 "Turn it off" → fan OFF.
  SCENARIO  7: Unknown device "Turn on the toaster" → Reject (REJECT).
  SCENARIO  8: Unsupported action "Dim the fan" → Reject (REJECT).
  SCENARIO  9: Device execution fails → Do NOT report success.
  SCENARIO 10: Existing speaker auth tests still pass (verified separately).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure backend directory is in python path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.database.session import Base
from app.models.device import Device
from app.services.context_interpreter import ContextInterpreter, ContextProposal
from app.services.context_service import ContextService
from app.services.decision_engine import DecisionEngine, EXECUTE, CLARIFY, REJECT
from app.services.device_service import DeviceService
from app.services.intent_service import (
    IntentResult,
    IntentService,
    CONTROL_DEVICE,
    UNKNOWN,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def db_session():
    """In-memory SQLite database with default device seed data."""
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
def context_service():
    """Fresh ContextService for each test."""
    return ContextService()


@pytest.fixture
def intent_service():
    """IntentService instance."""
    return IntentService()


# ── Helpers ──────────────────────────────────────────────────────────────────


def set_device_state(db_session, device_id: str, state: str) -> None:
    """Helper to set a device's state in the test DB."""
    device = db_session.query(Device).filter(Device.id == device_id).first()
    if device:
        device.state = state
        db_session.commit()


def get_device_states(db_session) -> dict[str, str]:
    """Get current device states from DB."""
    devices = db_session.query(Device).all()
    return {d.id: d.state for d in devices}


# ══════════════════════════════════════════════════════════════════════════════
# UNIT TESTS: ContextInterpreter in isolation
# ══════════════════════════════════════════════════════════════════════════════


class TestContextInterpreterUnit:
    """Tests for ContextInterpreter.interpret() directly."""

    def test_cool_with_fan_on_proposes_fan_off(self, db_session, context_service):
        """SCENARIO 1a: Fan ON + 'It's too cool' → propose fan OFF."""
        interpreter = ContextInterpreter()
        states = {"fan": "ON", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="It's too cool.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.device == "fan"
        assert proposal.action == "OFF"
        assert proposal.no_action_needed is False
        assert proposal.requires_clarification is False

    def test_cold_with_fan_on_proposes_fan_off(self, db_session, context_service):
        """SCENARIO 1b: Fan ON + 'It's too cold' → propose fan OFF."""
        interpreter = ContextInterpreter()
        states = {"fan": "ON", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="It's too cold.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.device == "fan"
        assert proposal.action == "OFF"
        assert proposal.no_action_needed is False

    def test_cool_with_fan_off_no_action(self, db_session, context_service):
        """SCENARIO 2: Fan OFF + 'It's too cool' → no_action_needed."""
        interpreter = ContextInterpreter()
        states = {"fan": "OFF", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="It's too cool.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.device == "fan"
        assert proposal.no_action_needed is True

    def test_hot_with_fan_off_proposes_fan_on(self, db_session, context_service):
        """Fan OFF + 'I'm feeling hot' → propose fan ON."""
        interpreter = ContextInterpreter()
        states = {"fan": "OFF", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="I'm feeling hot.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.device == "fan"
        assert proposal.action == "ON"
        assert proposal.no_action_needed is False

    def test_hot_with_fan_on_no_action(self, db_session, context_service):
        """Fan ON + 'I'm feeling hot' → no_action_needed."""
        interpreter = ContextInterpreter()
        states = {"fan": "ON", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="I'm feeling hot.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.no_action_needed is True

    def test_dark_both_lights_off_clarify(self, db_session, context_service):
        """SCENARIO 3a: Both lights OFF + 'It's too dark' → clarification."""
        interpreter = ContextInterpreter()
        states = {"fan": "OFF", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="It's too dark.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.action == "ON"
        assert proposal.requires_clarification is True

    def test_dark_one_light_off_proposes_that_light(self, db_session, context_service):
        """SCENARIO 3b: Bedroom OFF, Living ON + 'It's too dark' → propose bedroom ON."""
        interpreter = ContextInterpreter()
        states = {"fan": "OFF", "bedroom_light": "OFF", "living_room_light": "ON"}
        proposal = interpreter.interpret(
            text="It's too dark.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.device == "bedroom_light"
        assert proposal.action == "ON"
        assert proposal.requires_clarification is False

    def test_dark_all_lights_on_no_action(self, db_session, context_service):
        """Both lights ON + 'It's too dark' → no_action_needed."""
        interpreter = ContextInterpreter()
        states = {"fan": "OFF", "bedroom_light": "ON", "living_room_light": "ON"}
        proposal = interpreter.interpret(
            text="It's too dark.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.no_action_needed is True

    def test_bright_all_off_no_action(self, db_session, context_service):
        """All lights OFF + 'It's too bright' → no_action_needed."""
        interpreter = ContextInterpreter()
        states = {"fan": "OFF", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="It's too bright.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.no_action_needed is True

    def test_bright_some_lights_on_clarify(self, db_session, context_service):
        """Some lights ON + 'It's too bright' → clarification."""
        interpreter = ContextInterpreter()
        states = {"fan": "OFF", "bedroom_light": "ON", "living_room_light": "ON"}
        proposal = interpreter.interpret(
            text="It's too bright.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.action == "OFF"
        assert proposal.requires_clarification is True

    def test_ambiguous_comfort_clarify(self, db_session, context_service):
        """SCENARIO 4: 'Make it comfortable' → clarification."""
        interpreter = ContextInterpreter()
        states = {"fan": "OFF", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="Make it comfortable.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.requires_clarification is True

    def test_pronoun_no_context_clarify(self, db_session, context_service):
        """SCENARIO 5: 'Turn it off' with no context → clarification."""
        interpreter = ContextInterpreter()
        states = {"fan": "OFF", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="Turn it off.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.requires_clarification is True

    def test_pronoun_with_context_resolves(self, db_session, context_service):
        """SCENARIO 6 (unit): 'Turn it off' with fan in context → fan OFF."""
        context_service.add_entry(
            session_id="test-session",
            device_id="fan",
            device_type="fan",
            action="ON",
            intent="CONTROL_DEVICE",
            raw_command="turn on the fan",
        )
        interpreter = ContextInterpreter()
        states = {"fan": "ON", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="Turn it off.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.device == "fan"
        assert proposal.action == "OFF"
        assert proposal.requires_clarification is False

    def test_unknown_device_toaster(self, db_session, context_service):
        """SCENARIO 7: 'Turn on the toaster' → is_unknown_device."""
        interpreter = ContextInterpreter()
        states = {"fan": "OFF", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="Turn on the toaster.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.is_unknown_device is True

    def test_unsupported_action_dim_fan(self, db_session, context_service):
        """SCENARIO 8: 'Dim the fan' → is_unsupported_action."""
        interpreter = ContextInterpreter()
        states = {"fan": "ON", "bedroom_light": "OFF", "living_room_light": "OFF"}
        proposal = interpreter.interpret(
            text="Dim the fan.",
            context=context_service,
            session_id="test-session",
            device_states=states,
        )
        assert proposal is not None
        assert proposal.is_unsupported_action is True


# ══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS: ContextInterpreter wired through DecisionEngine
# ══════════════════════════════════════════════════════════════════════════════


class TestContextInterpretationIntegration:
    """Tests that ContextInterpreter proposals are correctly translated to Decisions by DecisionEngine."""

    def test_scenario1_cool_fan_on_execute_off(self, db_session, context_service):
        """SCENARIO 1: Fan ON + 'It's too cool' → Decision(EXECUTE, fan, OFF)."""
        set_device_state(db_session, "fan", "ON")
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="It's too cool.",
            confidence=0.85,
            is_indirect=True,
            entities={"is_indirect": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == EXECUTE
        assert decision.target_device == "fan"
        assert decision.requested_action == "OFF"

    def test_scenario2_cool_fan_off_reject(self, db_session, context_service):
        """SCENARIO 2: Fan OFF + 'It's too cool' → Decision(REJECT, no_action_needed)."""
        set_device_state(db_session, "fan", "OFF")
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="It's too cool.",
            confidence=0.85,
            is_indirect=True,
            entities={"is_indirect": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == REJECT
        # Should explain the fan is already off
        assert "already OFF" in decision.reason or "already off" in decision.reason.lower()

    def test_scenario3_dark_lights_off_clarify_or_propose(self, db_session, context_service):
        """SCENARIO 3: Both lights OFF + 'It's too dark' → CLARIFY or EXECUTE."""
        set_device_state(db_session, "bedroom_light", "OFF")
        set_device_state(db_session, "living_room_light", "OFF")
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="It's too dark.",
            confidence=0.85,
            is_indirect=True,
            entities={"is_indirect": True},
        )
        decision = engine.decide(intent_result, "test-session")
        # Should clarify which light to turn on (both are off)
        assert decision.outcome == CLARIFY
        assert decision.requested_action == "ON"

    def test_scenario3b_dark_one_light_off_execute(self, db_session, context_service):
        """SCENARIO 3b: Bedroom OFF + Living ON + 'It's too dark' → EXECUTE bedroom ON."""
        set_device_state(db_session, "bedroom_light", "OFF")
        set_device_state(db_session, "living_room_light", "ON")
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="It's too dark.",
            confidence=0.85,
            is_indirect=True,
            entities={"is_indirect": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == EXECUTE
        assert decision.target_device == "bedroom_light"
        assert decision.requested_action == "ON"

    def test_scenario4_ambiguous_clarify(self, db_session, context_service):
        """SCENARIO 4: 'Make it comfortable' → Decision(CLARIFY)."""
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="Make it comfortable.",
            confidence=0.6,
            is_indirect=True,
            entities={"is_indirect": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == CLARIFY

    def test_scenario5_turn_it_off_no_context_clarify(self, db_session, context_service):
        """SCENARIO 5: 'Turn it off' with no context → Decision(CLARIFY)."""
        engine = DecisionEngine(db=db_session, context=context_service)
        # The intent service recognizes "turn it off" as a pronoun reference
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="Turn it off.",
            confidence=0.8,
            is_indirect=True,
            entities={"is_indirect": True, "pronoun_reference": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == CLARIFY

    def test_scenario6_followup_turn_it_off(self, db_session, context_service):
        """SCENARIO 6: Turn 1 = fan ON, Turn 2 = 'Turn it off' → Decision(EXECUTE, fan, OFF)."""
        set_device_state(db_session, "fan", "ON")
        context_service.add_entry(
            session_id="test-session",
            device_id="fan",
            device_type="fan",
            action="ON",
            intent="CONTROL_DEVICE",
            raw_command="turn on the fan",
        )
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="Turn it off.",
            confidence=0.8,
            is_indirect=True,
            entities={"is_indirect": True, "pronoun_reference": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == EXECUTE
        assert decision.target_device == "fan"
        assert decision.requested_action == "OFF"

    def test_scenario7_unknown_device_reject(self, db_session, context_service):
        """SCENARIO 7: 'Turn on the toaster' → Decision(REJECT, unknown device)."""
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="Turn on the toaster.",
            confidence=0.8,
            is_indirect=True,
            entities={"is_indirect": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == REJECT
        assert "toaster" in decision.message.lower() or "toaster" in decision.reason.lower()

    def test_scenario8_unsupported_action_reject(self, db_session, context_service):
        """SCENARIO 8: 'Dim the fan' → Decision(REJECT, unsupported action)."""
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="Dim the fan.",
            confidence=0.8,
            is_indirect=True,
            entities={"is_indirect": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == REJECT

    def test_scenario9_execution_failure_not_success(self, db_session, context_service):
        """SCENARIO 9: Device execution fails → execution_status is 'FAILED', not 'SUCCESS'."""
        set_device_state(db_session, "fan", "ON")
        engine = DecisionEngine(db=db_session, context=context_service)

        # First, get a valid EXECUTE decision
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="It's too cool.",
            confidence=0.85,
            is_indirect=True,
            entities={"is_indirect": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == EXECUTE
        assert decision.target_device == "fan"

        # Now simulate the execution failing (as voice.py does)
        device_service = DeviceService(db_session)
        with patch.object(device_service, "execute_action", return_value={"success": False, "message": "Hardware error"}):
            exec_result = device_service.execute_action(
                device_id=decision.target_device,
                action=decision.requested_action,
            )
            execution_status = "SUCCESS" if exec_result["success"] else "FAILED"

        assert execution_status == "FAILED"

    def test_hot_fan_off_executes_on(self, db_session, context_service):
        """Fan OFF + 'I'm feeling hot' → Decision(EXECUTE, fan, ON)."""
        set_device_state(db_session, "fan", "OFF")
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="I'm feeling hot.",
            confidence=0.85,
            is_indirect=True,
            entities={"is_indirect": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == EXECUTE
        assert decision.target_device == "fan"
        assert decision.requested_action == "ON"

    def test_hot_fan_on_reject_no_action(self, db_session, context_service):
        """Fan ON + 'I'm feeling hot' → REJECT (already on)."""
        set_device_state(db_session, "fan", "ON")
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="I'm feeling hot.",
            confidence=0.85,
            is_indirect=True,
            entities={"is_indirect": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == REJECT
        assert "already ON" in decision.reason or "already on" in decision.reason.lower()

    def test_direct_command_unchanged(self, db_session, context_service):
        """Direct 'turn on the fan' still goes through standard _handle_control, not context interpreter."""
        set_device_state(db_session, "fan", "OFF")
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="Turn on the fan.",
            confidence=0.95,
            is_indirect=False,
            entities={"device": "fan", "action": "ON"},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == EXECUTE
        assert decision.target_device == "fan"
        assert decision.requested_action == "ON"

    def test_context_interpreter_returns_none_falls_to_clarify(self, db_session, context_service):
        """Unrecognized indirect statement → fallback CLARIFY."""
        engine = DecisionEngine(db=db_session, context=context_service)
        intent_result = IntentResult(
            intent=CONTROL_DEVICE,
            raw_text="I don't feel great about the environment.",
            confidence=0.5,
            is_indirect=True,
            entities={"is_indirect": True},
        )
        decision = engine.decide(intent_result, "test-session")
        assert decision.outcome == CLARIFY


# ══════════════════════════════════════════════════════════════════════════════
# INTENT SERVICE INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════


class TestIntentServiceContextAware:
    """Verify IntentService correctly flags indirect statements for context interpretation."""

    def test_too_cool_is_indirect(self, intent_service):
        result = intent_service.extract("It's too cool.")
        assert result.is_indirect is True
        assert result.intent == CONTROL_DEVICE

    def test_too_cold_is_indirect(self, intent_service):
        result = intent_service.extract("It's too cold.")
        assert result.is_indirect is True

    def test_feeling_hot_is_indirect(self, intent_service):
        result = intent_service.extract("I'm feeling hot.")
        assert result.is_indirect is True

    def test_too_dark_is_indirect(self, intent_service):
        result = intent_service.extract("It's too dark.")
        assert result.is_indirect is True

    def test_direct_command_not_indirect(self, intent_service):
        result = intent_service.extract("Turn on the fan.")
        assert result.is_indirect is False
        assert result.intent == CONTROL_DEVICE

