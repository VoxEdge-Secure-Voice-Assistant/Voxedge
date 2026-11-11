"""
Intent service — rule-based natural-language understanding for VoxEdge.

Feature 4: Ambiguity handling, intelligent intent recognition, and indirect
natural-language command interpretation.

Converts transcribed speech into structured intent data containing:
  - raw_text: original transcription
  - intent: intent category (CONTROL_DEVICE, STATUS_CHECK, EMERGENCY, HELP, etc.)
  - target_device / device: identified device or category
  - requested_action / action: ON, OFF, etc.
  - is_ambiguous: whether the command or target is ambiguous
  - requires_clarification: whether clarification is required before execution
  - clarification_prompt: suggested follow-up question
  - reason: explanation of intent decision
  - is_indirect: whether the command is an indirect statement (e.g. "I'm feeling hot")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.services.emergency_detector import EmergencyDetector

if TYPE_CHECKING:
    from app.schemas.voice import StructuredIntent


# ── Intent names (constants) ──────────────────────────────────────────────────
CONTROL_DEVICE = "CONTROL_DEVICE"
STATUS_CHECK = "STATUS_CHECK"
EMERGENCY = "EMERGENCY"
CANCEL = "CANCEL"
CONFIRM = "CONFIRM"
HELP = "HELP"
UNKNOWN = "UNKNOWN"

# ── Device vocabulary ─────────────────────────────────────────────────────────
DEVICE_ALIASES: dict[str, tuple[str | None, str, str | None]] = {
    # Bedroom light & acoustic variants (Vosk often hears "light" as "late" / "lite")
    "bedroom light": ("bedroom_light", "light", "bedroom"),
    "bedroom late": ("bedroom_light", "light", "bedroom"),
    "bedroom lite": ("bedroom_light", "light", "bedroom"),
    "bedroom night": ("bedroom_light", "light", "bedroom"),
    "bedroom like": ("bedroom_light", "light", "bedroom"),
    "bedroom lamp": ("bedroom_light", "light", "bedroom"),
    "bed light": ("bedroom_light", "light", "bedroom"),
    "bed late": ("bedroom_light", "light", "bedroom"),
    "bedside light": ("bedroom_light", "light", "bedroom"),
    "bedside late": ("bedroom_light", "light", "bedroom"),
    "bedside lamp": ("bedroom_light", "light", "bedroom"),
    # Living room light & acoustic variants
    "living room light": ("living_room_light", "light", "living_room"),
    "living room late": ("living_room_light", "light", "living_room"),
    "living room lite": ("living_room_light", "light", "living_room"),
    "living room night": ("living_room_light", "light", "living_room"),
    "living room lamp": ("living_room_light", "light", "living_room"),
    "hall light": ("living_room_light", "light", "living_room"),
    "hall late": ("living_room_light", "light", "living_room"),
    "lounge light": ("living_room_light", "light", "living_room"),
    # Fan & acoustic variants
    "bedroom fan": ("fan", "fan", "bedroom"),
    "ceiling fan": ("fan", "fan", None),
    "fan": ("fan", "fan", None),
    "van": ("fan", "fan", None),
    "fen": ("fan", "fan", None),
    # Generic lights (ambiguous — multiple exist)
    "the lights": ("lights", "light", None),
    "lights": ("lights", "light", None),
    "the light": ("light", "light", None),
    "light": ("light", "light", None),
    "the late": ("light", "light", None),
    "late": ("light", "light", None),
    "the lamp": ("lamp", "light", None),
    "lamp": ("lamp", "light", None),
}

# ── Unsupported Actions Vocabulary ───────────────────────────────────────────
UNSUPPORTED_ACTIONS: dict[str, str] = {
    "dim": "DIM",
    "dimming": "DIM",
    "brighten": "BRIGHTEN",
    "increase speed": "SET_SPEED",
    "speed up": "SET_SPEED",
    "slow down": "SET_SPEED",
    "lock": "LOCK",
    "unlock": "UNLOCK",
    "rotate": "ROTATE",
    "oscillate": "OSCILLATE",
}

# ── Unknown Devices Vocabulary (common smart home nouns not in VoxEdge) ───────
UNKNOWN_DEVICE_NAMES = [
    "tv", "television", "microwave", "radio", "front door", "door", "garage",
    "garage door", "oven", "refrigerator", "fridge", "heater", "ac", "air conditioner",
    "thermostat", "music", "stereo", "computer", "blinds", "curtains", "kettle",
]

# ── Action vocabulary ─────────────────────────────────────────────────────────
ON_WORDS = {"on", "start", "enable", "activate", "switch on", "power on", "open"}
OFF_WORDS = {"off", "stop", "disable", "deactivate", "switch off", "power off", "close", "shut"}

# ── Emergency triggers ────────────────────────────────────────────────────────
EMERGENCY_PHRASES = [
    "help me", "emergency", "call for help", "i need help",
    "i've fallen", "i fell", "call ambulance", "call doctor",
    "i can't breathe", "chest pain", "i'm hurt", "sos",
    "someone help", "please help", "need assistance",
]

# ── Confirmation / cancellation ───────────────────────────────────────────────
CONFIRM_WORDS = {"yes", "yeah", "yep", "confirm", "sure", "okay", "ok", "do it", "go ahead", "proceed"}
CANCEL_WORDS = {"no", "nope", "cancel", "stop", "never mind", "nevermind", "forget it", "abort"}

# ── Status-check triggers ────────────────────────────────────────────────────
STATUS_PATTERNS = [
    r"\b(?:is|are)\b.*\b(?:on|off|running|working)\b",
    r"\bstatus\b",
    r"\bwhat.*state\b",
    r"\bhow.*(?:light|fan|lamp)\b",
    r"\bcheck\b.*\b(?:light|fan|lamp)\b",
]

# ── Help triggers ─────────────────────────────────────────────────────────────
HELP_PATTERNS = [
    r"\bwhat can you do\b",
    r"\bhelp\b",
    r"\bcommands\b",
    r"\bwhat.*commands\b",
    r"\blist.*(?:device|action)\b",
]


@dataclass
class IntentResult:
    """Structured output of intent extraction."""

    intent: str = UNKNOWN
    confidence: float = 0.0
    entities: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    is_ambiguous: bool = False
    requires_clarification: bool = False
    reason: str = ""
    target_device: str | None = None
    requested_action: str | None = None
    is_indirect: bool = False
    suggested_action: str | None = None
    suggested_device: str | None = None
    clarification_prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to simple dict representation."""
        return {
            "intent": self.intent,
            "device": self.target_device or self.entities.get("device"),
            "action": self.requested_action or self.entities.get("action"),
            "is_ambiguous": self.is_ambiguous,
            "requires_clarification": self.requires_clarification,
            "reason": self.reason,
            "raw_text": self.raw_text,
            "confidence": self.confidence,
        }

    def to_structured(self) -> StructuredIntent:
        """Convert to Pydantic StructuredIntent model."""
        from app.schemas.voice import StructuredIntent

        dev = self.target_device or self.entities.get("device")
        act = self.requested_action or self.entities.get("action")
        return StructuredIntent(
            raw_text=self.raw_text,
            intent=self.intent,
            device=dev,
            device_type=self.entities.get("device_type"),
            location=self.entities.get("location"),
            action=act,
            is_ambiguous=self.is_ambiguous,
            requires_clarification=self.requires_clarification,
            clarification_prompt=self.clarification_prompt,
            confidence=self.confidence,
            reason=self.reason,
            is_indirect=self.is_indirect,
            suggested_action=self.suggested_action,
            suggested_device=self.suggested_device,
        )


class IntentService:
    """
    Modular, rule-based natural language intent extractor.

    Converts speech/text into structured intents with ambiguity detection,
    indirect statement interpretation, and actionable clarification prompts.
    """

    def extract(self, text: str) -> IntentResult:
        """Extract structured intent and entities from raw text."""
        if not text or not text.strip():
            return IntentResult(
                intent=UNKNOWN,
                confidence=0.0,
                raw_text=text or "",
                is_ambiguous=True,
                requires_clarification=True,
                reason="Input text is empty.",
                entities={"reason": "empty_input"},
            )

        cleaned = text.lower().strip()

        # ── Priority 1: Emergency ─────────────────────────────────────────
        result = self._check_emergency(cleaned)
        if result:
            return result

        # ── Priority 2: Cancel / Confirm ──────────────────────────────────
        result = self._check_cancel_confirm(cleaned)
        if result:
            return result

        # ── Priority 3: Help ──────────────────────────────────────────────
        result = self._check_help(cleaned)
        if result:
            return result

        # ── Priority 4: Indirect statements & comfort requests ────────────
        result = self._check_indirect_statement(cleaned)
        if result:
            return result

        # ── Priority 5: Status check ──────────────────────────────────────
        result = self._check_status(cleaned)
        if result:
            return result

        # ── Priority 6: Device control (direct & ambiguous) ───────────────
        result = self._check_control(cleaned)
        if result:
            return result

        # ── Fallback: Unknown ─────────────────────────────────────────────
        return IntentResult(
            intent=UNKNOWN,
            confidence=0.0,
            raw_text=text,
            is_ambiguous=True,
            requires_clarification=False,
            reason="No known command pattern or device could be recognized.",
            entities={"reason": "no_matching_pattern"},
        )

    # ── Matchers ──────────────────────────────────────────────────────────

    def _check_emergency(self, text: str) -> IntentResult | None:
        detector = EmergencyDetector()
        res = detector.detect(text)
        if res.is_emergency:
            return IntentResult(
                intent=EMERGENCY,
                confidence=1.0,
                raw_text=text,
                is_ambiguous=False,
                requires_clarification=res.requires_clarification,
                clarification_prompt=res.clarification_prompt,
                reason=res.detection_reason,
                entities={
                    "trigger_phrase": res.matched_pattern,
                    "category": res.category,
                    "severity": res.severity,
                    "recommended_response": res.recommended_response,
                    "emergency_detection": res.to_dict(),
                },
            )
        return None

    def _check_cancel_confirm(self, text: str) -> IntentResult | None:
        words = set(re.findall(r"\b\w+\b", text.lower()))
        for phrase in CANCEL_WORDS:
            if " " in phrase and phrase in text:
                return IntentResult(
                    intent=CANCEL,
                    confidence=0.9,
                    raw_text=text,
                    reason="Cancellation phrase detected.",
                    entities={},
                )
        for phrase in CONFIRM_WORDS:
            if " " in phrase and phrase in text:
                return IntentResult(
                    intent=CONFIRM,
                    confidence=0.9,
                    raw_text=text,
                    reason="Confirmation phrase detected.",
                    entities={},
                )
        if words & CANCEL_WORDS:
            return IntentResult(
                intent=CANCEL,
                confidence=0.8,
                raw_text=text,
                reason="Cancellation word detected.",
                entities={},
            )
        if words & CONFIRM_WORDS:
            return IntentResult(
                intent=CONFIRM,
                confidence=0.8,
                raw_text=text,
                reason="Confirmation word detected.",
                entities={},
            )
        return None

    def _check_help(self, text: str) -> IntentResult | None:
        for pattern in HELP_PATTERNS:
            if re.search(pattern, text):
                return IntentResult(
                    intent=HELP,
                    confidence=0.9,
                    raw_text=text,
                    reason="User requested system help or capabilities.",
                    entities={},
                )
        return None

    def _check_indirect_statement(self, text: str) -> IntentResult | None:
        """
        Check for natural-language indirect expressions of state/comfort.
        Examples:
          - "It's too dark." / "Too dark" → suggests Light ON.
          - "It's too bright." / "Too bright" → suggests Light dim/off.
          - "I'm feeling hot." / "It's too hot" → suggests Fan ON.
          - "It's too cold." / "Feeling cold" → suggests Fan OFF.
          - "Make it comfortable." / "Change the settings." → ambiguous comfort request.
        """
        # 1. Darkness → suggests light ON
        if re.search(r"\b(?:it(?:'?s| is)?\s+)?(?:too\s+)?dark\b|\bcan(?:'?t| not)?\s+see\b|\bneed\s+(?:more\s+)?light\b", text):
            prompt = "It sounds like it's too dark. Which light would you like me to turn on: the Bedroom Light or the Living Room Light?"
            return IntentResult(
                intent=CONTROL_DEVICE,
                confidence=0.85,
                raw_text=text,
                is_indirect=True,
                is_ambiguous=True,
                requires_clarification=True,
                suggested_action="ON",
                suggested_device="lights",
                clarification_prompt=prompt,
                reason="Indirect expression indicating darkness. Suggests turning on lights.",
                entities={
                    "is_indirect": True,
                    "device_type": "light",
                    "device_ambiguous": True,
                    "suggested_action": "ON",
                    "action": "ON",
                    "clarification_prompt": prompt,
                },
            )

        # 2. Brightness → suggests light DIM or OFF
        if re.search(r"\b(?:it(?:'?s| is)?\s+)?(?:too\s+)?bright\b|\bblinding\b|\bhurts?\s+my\s+eyes\b", text):
            prompt = "The lights do not support dimming. Would you like me to turn off the Bedroom Light or the Living Room Light?"
            return IntentResult(
                intent=CONTROL_DEVICE,
                confidence=0.85,
                raw_text=text,
                is_indirect=True,
                is_ambiguous=True,
                requires_clarification=True,
                suggested_action="OFF",
                suggested_device="lights",
                clarification_prompt=prompt,
                reason="Indirect expression indicating excess brightness. Dimming is unsupported on these lights.",
                entities={
                    "is_indirect": True,
                    "device_type": "light",
                    "device_ambiguous": True,
                    "suggested_action": "OFF",
                    "action": "OFF",
                    "unsupported_intent": "DIM",
                    "clarification_prompt": prompt,
                },
            )

        # 3. Heat / Warmth → suggests fan ON
        if re.search(r"\b(?:i(?:'?m| am)?\s+)?(?:feeling\s+)?(?:too\s+)?hot\b|\b(?:it(?:'?s| is)?\s+)?(?:too\s+)?warm\b|\bstuffy\b|\bsweating\b", text):
            prompt = "You mentioned you're feeling hot. Would you like me to turn on the fan?"
            return IntentResult(
                intent=CONTROL_DEVICE,
                confidence=0.85,
                raw_text=text,
                is_indirect=True,
                is_ambiguous=True,
                requires_clarification=True,
                target_device="fan",
                requested_action="ON",
                suggested_device="fan",
                suggested_action="ON",
                clarification_prompt=prompt,
                reason="Indirect expression indicating heat. Cautiously clarifies whether to turn on the fan.",
                entities={
                    "is_indirect": True,
                    "device": "fan",
                    "device_type": "fan",
                    "suggested_action": "ON",
                    "action": "ON",
                    "requires_clarification": True,
                    "clarification_prompt": prompt,
                },
            )

        # 4. Cold / Chilly / Cool → suggests fan OFF
        if re.search(r"\b(?:i(?:'?m| am)?\s+)?(?:feeling\s+)?(?:too\s+)?(?:cold|cool)\b|\b(?:it(?:'?s| is)?\s+)?(?:too\s+)?(?:chilly|cool)\b|\bfreezing\b|\bshivering\b", text):
            prompt = "You mentioned you're feeling cold. Would you like me to turn off the fan?"
            return IntentResult(
                intent=CONTROL_DEVICE,
                confidence=0.85,
                raw_text=text,
                is_indirect=True,
                is_ambiguous=True,
                requires_clarification=True,
                target_device="fan",
                requested_action="OFF",
                suggested_device="fan",
                suggested_action="OFF",
                clarification_prompt=prompt,
                reason="Indirect expression indicating cold. Cautiously clarifies whether to turn off the fan.",
                entities={
                    "is_indirect": True,
                    "device": "fan",
                    "device_type": "fan",
                    "suggested_action": "OFF",
                    "action": "OFF",
                    "requires_clarification": True,
                    "clarification_prompt": prompt,
                },
            )

        # 5. General comfort / settings request → ambiguous
        if re.search(r"\bmake\s+it\s+comfortable\b|\bchange\s+(?:the\s+)?settings\b|\badjust\s+(?:the\s+)?settings\b|\bfix\s+the\s+room\b", text):
            prompt = "Would you like me to adjust the fan or the lights?"
            return IntentResult(
                intent=CONTROL_DEVICE,
                confidence=0.75,
                raw_text=text,
                is_indirect=True,
                is_ambiguous=True,
                requires_clarification=True,
                clarification_prompt=prompt,
                reason="Ambiguous comfort or settings request without specified device or operation.",
                entities={
                    "is_ambiguous": True,
                    "device_missing": True,
                    "action_missing": True,
                    "clarification_prompt": prompt,
                },
            )

        return None

    def _check_status(self, text: str) -> IntentResult | None:
        for pattern in STATUS_PATTERNS:
            if re.search(pattern, text):
                device_info = self._extract_device(text)
                entities: dict[str, Any] = {}
                confidence = 0.7
                is_ambiguous = False
                device_id = None

                if device_info:
                    device_id = device_info["device_id"]
                    entities["device"] = device_id
                    entities["device_type"] = device_info["device_type"]
                    if device_info.get("location"):
                        entities["location"] = device_info["location"]
                    if device_id is not None and device_id not in ("light", "lights"):
                        confidence = 0.9
                    else:
                        is_ambiguous = True
                else:
                    is_ambiguous = True

                return IntentResult(
                    intent=STATUS_CHECK,
                    confidence=confidence,
                    raw_text=text,
                    target_device=device_id,
                    is_ambiguous=is_ambiguous,
                    requires_clarification=is_ambiguous,
                    reason="Status check query.",
                    entities=entities,
                )
        return None

    def _check_control(self, text: str) -> IntentResult | None:
        """Extract CONTROL_DEVICE intent with device and action entities."""
        action = self._extract_action(text)
        unsupported_action = self._extract_unsupported_action(text)
        device_info = self._extract_device(text)
        unknown_device = self._extract_unknown_device(text)

        # If user mentioned an unsupported action (e.g. "dim")
        if unsupported_action and not action:
            action = unsupported_action

        # Check for pronoun reference without device ("turn it off", "switch that on", "stop it")
        has_pronoun = bool(re.search(r"\b(?:it|that|this|the\s+same)\b", text))

        if action is None and device_info is None and not has_pronoun and not unknown_device:
            return None

        entities: dict[str, Any] = {}
        confidence = 0.0
        is_ambiguous = False
        requires_clarification = False
        reason = ""
        clarification_prompt = None
        target_device = None

        # ── Check Unknown Device ──────────────────────────────────────────
        if unknown_device and not device_info:
            entities["device"] = unknown_device
            entities["unknown_device"] = True
            entities["action"] = action
            return IntentResult(
                intent=CONTROL_DEVICE,
                confidence=0.7,
                raw_text=text,
                target_device=unknown_device,
                requested_action=action,
                is_ambiguous=False,
                requires_clarification=False,
                reason=f"Device '{unknown_device}' is not registered or supported.",
                entities=entities,
            )

        # ── Check Action ──────────────────────────────────────────────────
        if action:
            entities["action"] = action
            confidence += 0.4
        else:
            entities["action"] = None
            entities["action_missing"] = True
            is_ambiguous = True
            requires_clarification = True

        # ── Check Device ──────────────────────────────────────────────────
        if device_info:
            target_device = device_info["device_id"]
            entities["device"] = target_device
            entities["device_type"] = device_info["device_type"]
            if device_info.get("location"):
                entities["location"] = device_info["location"]

            # Fully resolved specific device (e.g. "fan", "bedroom_light")
            if target_device and target_device not in ("light", "lights", "lamp"):
                confidence += 0.6
                reason = f"Identified device '{target_device}' and action '{action}'."
            else:
                # Generic light reference (e.g. "the lights", "turn off the light")
                confidence += 0.4
                is_ambiguous = True
                requires_clarification = True
                entities["device_ambiguous"] = True
                act_str = action.lower() if action else "adjust"
                clarification_prompt = f"Which light would you like me to turn {act_str}: the Bedroom Light or the Living Room Light?"
                reason = "Multiple lights available in bedroom and living room."
        elif has_pronoun:
            entities["pronoun_reference"] = True
            is_ambiguous = True
            requires_clarification = True
            act_str = action.lower() if action else "adjust"
            clarification_prompt = f"Which device would you like me to turn {act_str}: the fan or the lights?"
            reason = "Command contains a pronoun without target device specified."
            confidence += 0.3
        else:
            entities["device_missing"] = True
            is_ambiguous = True
            requires_clarification = True
            clarification_prompt = "Which device would you like to control?"
            reason = "No target device could be identified in the command."

        confidence = min(max(confidence, 0.3), 1.0)

        # If unsupported action detected (e.g. "dim")
        if unsupported_action:
            entities["unsupported_action"] = unsupported_action
            reason = f"Action '{unsupported_action}' is not supported for this device."

        return IntentResult(
            intent=CONTROL_DEVICE,
            confidence=round(confidence, 2),
            raw_text=text,
            target_device=target_device,
            requested_action=action,
            is_ambiguous=is_ambiguous,
            requires_clarification=requires_clarification,
            clarification_prompt=clarification_prompt,
            reason=reason,
            entities=entities,
        )

    def _extract_action(self, text: str) -> str | None:
        """Determine ON or OFF from text."""
        words = text.split()
        word_set = set(words)

        # Multi-word actions first
        for phrase in sorted(ON_WORDS, key=len, reverse=True):
            if " " in phrase and phrase in text:
                return "ON"
        for phrase in sorted(OFF_WORDS, key=len, reverse=True):
            if " " in phrase and phrase in text:
                return "OFF"

        if re.search(r"\bturn\s+on\b|\bswitch\s+on\b|\bpower\s+on\b", text):
            return "ON"
        if re.search(r"\bturn\s+off\b|\bswitch\s+off\b|\bpower\s+off\b", text):
            return "OFF"
        if re.search(r"\bturn\b.*\bon\b|\bswitch\b.*\bon\b", text):
            return "ON"
        if re.search(r"\bturn\b.*\boff\b|\bswitch\b.*\boff\b", text):
            return "OFF"

        if word_set & ON_WORDS:
            return "ON"
        if word_set & OFF_WORDS:
            return "OFF"

        # Vosk mis-hears
        if "of" in word_set and ("fan" in word_set or "light" in word_set or "lights" in word_set or "lamp" in word_set):
            return "OFF"

        return None

    def _extract_unsupported_action(self, text: str) -> str | None:
        """Detect actions like 'dim', 'brighten', etc. not supported by binary state."""
        for phrase, act in UNSUPPORTED_ACTIONS.items():
            if re.search(rf"\b{re.escape(phrase)}\b", text):
                return act
        return None

    def _extract_device(self, text: str) -> dict[str, Any] | None:
        """Find the longest matching device alias in text."""
        for alias in sorted(DEVICE_ALIASES.keys(), key=len, reverse=True):
            # Match word boundary
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, text):
                device_id, device_type, location = DEVICE_ALIASES[alias]
                return {
                    "device_id": device_id,
                    "device_type": device_type,
                    "location": location,
                    "matched_alias": alias,
                }
        return None

    def _extract_unknown_device(self, text: str) -> str | None:
        """Detect mentions of unsupported smart home items (e.g. TV, microwave)."""
        for noun in sorted(UNKNOWN_DEVICE_NAMES, key=len, reverse=True):
            pattern = rf"\b{re.escape(noun)}\b"
            if re.search(pattern, text):
                return noun
        return None
