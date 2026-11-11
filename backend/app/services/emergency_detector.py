"""
Emergency Detection Module — deterministic rule-based emergency phrase detector.

Detects potential emergency statements in recognized speech using:
  - Normalized phrase matching with category classification
  - Negation filtering ("I haven't fallen" is NOT an emergency)
  - Hypothetical/question filtering ("What if I fall?" is NOT an emergency)
  - Severity classification
  - Structured result output

LIMITATIONS:
  - Cannot reliably diagnose medical emergencies.
  - Relies on text that has already been through speech recognition;
    recognition errors may cause false negatives.
  - Negation and hypothetical filtering uses heuristics and may not
    cover every phrasing.
  - Does not detect emergencies from non-verbal cues (silence, crashes, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Emergency Categories ─────────────────────────────────────────────────────

class EmergencyCategory(str, Enum):
    FALL = "FALL"
    BREATHING = "BREATHING"
    PAIN = "PAIN"
    GENERAL_DISTRESS = "GENERAL_DISTRESS"
    CALL_FOR_HELP = "CALL_FOR_HELP"
    UNKNOWN = "UNKNOWN"


# ── Category → severity mapping ──────────────────────────────────────────────

CATEGORY_SEVERITY: dict[EmergencyCategory, str] = {
    EmergencyCategory.FALL: "HIGH",
    EmergencyCategory.BREATHING: "CRITICAL",
    EmergencyCategory.PAIN: "HIGH",
    EmergencyCategory.GENERAL_DISTRESS: "MEDIUM",
    EmergencyCategory.CALL_FOR_HELP: "HIGH",
    EmergencyCategory.UNKNOWN: "MEDIUM",
}

# ── Category → recommended response ──────────────────────────────────────────

CATEGORY_RESPONSE: dict[EmergencyCategory, str] = {
    EmergencyCategory.FALL: "Fall detected. Simulated alert sent to emergency contacts. Stay still and help is on the way.",
    EmergencyCategory.BREATHING: "Breathing difficulty detected. Simulated alert sent to emergency contacts and medical service.",
    EmergencyCategory.PAIN: "Pain reported. Simulated alert sent to emergency contacts.",
    EmergencyCategory.GENERAL_DISTRESS: "Distress detected. Simulated alert sent to emergency contacts.",
    EmergencyCategory.CALL_FOR_HELP: "Help request received. Simulated alert sent to emergency contacts.",
    EmergencyCategory.UNKNOWN: "Potential emergency detected. Simulated alert sent to emergency contacts.",
}


# ── Emergency phrase patterns ────────────────────────────────────────────────
# Each entry: (compiled regex, category, base description)

_EMERGENCY_PATTERNS: list[tuple[str, EmergencyCategory, str]] = [
    # ── FALL ──────────────────────────────────────────────────────────────
    (r"\bi(?:'?ve| have)?\s+fallen\b", EmergencyCategory.FALL, "Reported a fall"),
    (r"\bi\s+fell\b", EmergencyCategory.FALL, "Reported a fall"),
    (r"\bi(?:'?m| am)?\s+on\s+the\s+(?:floor|ground)\b", EmergencyCategory.FALL, "Reported being on the floor"),
    (r"\bcan(?:'?t| not)\s+get\s+up\b", EmergencyCategory.FALL, "Cannot get up"),
    (r"\bfallen\s+down\b", EmergencyCategory.FALL, "Reported falling down"),
    (r"\bslipped\s+and\s+fell\b", EmergencyCategory.FALL, "Reported slipping and falling"),
    (r"\bfallen\s+and\s+can(?:'?t| not)\b", EmergencyCategory.FALL, "Fallen and unable"),
    (r"\bi\s+tripped\b", EmergencyCategory.FALL, "Reported tripping"),

    # ── BREATHING ─────────────────────────────────────────────────────────
    (r"\bcan(?:'?t| not)\s+breathe?\b", EmergencyCategory.BREATHING, "Breathing difficulty"),
    (r"\bdifficulty\s+breathing\b", EmergencyCategory.BREATHING, "Breathing difficulty"),
    (r"\bhard\s+to\s+breathe?\b", EmergencyCategory.BREATHING, "Breathing difficulty"),
    (r"\bshort(?:ness)?\s+of\s+breath\b", EmergencyCategory.BREATHING, "Shortness of breath"),
    (r"\bcan(?:'?t| not)\s+catch\s+my\s+breath\b", EmergencyCategory.BREATHING, "Cannot catch breath"),
    (r"\bchoking\b", EmergencyCategory.BREATHING, "Choking reported"),
    (r"\bsuffocating\b", EmergencyCategory.BREATHING, "Suffocation reported"),
    (r"\bhaving\s+(?:trouble|difficulty|problem)\s+breathing\b", EmergencyCategory.BREATHING, "Breathing trouble"),

    # ── PAIN ──────────────────────────────────────────────────────────────
    (r"\bchest\s+pain\b", EmergencyCategory.PAIN, "Chest pain reported"),
    (r"\bsevere\s+pain\b", EmergencyCategory.PAIN, "Severe pain reported"),
    (r"\bheart\s+(?:attack|hurts?)\b", EmergencyCategory.PAIN, "Heart-related pain"),
    (r"\bi(?:'?m| am)?\s+(?:really\s+)?hurt\b", EmergencyCategory.PAIN, "Injury reported"),
    (r"\bi(?:'?m| am)?\s+(?:in\s+)?(?:a\s+lot\s+of\s+)?pain\b", EmergencyCategory.PAIN, "Pain reported"),
    (r"\bi(?:'?m| am)?\s+(?:badly\s+)?injured\b", EmergencyCategory.PAIN, "Injury reported"),
    (r"\bbleeding\b", EmergencyCategory.PAIN, "Bleeding reported"),

    # ── CALL_FOR_HELP ─────────────────────────────────────────────────────
    (r"\bcall\s+(?:an?\s+)?ambulance\b", EmergencyCategory.CALL_FOR_HELP, "Ambulance requested"),
    (r"\bcall\s+(?:a\s+)?doctor\b", EmergencyCategory.CALL_FOR_HELP, "Doctor requested"),
    (r"\bcall\s+(?:for\s+)?help\b", EmergencyCategory.CALL_FOR_HELP, "Help call requested"),
    (r"\bcall\s+(?:the\s+)?(?:police|fire|emergency|nine one one|911)\b", EmergencyCategory.CALL_FOR_HELP, "Emergency services requested"),
    (r"\bplease\s+(?:call|send)\s+(?:for\s+)?help\b", EmergencyCategory.CALL_FOR_HELP, "Help requested"),
    (r"\bneed\s+(?:an?\s+)?ambulance\b", EmergencyCategory.CALL_FOR_HELP, "Ambulance needed"),

    # ── GENERAL_DISTRESS ──────────────────────────────────────────────────
    (r"\bhelp\s+me\b", EmergencyCategory.GENERAL_DISTRESS, "Help requested"),
    (r"\bi\s+need\s+help\b", EmergencyCategory.GENERAL_DISTRESS, "Help needed"),
    (r"\bsomeone\s+help\b", EmergencyCategory.GENERAL_DISTRESS, "Help requested"),
    (r"\bplease\s+help\b", EmergencyCategory.GENERAL_DISTRESS, "Help requested"),
    (r"\bhelp\b", EmergencyCategory.GENERAL_DISTRESS, "Help requested"),
    (r"\bneed\s+(?:emergency\s+)?assistance\b", EmergencyCategory.GENERAL_DISTRESS, "Assistance needed"),
    (r"\bemergency\b", EmergencyCategory.GENERAL_DISTRESS, "Emergency keyword"),
    (r"\bsos\b", EmergencyCategory.GENERAL_DISTRESS, "SOS signal"),
    (r"\bi(?:'?m| am)?\s+(?:feeling\s+)?(?:very\s+)?(?:dizzy|faint|weak|unwell|sick)\b", EmergencyCategory.GENERAL_DISTRESS, "Feeling unwell"),
    (r"\bi(?:'?m| am)?\s+(?:going\s+to\s+)?(?:pass|faint)\s+out\b", EmergencyCategory.GENERAL_DISTRESS, "Fainting"),
    (r"\bi\s+need\s+emergency\s+assistance\b", EmergencyCategory.GENERAL_DISTRESS, "Emergency assistance needed"),
]

# Compile patterns once
COMPILED_PATTERNS: list[tuple[re.Pattern, EmergencyCategory, str]] = [
    (re.compile(pat, re.IGNORECASE), cat, desc)
    for pat, cat, desc in _EMERGENCY_PATTERNS
]


# ── Negation patterns ────────────────────────────────────────────────────────
# These indicate the speaker is negating an emergency condition.
NEGATION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bi\s+(?:have\s+)?(?:not|n't|haven't|didn't|don't)\s+fallen\b", re.IGNORECASE),
    re.compile(r"\bi\s+(?:have\s+)?(?:not|n't|haven't)\s+fell\b", re.IGNORECASE),
    re.compile(r"\bi\s+(?:did\s+)?(?:not|n't|didn't)\s+fall\b", re.IGNORECASE),
    re.compile(r"\bi\s+(?:am\s+)?(?:not|n't)\s+(?:hurt|injured|in\s+pain)\b", re.IGNORECASE),
    re.compile(r"\bi\s+(?:can|am\s+able\s+to)\s+breathe?\s+(?:fine|okay|now|normally)\b", re.IGNORECASE),
    re.compile(r"\bi\s+(?:don't|do\s+not)\s+need\s+(?:help|assistance|an?\s+ambulance)\b", re.IGNORECASE),
    re.compile(r"\bi\s+(?:haven't|have\s+not)\s+fallen\b", re.IGNORECASE),
    re.compile(r"\bno\s+emergency\b", re.IGNORECASE),
    re.compile(r"\bnot\s+(?:an?\s+)?emergency\b", re.IGNORECASE),
    re.compile(r"\bfalse\s+alarm\b", re.IGNORECASE),
    re.compile(r"\bi(?:'?m| am)?\s+(?:fine|okay|alright|all\s+right)\b", re.IGNORECASE),
]


# ── Hypothetical / question patterns ─────────────────────────────────────────
# These indicate the speaker is asking a hypothetical question, not reporting.
HYPOTHETICAL_PATTERNS: list[re.Pattern] = [
    re.compile(r"^what\s+(?:if|would|should|happens?)\b", re.IGNORECASE),
    re.compile(r"^(?:if|suppose|imagine|say)\s+(?:i|someone|a\s+person)\b", re.IGNORECASE),
    re.compile(r"^(?:how|what)\s+(?:do|does|would|should|can)\b.*\b(?:fall\w*|breathe\w*|emergency\w*|hurt\w*)\b", re.IGNORECASE),
    re.compile(r"^(?:can|could|would)\s+you\s+(?:detect|recognize|handle|help)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:does|is)\s+.*\bemergency\b", re.IGNORECASE),
    re.compile(r"\bhow\s+does\s+.*\bemergency\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+happens\s+if\b", re.IGNORECASE),
    re.compile(r"\bis\s+it\s+(?:an?\s+)?emergency\s+if\b", re.IGNORECASE),
    re.compile(r"\b(?:handle|deal\s+with)\s+if\s+(?:i|someone|anybody|a\s+person)\s+fall\w*\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+can\s+you\s+do\b", re.IGNORECASE),
    re.compile(r"\b(?:list|show|what)\s+(?:are\s+the\s+)?commands\b", re.IGNORECASE),
]


# ── Structured detection result ──────────────────────────────────────────────

@dataclass
class EmergencyDetectionResult:
    """Structured output from the emergency detector."""

    is_emergency: bool = False
    category: str = EmergencyCategory.UNKNOWN.value
    severity: str = "MEDIUM"
    matched_pattern: str = ""
    detection_reason: str = ""
    recommended_response: str = ""
    requires_clarification: bool = False
    clarification_prompt: str | None = None
    is_negated: bool = False
    is_hypothetical: bool = False
    raw_text: str = ""
    all_matches: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_emergency": self.is_emergency,
            "category": self.category,
            "severity": self.severity,
            "matched_pattern": self.matched_pattern,
            "detection_reason": self.detection_reason,
            "recommended_response": self.recommended_response,
            "requires_clarification": self.requires_clarification,
            "clarification_prompt": self.clarification_prompt,
            "is_negated": self.is_negated,
            "is_hypothetical": self.is_hypothetical,
        }

    def to_response(self):
        """Convert to Pydantic EmergencyDetectionResponse."""
        from app.schemas.emergency import EmergencyDetectionResponse

        return EmergencyDetectionResponse(
            is_emergency=self.is_emergency,
            category=self.category,
            severity=self.severity,
            matched_pattern=self.matched_pattern,
            detection_reason=self.detection_reason,
            recommended_response=self.recommended_response,
            requires_clarification=self.requires_clarification,
            clarification_prompt=self.clarification_prompt,
            is_negated=self.is_negated,
            is_hypothetical=self.is_hypothetical,
        )


# ── Detector class ───────────────────────────────────────────────────────────

class EmergencyDetector:
    """
    Deterministic, rule-based emergency phrase detector.

    Scans normalized text for emergency patterns, filters out negations
    and hypotheticals, classifies the emergency category, and returns
    a structured result.

    This detector does NOT claim to reliably diagnose medical emergencies.
    It is a first-line screening tool intended to flag potentially critical
    statements for further action.
    """

    def detect(self, text: str) -> EmergencyDetectionResult:
        """
        Analyze text for emergency indicators.

        Returns an EmergencyDetectionResult with classification details.
        """
        if not text or not text.strip():
            return EmergencyDetectionResult(
                is_emergency=False,
                detection_reason="Empty or unintelligible input.",
                raw_text=text or "",
            )

        cleaned = text.strip()
        lower = cleaned.lower()

        # ── Step 1: Check for hypothetical / question framing ────────────
        for hyp_pat in HYPOTHETICAL_PATTERNS:
            if hyp_pat.search(lower):
                return EmergencyDetectionResult(
                    is_emergency=False,
                    is_hypothetical=True,
                    detection_reason=f"Hypothetical or question framing detected: '{cleaned}'",
                    raw_text=cleaned,
                )

        # ── Step 2: Check for negation ───────────────────────────────────
        has_negation = any(neg_pat.search(lower) for neg_pat in NEGATION_PATTERNS)

        # ── Step 3: Scan for emergency patterns ──────────────────────────
        matches: list[tuple[EmergencyCategory, str, str]] = []
        for compiled_pat, category, description in COMPILED_PATTERNS:
            m = compiled_pat.search(lower)
            if m:
                matches.append((category, description, m.group(0)))

        # ── Step 4: If negated, do NOT classify as emergency ─────────────
        if has_negation:
            primary_cat = matches[0][0].value if matches else "UNKNOWN"
            primary_match = matches[0][2] if matches else ""
            return EmergencyDetectionResult(
                is_emergency=False,
                is_negated=True,
                category=primary_cat,
                matched_pattern=primary_match,
                detection_reason="Emergency pattern negated or negative emergency report detected.",
                raw_text=cleaned,
            )

        if not matches:
            return EmergencyDetectionResult(
                is_emergency=False,
                detection_reason="No emergency pattern matched.",
                raw_text=cleaned,
            )

        # ── Step 5: Classify using highest-severity match ────────────────
        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        best_match = max(
            matches,
            key=lambda m: severity_order.get(CATEGORY_SEVERITY.get(m[0], "MEDIUM"), 2),
        )
        primary_cat, primary_desc, primary_match = best_match
        severity = CATEGORY_SEVERITY.get(primary_cat, "MEDIUM")
        response = CATEGORY_RESPONSE.get(primary_cat, CATEGORY_RESPONSE[EmergencyCategory.UNKNOWN])

        all_matches_list = [
            {"category": cat.value, "description": desc, "matched": matched}
            for cat, desc, matched in matches
        ]

        # ── Step 6: Check if clarification might be appropriate ──────────
        # For lower-confidence single-word matches like just "emergency",
        # or ambiguous statements, suggest clarification
        requires_clarification = False
        clarification_prompt = None

        if len(lower.split()) <= 2 and primary_cat == EmergencyCategory.GENERAL_DISTRESS:
            # Very short utterance like "emergency" — might be accidental
            requires_clarification = True
            clarification_prompt = "I detected a possible emergency. Are you okay? Do you need help?"

        return EmergencyDetectionResult(
            is_emergency=True,
            category=primary_cat.value,
            severity=severity,
            matched_pattern=primary_match,
            detection_reason=f"Emergency detected: {primary_desc}. Matched: '{primary_match}'",
            recommended_response=response,
            requires_clarification=requires_clarification,
            clarification_prompt=clarification_prompt,
            raw_text=cleaned,
            all_matches=all_matches_list,
        )
