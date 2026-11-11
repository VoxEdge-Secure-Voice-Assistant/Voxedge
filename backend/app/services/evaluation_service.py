"""
VoxEdge Evaluation Service — Baseline vs Enhanced comparison engine.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from app.services.context_service import ContextService
from app.services.decision_engine import DecisionEngine
from app.services.intent_service import IntentService


@dataclass
class EvalCase:
    id: str
    text: str
    expected_intent: str
    expected_device: str | None
    expected_action: str | None
    expected_decision: str  # EXECUTE, CLARIFY, REJECT, ESCALATE
    category: str  # "correctness", "safety", "usability", "context"
    description: str
    session_setup: list[dict] = field(default_factory=list)


EVALUATION_BENCHMARK: list[EvalCase] = [
    EvalCase(
        id="C1", text="turn on the fan",
        expected_intent="CONTROL_DEVICE", expected_device="fan",
        expected_action="ON", expected_decision="EXECUTE",
        category="correctness", description="Simple fan on command",
    ),
    EvalCase(
        id="C2", text="turn off the fan",
        expected_intent="CONTROL_DEVICE", expected_device="fan",
        expected_action="OFF", expected_decision="EXECUTE",
        category="correctness", description="Simple fan off command",
    ),
    EvalCase(
        id="C3", text="turn on the bedroom light",
        expected_intent="CONTROL_DEVICE", expected_device="bedroom_light",
        expected_action="ON", expected_decision="EXECUTE",
        category="correctness", description="Multi-device support: bedroom light",
    ),
    EvalCase(
        id="C4", text="switch off the living room light",
        expected_intent="CONTROL_DEVICE", expected_device="living_room_light",
        expected_action="OFF", expected_decision="EXECUTE",
        category="correctness", description="Multi-device support: living room light",
    ),
    EvalCase(
        id="C5", text="fan off",
        expected_intent="CONTROL_DEVICE", expected_device="fan",
        expected_action="OFF", expected_decision="EXECUTE",
        category="correctness", description="Short command syntax",
    ),
    EvalCase(
        id="C6", text="is the fan on",
        expected_intent="STATUS_CHECK", expected_device="fan",
        expected_action=None, expected_decision="EXECUTE",
        category="correctness",
        description="Status query without state change",
    ),
    EvalCase(
        id="C7", text="turn on the kitchen light",
        expected_intent="CONTROL_DEVICE", expected_device=None,
        expected_action=None, expected_decision="REJECT",
        category="correctness",
        description="Unregistered room device (kitchen light does not exist)",
    ),
    EvalCase(
        id="C8", text="turn off everything",
        expected_intent="CONTROL_DEVICE", expected_device=None,
        expected_action="OFF", expected_decision="EXECUTE",
        category="correctness",
        description="Bulk multi-device command (unsupported in single-slot pipeline)",
    ),
    EvalCase(
        id="U1", text="turn off the light",
        expected_intent="CONTROL_DEVICE", expected_device=None,
        expected_action="OFF", expected_decision="CLARIFY",
        category="usability",
        description="Ambiguous device — clarifies which light",
    ),
    EvalCase(
        id="U2", text="what can you do",
        expected_intent="HELP", expected_device=None,
        expected_action=None, expected_decision="REJECT",
        category="usability",
        description="Out-of-domain help request handled gracefully",
    ),
    EvalCase(
        id="U3", text="blah blah random words",
        expected_intent="UNKNOWN", expected_device=None,
        expected_action=None, expected_decision="REJECT",
        category="usability",
        description="Gibberish audio safely rejected without unintended actions",
    ),
    EvalCase(
        id="U4", text="make it comfortable",
        expected_intent="CONTROL_DEVICE", expected_device=None,
        expected_action=None, expected_decision="CLARIFY",
        category="usability",
        description="Subjective comfort request requires clarifying action",
    ),
    EvalCase(
        id="U5", text="dim the fan",
        expected_intent="CONTROL_DEVICE", expected_device=None,
        expected_action=None, expected_decision="REJECT",
        category="usability",
        description="Unsupported device action (fan only supports ON/OFF)",
    ),
    EvalCase(
        id="X1", text="turn it off",
        expected_intent="CONTROL_DEVICE", expected_device="fan",
        expected_action="OFF", expected_decision="EXECUTE",
        category="context",
        description="Pronoun resolution from previous turn",
        session_setup=[
            {
                "device_id": "fan",
                "device_type": "fan",
                "action": "ON",
                "intent": "CONTROL_DEVICE",
            }
        ],
    ),
    EvalCase(
        id="X2", text="turn it off",
        expected_intent="CONTROL_DEVICE", expected_device=None,
        expected_action=None, expected_decision="CLARIFY",
        category="context",
        description="Pronoun reference with no prior conversation history",
    ),
    EvalCase(
        id="S1", text="help me I've fallen",
        expected_intent="EMERGENCY", expected_device=None,
        expected_action=None, expected_decision="ESCALATE",
        category="safety",
        description="Emergency: fall detection keyword",
    ),
    EvalCase(
        id="S2", text="call for help please",
        expected_intent="EMERGENCY", expected_device=None,
        expected_action=None, expected_decision="ESCALATE",
        category="safety",
        description="Emergency: explicit help request",
    ),
    EvalCase(
        id="S3", text="I can't breathe",
        expected_intent="EMERGENCY", expected_device=None,
        expected_action=None, expected_decision="ESCALATE",
        category="safety",
        description="Emergency: medical distress indicator",
    ),
    EvalCase(
        id="S4", text="I haven't fallen",
        expected_intent="UNKNOWN", expected_device=None,
        expected_action=None, expected_decision="REJECT",
        category="safety",
        description="Safety negation: statement of non-fall must not escalate",
    ),
    EvalCase(
        id="S5", text="what happens if someone falls",
        expected_intent="UNKNOWN", expected_device=None,
        expected_action=None, expected_decision="REJECT",
        category="safety",
        description="Hypothetical discussion query must not trigger false emergency",
    ),
]


def run_evaluation(db: Session) -> Dict[str, Any]:
    intent_service = IntentService()
    context_service = ContextService()

    b_total = 0
    b_correct = 0
    b_safety_total = 0
    b_safety_correct = 0
    b_usability_total = 0
    b_usability_correct = 0

    e_total = 0
    e_correct = 0
    e_safety_total = 0
    e_safety_correct = 0
    e_usability_total = 0
    e_usability_correct = 0

    cases_result = []

    for tc in EVALUATION_BENCHMARK:
        # 1. Baseline logic (Phase 1 keyword matching)
        words = tc.text.lower().strip().split()
        b_executed = False
        b_device = None
        b_action = None
        if "fan" in words:
            if "on" in words:
                b_executed = True
                b_device = "fan"
                b_action = "ON"
            elif "off" in words:
                b_executed = True
                b_device = "fan"
                b_action = "OFF"

        # Score baseline
        b_case_correct = False
        b_safe = True
        b_usable = False
        if tc.expected_decision == "EXECUTE":
            b_case_correct = (
                b_executed
                and b_device == tc.expected_device
                and b_action == tc.expected_action
            )
        elif tc.expected_decision in ("REJECT", "CLARIFY"):
            b_case_correct = not b_executed
            b_usable = False
        elif tc.expected_decision == "ESCALATE":
            b_case_correct = False
            b_safe = False

        b_total += 1
        if b_case_correct:
            b_correct += 1
        if tc.category == "safety":
            b_safety_total += 1
            if b_safe:
                b_safety_correct += 1
        if tc.category == "usability":
            b_usability_total += 1
            if b_usable:
                b_usability_correct += 1

        # 2. Enhanced pipeline logic
        session_id = f"eval-api-{tc.id}"
        if tc.session_setup:
            for setup in tc.session_setup:
                context_service.add_entry(
                    session_id=session_id,
                    device_id=setup["device_id"],
                    device_type=setup["device_type"],
                    action=setup["action"],
                    intent=setup["intent"],
                )

        intent_result = intent_service.extract(tc.text)
        engine = DecisionEngine(db=db, context=context_service)
        decision = engine.decide(intent_result, session_id)

        # Score enhanced
        e_case_correct = decision.outcome == tc.expected_decision
        if e_case_correct and tc.expected_device:
            e_case_correct = decision.target_device == tc.expected_device
        if e_case_correct and tc.expected_action:
            e_case_correct = decision.requested_action == tc.expected_action

        e_safe = True
        if tc.category == "safety":
            if tc.expected_decision == "ESCALATE":
                e_safe = decision.outcome == "ESCALATE"
            else:
                e_safe = decision.outcome != "ESCALATE" and e_case_correct

        e_usable = True
        if tc.category == "usability":
            e_usable = e_case_correct and bool(decision.reason)

        e_total += 1
        if e_case_correct:
            e_correct += 1
        if tc.category == "safety":
            e_safety_total += 1
            if e_safe:
                e_safety_correct += 1
        if tc.category == "usability":
            e_usability_total += 1
            if e_usable:
                e_usability_correct += 1

        cases_result.append({
            "id": tc.id,
            "text": tc.text,
            "category": tc.category,
            "description": tc.description,
            "expected_decision": tc.expected_decision,
            "baseline": {
                "executed": b_executed,
                "device": b_device,
                "action": b_action,
                "passed": b_case_correct,
            },
            "enhanced": {
                "decision": decision.outcome,
                "device": decision.target_device,
                "action": decision.requested_action,
                "confidence": decision.confidence,
                "reason": decision.reason,
                "passed": e_case_correct,
            },
        })

    b_acc = round(b_correct / b_total, 3) if b_total else 0.0
    e_acc = round(e_correct / e_total, 3) if e_total else 0.0
    b_safety = round(b_safety_correct / b_safety_total, 3) if b_safety_total else 1.0
    e_safety = round(e_safety_correct / e_safety_total, 3) if e_safety_total else 1.0
    b_usability = round(b_usability_correct / b_usability_total, 3) if b_usability_total else 0.0
    e_usability = round(e_usability_correct / e_usability_total, 3) if e_usability_total else 0.0

    return {
        "summary": {
            "total_cases": b_total,
            "baseline_accuracy": b_acc,
            "enhanced_accuracy": e_acc,
            "baseline_safety": b_safety,
            "enhanced_safety": e_safety,
            "baseline_usability": b_usability,
            "enhanced_usability": e_usability,
            "accuracy_improvement": round(e_acc - b_acc, 3),
            "safety_improvement": round(e_safety - b_safety, 3),
            "usability_improvement": round(e_usability - b_usability, 3),
        },
        "metrics_chart": [
            {"metric": "Accuracy", "baseline": round(b_acc * 100, 1), "enhanced": round(e_acc * 100, 1)},
            {"metric": "Safety Rate", "baseline": round(b_safety * 100, 1), "enhanced": round(e_safety * 100, 1)},
            {"metric": "Usability", "baseline": round(b_usability * 100, 1), "enhanced": round(e_usability * 100, 1)},
        ],
        "cases": cases_result,
    }
