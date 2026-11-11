"""
Context-Aware Command Interpreter for VoxEdge.

Interprets natural-language commands and indirect statements in the context
of active conversation history and current simulated device states.

Outputs structured proposals (e.g. {"intent": "CONTROL_DEVICE", "device": "fan", "action": "OFF"})
that must be validated by the backend decision engine before any device action is executed.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.models.device import Device
from app.services.context_service import ContextService

logger = logging.getLogger(__name__)


# ── Vocabulary & Patterns ───────────────────────────────────────────────────

COOL_PATTERNS = [
    r"\b(?:it(?:'?s| is)?\s+)?(?:too\s+)?cool\b",
    r"\b(?:it(?:'?s| is)?\s+)?(?:too\s+)?cold\b",
    r"\b(?:it(?:'?s| is)?\s+)?(?:too\s+)?chilly\b",
    r"\b(?:i(?:'?m| am)?\s+)?(?:feeling\s+)?(?:too\s+)?cool\b",
    r"\b(?:i(?:'?m| am)?\s+)?(?:feeling\s+)?(?:too\s+)?cold\b",
    r"\b(?:i(?:'?m| am)?\s+)?(?:feeling\s+)?(?:too\s+)?chilly\b",
    r"\bfreezing\b",
    r"\bshivering\b",
]

HOT_PATTERNS = [
    r"\b(?:i(?:'?m| am)?\s+)?(?:feeling\s+)?(?:too\s+)?hot\b",
    r"\b(?:i(?:'?m| am)?\s+)?(?:feeling\s+)?(?:too\s+)?warm\b",
    r"\b(?:it(?:'?s| is)?\s+)?(?:too\s+)?hot\b",
    r"\b(?:it(?:'?s| is)?\s+)?(?:too\s+)?warm\b",
    r"\bstuffy\b",
    r"\bsweating\b",
]

DARK_PATTERNS = [
    r"\b(?:it(?:'?s| is)?\s+)?(?:too\s+)?dark\b",
    r"\bcan(?:'?t| not)?\s+see\b",
    r"\bneed\s+(?:more\s+)?light\b",
    r"\bhard\s+to\s+see\b",
]

BRIGHT_PATTERNS = [
    r"\b(?:it(?:'?s| is)?\s+)?(?:too\s+)?bright\b",
    r"\bblinding\b",
    r"\bhurts?\s+my\s+eyes\b",
]

AMBIGUOUS_COMFORT_PATTERNS = [
    r"\bmake\s+it\s+comfortable\b",
    r"\bchange\s+(?:the\s+)?settings\b",
    r"\badjust\s+(?:the\s+)?settings\b",
    r"\bfix\s+the\s+room\b",
]

PRONOUN_PATTERNS = [
    r"\b(?:turn|switch|power)\s+(?:it|that|this)\s+(on|off)\b",
    r"\b(?:turn|switch|power)\s+(on|off)\s+(?:it|that|this)\b",
]

UNKNOWN_DEVICES = [
    "tv", "television", "microwave", "radio", "front door", "door", "garage",
    "garage door", "oven", "refrigerator", "fridge", "heater", "ac", "air conditioner",
    "thermostat", "music", "stereo", "computer", "blinds", "curtains", "kettle",
    "toaster", "coffee maker", "vacuum",
]

UNSUPPORTED_ACTIONS = {
    "dim": "DIM",
    "dimming": "DIM",
    "brighten": "BRIGHTEN",
    "speed up": "SET_SPEED",
    "slow down": "SET_SPEED",
    "rotate": "ROTATE",
    "oscillate": "OSCILLATE",
    "lock": "LOCK",
    "unlock": "UNLOCK",
}


@dataclass
class ContextProposal:
    """
    Structured proposal produced by ContextInterpreter.
    Describes the inferred intent, target device, and requested action.
    """
    intent: str
    device: str | None = None
    action: str | None = None
    requires_clarification: bool = False
    clarification_prompt: str | None = None
    confidence: float = 0.85
    reason: str = ""
    context_used: dict[str, Any] = field(default_factory=dict)
    no_action_needed: bool = False
    is_unknown_device: bool = False
    is_unsupported_action: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return standardized dict representation."""
        return {
            "intent": self.intent,
            "device": self.device,
            "action": self.action,
            "requires_clarification": self.requires_clarification,
            "clarification_prompt": self.clarification_prompt,
            "confidence": self.confidence,
            "reason": self.reason,
            "no_action_needed": self.no_action_needed,
        }


class ContextInterpreter:
    """
    Interprets recognized speech using conversation context and device states.
    Produces structured proposals for backend validation.
    """

    def interpret(
        self,
        text: str,
        context: ContextService,
        session_id: str,
        device_states: dict[str, str],
        known_devices: list[Device] | None = None,
    ) -> ContextProposal | None:
        """
        Evaluate utterance in context.
        Returns a ContextProposal or None if utterance should pass to standard parsing.
        """
        cleaned = text.lower().strip()
        if not cleaned:
            return None

        known_ids = {d.id for d in known_devices} if known_devices else {"fan", "bedroom_light", "living_room_light"}

        # ── 1. Check for Unknown Device ───────────────────────────────────────
        for unk in UNKNOWN_DEVICES:
            if re.search(rf"\b{re.escape(unk)}\b", cleaned):
                action = "ON" if any(w in cleaned for w in ["on", "start", "open"]) else "OFF"
                return ContextProposal(
                    intent="CONTROL_DEVICE",
                    device=unk,
                    action=action,
                    confidence=0.9,
                    is_unknown_device=True,
                    reason=f"Device '{unk}' does not exist or is not supported in VoxEdge.",
                )

        # ── 2. Check for Unsupported Action on a Device ───────────────────────
        for unsupp_word, unsupp_action in UNSUPPORTED_ACTIONS.items():
            if re.search(rf"\b{re.escape(unsupp_word)}\b", cleaned):
                # Identify target device if any
                target_dev = None
                for dev_id in ["fan", "bedroom_light", "living_room_light"]:
                    if dev_id.replace("_", " ") in cleaned or dev_id in cleaned:
                        target_dev = dev_id
                        break
                if not target_dev:
                    if "light" in cleaned or "lamp" in cleaned:
                        target_dev = "bedroom_light"
                    elif "fan" in cleaned:
                        target_dev = "fan"

                return ContextProposal(
                    intent="CONTROL_DEVICE",
                    device=target_dev or "device",
                    action=unsupp_action,
                    confidence=0.9,
                    is_unsupported_action=True,
                    reason=f"Action '{unsupp_action}' is not supported.",
                )

        # ── 3. Indirect Statement: "It's too cool" / "It's too cold" ─────────
        if any(re.search(pat, cleaned) for pat in COOL_PATTERNS):
            fan_state = device_states.get("fan", "OFF")
            if fan_state == "ON":
                return ContextProposal(
                    intent="CONTROL_DEVICE",
                    device="fan",
                    action="OFF",
                    requires_clarification=False,
                    confidence=0.9,
                    reason="User expressed feeling cool/cold and fan is currently ON. Proposing fan OFF.",
                    context_used={"cue": "cold", "fan_state": "ON"},
                )
            else:
                return ContextProposal(
                    intent="CONTROL_DEVICE",
                    device="fan",
                    action="OFF",
                    no_action_needed=True,
                    requires_clarification=False,
                    confidence=0.9,
                    reason="User expressed feeling cool/cold, but the fan is already OFF. No unnecessary state change.",
                    context_used={"cue": "cold", "fan_state": "OFF"},
                )

        # ── 4. Indirect Statement: "I'm feeling hot" / "It's too hot" ─────────
        if any(re.search(pat, cleaned) for pat in HOT_PATTERNS):
            fan_state = device_states.get("fan", "OFF")
            if fan_state == "OFF":
                return ContextProposal(
                    intent="CONTROL_DEVICE",
                    device="fan",
                    action="ON",
                    requires_clarification=False,
                    confidence=0.9,
                    reason="User expressed feeling hot and fan is currently OFF. Proposing fan ON.",
                    context_used={"cue": "hot", "fan_state": "OFF"},
                )
            else:
                return ContextProposal(
                    intent="CONTROL_DEVICE",
                    device="fan",
                    action="ON",
                    no_action_needed=True,
                    requires_clarification=False,
                    confidence=0.9,
                    reason="User expressed feeling hot, but the fan is already ON. No unnecessary state change.",
                    context_used={"cue": "hot", "fan_state": "ON"},
                )

        # ── 5. Indirect Statement: "It's too dark" ────────────────────────────
        if any(re.search(pat, cleaned) for pat in DARK_PATTERNS):
            b_light_state = device_states.get("bedroom_light", "OFF")
            l_light_state = device_states.get("living_room_light", "OFF")

            # Check if a specific light was recently used in context
            last_dev = context.get_last_device(session_id)
            if last_dev in ("bedroom_light", "living_room_light"):
                if device_states.get(last_dev, "OFF") == "OFF":
                    return ContextProposal(
                        intent="CONTROL_DEVICE",
                        device=last_dev,
                        action="ON",
                        requires_clarification=False,
                        confidence=0.88,
                        reason=f"User indicated darkness. Recently referenced {last_dev} is OFF; proposing ON.",
                        context_used={"cue": "dark", "resolved_light": last_dev},
                    )

            # Both are OFF and no specific light in context -> ask which light
            if b_light_state == "OFF" and l_light_state == "OFF":
                prompt = "It sounds like it's too dark. Which light would you like me to turn on: the Bedroom Light or the Living Room Light?"
                return ContextProposal(
                    intent="CONTROL_DEVICE",
                    device="lights",
                    action="ON",
                    requires_clarification=True,
                    clarification_prompt=prompt,
                    confidence=0.85,
                    reason="Darkness expressed. Both Bedroom Light and Living Room Light are OFF; clarification needed.",
                    context_used={"cue": "dark", "bedroom_light": "OFF", "living_room_light": "OFF"},
                )

            # Only one light is OFF -> propose that light
            if b_light_state == "OFF" and l_light_state == "ON":
                return ContextProposal(
                    intent="CONTROL_DEVICE",
                    device="bedroom_light",
                    action="ON",
                    requires_clarification=False,
                    confidence=0.88,
                    reason="Darkness expressed and Bedroom Light is OFF while Living Room Light is ON. Proposing Bedroom Light ON.",
                    context_used={"cue": "dark", "bedroom_light": "OFF"},
                )
            if l_light_state == "OFF" and b_light_state == "ON":
                return ContextProposal(
                    intent="CONTROL_DEVICE",
                    device="living_room_light",
                    action="ON",
                    requires_clarification=False,
                    confidence=0.88,
                    reason="Darkness expressed and Living Room Light is OFF while Bedroom Light is ON. Proposing Living Room Light ON.",
                    context_used={"cue": "dark", "living_room_light": "OFF"},
                )

            # All lights are already ON
            return ContextProposal(
                intent="CONTROL_DEVICE",
                device="lights",
                action="ON",
                no_action_needed=True,
                requires_clarification=False,
                confidence=0.85,
                reason="Darkness expressed, but all available lights are already ON. No unnecessary state change.",
                context_used={"cue": "dark", "all_lights_on": True},
            )

        # ── 6. Indirect Statement: "It's too bright" ──────────────────────────
        if any(re.search(pat, cleaned) for pat in BRIGHT_PATTERNS):
            b_light_state = device_states.get("bedroom_light", "OFF")
            l_light_state = device_states.get("living_room_light", "OFF")

            if b_light_state == "OFF" and l_light_state == "OFF":
                return ContextProposal(
                    intent="CONTROL_DEVICE",
                    device="lights",
                    action="OFF",
                    no_action_needed=True,
                    requires_clarification=False,
                    confidence=0.85,
                    reason="Excess brightness expressed, but all lights are already OFF and dimming is unsupported.",
                    context_used={"cue": "bright", "all_lights_off": True},
                )

            prompt = "The lights do not support dimming. Would you like me to turn off the Bedroom Light or the Living Room Light?"
            return ContextProposal(
                intent="CONTROL_DEVICE",
                device="lights",
                action="OFF",
                requires_clarification=True,
                clarification_prompt=prompt,
                confidence=0.85,
                reason="Excess brightness expressed. Dimming is unsupported; clarifying which light to turn off.",
                context_used={"cue": "bright"},
            )

        # ── 7. Ambiguous General Comfort Request ──────────────────────────────
        if any(re.search(pat, cleaned) for pat in AMBIGUOUS_COMFORT_PATTERNS):
            prompt = "Would you like me to adjust the fan or the lights?"
            return ContextProposal(
                intent="CONTROL_DEVICE",
                device=None,
                action=None,
                requires_clarification=True,
                clarification_prompt=prompt,
                confidence=0.75,
                reason="General comfort or settings statement without specified target device or action.",
            )

        # ── 8. Pronoun Reference: "Turn it off" / "Turn it on" ────────────────
        for pat in PRONOUN_PATTERNS:
            m = re.search(pat, cleaned)
            if m:
                action = m.group(1).upper()
                last_dev = context.get_last_device(session_id)
                recent_devices = context.get_recent_devices(session_id, limit=2)

                # Sufficient context with a single unambiguous recent device
                if last_dev and len(recent_devices) <= 1:
                    dev_current_state = device_states.get(last_dev)
                    return ContextProposal(
                        intent="CONTROL_DEVICE",
                        device=last_dev,
                        action=action,
                        requires_clarification=False,
                        confidence=0.9,
                        reason=f"Resolved pronoun reference to recently referenced device '{last_dev}'.",
                        context_used={"resolved_device": last_dev, "last_state": dev_current_state},
                    )

                # No context or ambiguous multiple recent devices
                act_str = action.lower()
                prompt = f"Which device would you like me to turn {act_str}: the fan or the lights?"
                return ContextProposal(
                    intent="CONTROL_DEVICE",
                    device=None,
                    action=action,
                    requires_clarification=True,
                    clarification_prompt=prompt,
                    confidence=0.5,
                    reason="Pronoun reference with no unambiguous device in conversation context.",
                )

        return None
