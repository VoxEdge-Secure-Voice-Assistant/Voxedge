"""
Decision engine — reliability-aware command processing.

This is the core module of VoxEdge Phase 2.  Every voice or text command
passes through the decision engine, which considers:

  1. Parsed intent and confidence
  2. Whether the device is identifiable
  3. Whether the action is supported
  4. Recent interaction context (pronoun resolution)
  5. Risk classification
  6. Pending clarification state

The engine outputs one of four outcomes:
  EXECUTE  — valid, clear, authorized request → perform the action
  CLARIFY  — ambiguous target or action → ask a follow-up question
  REJECT   — unsupported, unauthorized, or invalid → refuse with explanation
  ESCALATE — emergency or high-risk request → trigger assistance workflow
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.context_service import ContextService, PendingClarification
from app.services.context_interpreter import ContextInterpreter
from app.services.device_service import DeviceService
from app.services.emergency_service import EmergencyService
from app.services.slm_service import SLMService
from app.services.intent_service import (
    CANCEL,
    CONFIRM,
    CONTROL_DEVICE,
    EMERGENCY,
    HELP,
    STATUS_CHECK,
    UNKNOWN,
    IntentResult,
)


# ── Decision outcomes ─────────────────────────────────────────────────────────
EXECUTE = "EXECUTE"
CLARIFY = "CLARIFY"
REJECT = "REJECT"
ESCALATE = "ESCALATE"


@dataclass
class Decision:
    """Structured output of the decision engine."""

    outcome: str  # EXECUTE, CLARIFY, REJECT, ESCALATE
    intent: str
    target_device: str | None = None
    requested_action: str | None = None
    confidence: float = 0.0
    reason: str = ""
    clarification_question: str | None = None
    requires_confirmation: bool = False
    message: str = ""
    entities: dict = field(default_factory=dict)
    slm_proposal: dict | None = None


class DecisionEngine:
    """
    Processes an IntentResult and context to produce a Decision.

    This engine is deliberately implemented as a separate, testable
    component with no dependency on the API layer.
    """

    def __init__(
        self,
        db: Session,
        context: ContextService,
    ) -> None:
        self.device_service = DeviceService(db)
        self.context = context
        self.db = db
        self.slm_service = SLMService()

    def decide(
        self,
        intent_result: IntentResult,
        session_id: str,
    ) -> Decision:
        """
        Main entry point: route the intent to the appropriate handler.
        First checks if the utterance answers an active clarification question.
        """
        # ── Priority 0: Multi-turn Clarification Answering ──────────────────
        # Only evaluate if the input is not a direct command or indirect statement
        pending = self.context.get_pending(session_id)
        if pending is not None and not (intent_result.is_indirect or intent_result.entities.get("is_indirect")):
            # Emergency always supersedes pending clarification
            if intent_result.intent == EMERGENCY:
                self.context.clear_pending(session_id)
                return self._handle_emergency(intent_result)

            clarify_status, resolution_data, explanation = (
                self.context.resolve_clarification_response(
                    session_id=session_id,
                    text=intent_result.raw_text,
                    db_session=self.db,
                )
            )

            if clarify_status == "RESOLVED" and resolution_data:
                target_dev = resolution_data["device"]
                target_act = resolution_data["action"]
                dev_obj = self.device_service.get_device(target_dev)
                if dev_obj:
                    try:
                        supported = json.loads(dev_obj.supported_actions)
                    except Exception:
                        supported = ["ON", "OFF"]

                    if target_act.upper() in supported:
                        return Decision(
                            outcome=EXECUTE,
                            intent=CONTROL_DEVICE,
                            target_device=target_dev,
                            requested_action=target_act.upper(),
                            confidence=0.95,
                            reason=f"Multi-turn clarification resolved: {explanation}",
                            message=f"Understood. Turning {target_act.upper()} the {dev_obj.name}.",
                            entities={
                                "device": target_dev,
                                "action": target_act.upper(),
                                "resolved_from_clarification": True,
                                "parent_interaction_id": resolution_data.get("parent_interaction_id"),
                            },
                        )
                    else:
                        return Decision(
                            outcome=REJECT,
                            intent=CONTROL_DEVICE,
                            target_device=target_dev,
                            requested_action=target_act,
                            reason=f"Action '{target_act}' is not supported for {dev_obj.name}.",
                            message=f"The {dev_obj.name} doesn't support '{target_act}'.",
                            entities={"device": target_dev, "action": target_act},
                        )

            elif clarify_status == "CANCELED":
                return Decision(
                    outcome=REJECT,
                    intent=CANCEL,
                    confidence=0.9,
                    reason="User canceled pending clarification.",
                    message="Okay, canceled.",
                    entities=intent_result.entities,
                )

            elif clarify_status == "UNCLEAR":
                prompt = pending.question if pending else "Please clarify which device you mean."
                return Decision(
                    outcome=CLARIFY,
                    intent=CONTROL_DEVICE,
                    confidence=0.4,
                    reason=f"Clarification answer was unclear: {explanation}",
                    clarification_question=prompt,
                    message=f"I didn't quite catch which device you meant. {prompt}",
                    entities=intent_result.entities,
                )

            elif clarify_status == "UNRELATED":
                # User changed topic or asked an unrelated command.
                # Clear pending clarification and proceed to process the new command naturally below!
                self.context.clear_pending(session_id)

        intent = intent_result.intent

        if intent == EMERGENCY:
            return self._handle_emergency(intent_result)

        if intent == CANCEL:
            return self._handle_cancel(intent_result, session_id)

        if intent == CONFIRM:
            return self._handle_confirm(intent_result, session_id)

        if intent == HELP:
            return self._handle_help(intent_result)

        if intent == STATUS_CHECK:
            return self._handle_status(intent_result, session_id)

        if intent == CONTROL_DEVICE:
            return self._handle_control(intent_result, session_id)

        if intent == UNKNOWN:
            return self._handle_unknown(intent_result)

        return Decision(
            outcome=REJECT,
            intent=intent,
            reason="Unhandled intent type.",
            message="I didn't understand that. Try saying 'turn on the bedroom light' or 'help'.",
        )

    # ── Intent handlers ───────────────────────────────────────────────────

    def _handle_emergency(self, ir: IntentResult) -> Decision:
        category = ir.entities.get("category", "GENERAL_DISTRESS")
        rec_resp = ir.entities.get("recommended_response")
        msg = rec_resp or "Emergency assistance triggered. Notifying contacts."
        return Decision(
            outcome=ESCALATE,
            intent=EMERGENCY,
            confidence=ir.confidence,
            reason=ir.reason or "Emergency keyword detected.",
            message=msg,
            entities=ir.entities,
        )

    def _handle_cancel(self, ir: IntentResult, session_id: str) -> Decision:
        # Check if an active emergency exists to cancel
        emergency_service = EmergencyService(self.db)
        active_em = emergency_service.get_active()
        if active_em:
            emergency_service.update_status(
                active_em.id, "CANCELLED", notes="Cancelled via user command."
            )
            return Decision(
                outcome=REJECT,
                intent=CANCEL,
                confidence=ir.confidence,
                reason="Active emergency cancelled by user request.",
                message="Emergency alert has been cancelled.",
                entities={"emergency_id": active_em.id, "cancelled": True},
            )

        pending = self.context.get_pending(session_id)
        if pending:
            self.context.clear_pending(session_id)
            return Decision(
                outcome=REJECT,
                intent=CANCEL,
                confidence=ir.confidence,
                reason="User cancelled the pending action.",
                message="Okay, the pending action has been cancelled.",
            )
        return Decision(
            outcome=REJECT,
            intent=CANCEL,
            confidence=ir.confidence,
            reason="Nothing to cancel.",
            message="There is nothing pending to cancel.",
        )

    def _handle_confirm(self, ir: IntentResult, session_id: str) -> Decision:
        pending = self.context.get_pending(session_id)
        if not pending:
            return Decision(
                outcome=REJECT,
                intent=CONFIRM,
                confidence=ir.confidence,
                reason="No pending action to confirm.",
                message="There is nothing pending to confirm.",
            )

        # Execute the pending action
        self.context.clear_pending(session_id)

        if pending.action and len(pending.candidates) == 1:
            device_id = pending.candidates[0]
            return Decision(
                outcome=EXECUTE,
                intent=CONTROL_DEVICE,
                target_device=device_id,
                requested_action=pending.action,
                confidence=0.9,
                reason="User confirmed the pending action.",
                message=f"Confirmed. Executing: {pending.action} on {device_id}.",
                entities=pending.entities,
            )

        return Decision(
            outcome=REJECT,
            intent=CONFIRM,
            reason="Pending action could not be resolved.",
            message="I couldn't resolve the pending action. Please try again.",
        )

    def _handle_help(self, ir: IntentResult) -> Decision:
        devices = self.device_service.list_devices()
        device_names = [d.name for d in devices]
        return Decision(
            outcome=REJECT,  # REJECT because no action is executed
            intent=HELP,
            confidence=ir.confidence,
            reason="Help request — listing capabilities.",
            message=(
                "I can control these devices: "
                + ", ".join(device_names)
                + ". Say things like 'turn on the bedroom light', "
                "'turn off the fan', or 'what is the status of the fan'. "
                "Say 'help me' or 'emergency' for assistance."
            ),
        )

    def _handle_status(self, ir: IntentResult, session_id: str) -> Decision:
        device_id = ir.entities.get("device")

        # Try context resolution if no device specified
        if device_id is None:
            device_id = self.context.get_last_device(session_id)

        if device_id is None:
            return Decision(
                outcome=CLARIFY,
                intent=STATUS_CHECK,
                confidence=ir.confidence,
                reason="No device specified for status check.",
                clarification_question="Which device would you like to check the status of?",
                message="Which device would you like to check?",
                entities=ir.entities,
            )

        device = self.device_service.get_device(device_id)
        if device is None:
            return Decision(
                outcome=REJECT,
                intent=STATUS_CHECK,
                target_device=device_id,
                confidence=ir.confidence,
                reason=f"Device '{device_id}' not found.",
                message=f"I couldn't find a device called '{device_id}'.",
            )

        return Decision(
            outcome=EXECUTE,
            intent=STATUS_CHECK,
            target_device=device_id,
            confidence=ir.confidence,
            reason="Status check for known device.",
            message=f"The {device.name} is currently {device.state}.",
            entities=ir.entities,
        )

    def _handle_control(self, ir: IntentResult, session_id: str) -> Decision:
        """
        Handle CONTROL_DEVICE intent — including direct commands, indirect
        natural-language requests, pronoun disambiguation, and unsupported actions.
        """
        # ── 1. Indirect natural language statements ───────────────────────
        if ir.is_indirect or ir.entities.get("is_indirect"):
            return self._handle_indirect_statement(ir, session_id)

        action = ir.entities.get("action")
        device_id = ir.entities.get("device")
        device_type = ir.entities.get("device_type")
        is_ambiguous = ir.is_ambiguous or ir.entities.get("device_ambiguous", False)
        has_pronoun = ir.entities.get("pronoun_reference", False)
        action_missing = ir.entities.get("action_missing", False)
        unknown_device = ir.entities.get("unknown_device", False)

        # ── 2. Unknown device check (e.g. "turn on the TV") ───────────────
        if unknown_device or (device_id and device_id not in ("fan", "bedroom_light", "living_room_light", "light", "lights", "lamp")):
            # Check if device exists in DB
            db_dev = self.device_service.get_device(device_id) if device_id else None
            if db_dev is None:
                dev_name = device_id or "requested device"
                all_devices = self.device_service.list_devices()
                known_names = ", ".join(d.name for d in all_devices)
                return Decision(
                    outcome=REJECT,
                    intent=CONTROL_DEVICE,
                    target_device=device_id,
                    requested_action=action,
                    confidence=ir.confidence,
                    reason=f"Device '{dev_name}' does not exist or is not supported.",
                    message=f"I don't have a registered device called '{dev_name}'. I can control: {known_names}.",
                    entities=ir.entities,
                )

        # ── 3. Missing action ─────────────────────────────────────────────
        if action is None or action_missing:
            if device_id and device_id in ("fan", "bedroom_light", "living_room_light"):
                db_dev = self.device_service.get_device(device_id)
                dev_name = db_dev.name if db_dev else device_id
                prompt = f"What would you like to do with the {dev_name}? Turn it on or off?"
                return Decision(
                    outcome=CLARIFY,
                    intent=CONTROL_DEVICE,
                    target_device=device_id,
                    confidence=ir.confidence,
                    reason="Target device identified but requested action is missing.",
                    clarification_question=prompt,
                    message=prompt,
                    entities=ir.entities,
                )
            prompt = "I didn't catch that clearly. Could you say something like 'turn on the fan' or 'turn off the bedroom light'?"
            return Decision(
                outcome=CLARIFY,
                intent=CONTROL_DEVICE,
                confidence=ir.confidence,
                reason="Neither device nor action are clear.",
                clarification_question=prompt,
                message=prompt,
                entities=ir.entities,
            )

        # ── 4. Pronoun resolution without device ("turn it off", "switch that on")
        if has_pronoun and (device_id is None or device_id in ("it", "that", "this")):
            resolved_dev, reason = self.context.resolve_pronoun(session_id, action, self.db)
            if resolved_dev:
                device_id = resolved_dev
                ir.entities["device"] = resolved_dev
                ir.entities["resolved_from_context"] = True
            else:
                act_str = action.lower() if action else "adjust"
                prompt = f"Which device would you like me to turn {act_str}: the fan or the lights?"
                self.context.set_pending(
                    session_id,
                    PendingClarification(
                        interaction_id=None,
                        question=prompt,
                        intent=CONTROL_DEVICE,
                        action=action,
                        needed_slot="device",
                        candidates=["fan", "bedroom_light", "living_room_light"],
                    ),
                )
                return Decision(
                    outcome=CLARIFY,
                    intent=CONTROL_DEVICE,
                    requested_action=action,
                    confidence=ir.confidence,
                    reason=f"Ambiguous pronoun reference: {reason}",
                    clarification_question=prompt,
                    message=prompt,
                    entities=ir.entities,
                )

        # ── 5. Generic or Ambiguous lights ("turn off the lights", "switch on the light")
        if (is_ambiguous and device_id in ("light", "lights", "the lights", "the light", None)) or device_id in ("lights", "light", "the lights", "the light"):
            candidates = self.device_service.get_device_by_name_or_location(device_type="light")
            candidate_names = [c.name for c in candidates]
            candidate_ids = [c.id for c in candidates]

            # If context was established, resolve
            last_device = self.context.get_last_device(session_id)
            if last_device and last_device in candidate_ids:
                device_id = last_device
                ir.entities["device"] = device_id
                ir.entities["resolved_from_context"] = True
            else:
                act_str = action.lower() if action else "adjust"
                prompt = f"Which light would you like me to turn {act_str}: the Bedroom Light or the Living Room Light?"
                self.context.set_pending(
                    session_id,
                    PendingClarification(
                        interaction_id=None,
                        question=prompt,
                        intent=CONTROL_DEVICE,
                        action=action,
                        needed_slot="device",
                        candidates=candidate_ids,
                    ),
                )
                return Decision(
                    outcome=CLARIFY,
                    intent=CONTROL_DEVICE,
                    requested_action=action,
                    confidence=ir.confidence,
                    reason=f"Ambiguous light command: multiple light devices exist ({', '.join(candidate_names)}).",
                    clarification_question=prompt,
                    message=prompt,
                    entities=ir.entities,
                )

        # ── 6. Missing device entirely ────────────────────────────────────
        if device_id is None:
            act_str = action.lower() if action else "adjust"
            prompt = f"Which device would you like me to turn {act_str}: the fan or the lights?"
            return Decision(
                outcome=CLARIFY,
                intent=CONTROL_DEVICE,
                requested_action=action,
                confidence=ir.confidence,
                reason="No device specified in the command.",
                clarification_question=prompt,
                message=prompt,
                entities=ir.entities,
            )

        # ── 7. Validate device exists ─────────────────────────────────────
        device = self.device_service.get_device(device_id)
        if device is None:
            all_devices = self.device_service.list_devices()
            known_names = ", ".join(d.name for d in all_devices)
            return Decision(
                outcome=REJECT,
                intent=CONTROL_DEVICE,
                target_device=device_id,
                requested_action=action,
                confidence=ir.confidence,
                reason=f"Device '{device_id}' does not exist.",
                message=f"I don't know a device called '{device_id}'. I can control: {known_names}.",
                entities=ir.entities,
            )

        if not device.is_active:
            return Decision(
                outcome=REJECT,
                intent=CONTROL_DEVICE,
                target_device=device_id,
                requested_action=action,
                confidence=ir.confidence,
                reason=f"Device '{device.name}' is currently inactive.",
                message=f"The {device.name} is not available right now.",
                entities=ir.entities,
            )

        # ── 8. Validate action is supported ───────────────────────────────
        supported = json.loads(device.supported_actions)
        if action.upper() not in supported:
            return Decision(
                outcome=REJECT,
                intent=CONTROL_DEVICE,
                target_device=device_id,
                requested_action=action,
                confidence=ir.confidence,
                reason=f"Action '{action}' is not supported for {device.name}. Supported: {supported}.",
                message=f"The {device.name} doesn't support '{action}'. Supported actions: {', '.join(supported)}.",
                entities=ir.entities,
            )

        # ── 9. Low confidence confirmation check ──────────────────────────
        if ir.confidence < settings.intent_confidence_threshold:
            prompt = f"Did you mean: turn {action} the {device.name}?"
            return Decision(
                outcome=CLARIFY,
                intent=CONTROL_DEVICE,
                target_device=device_id,
                requested_action=action,
                confidence=ir.confidence,
                requires_confirmation=True,
                reason=f"Low confidence ({ir.confidence:.2f} < {settings.intent_confidence_threshold}).",
                clarification_question=prompt,
                message="I'm not fully sure I understood. Can you confirm?",
                entities=ir.entities,
            )

        # ── 10. Clear, validated command → EXECUTE ────────────────────────
        return Decision(
            outcome=EXECUTE,
            intent=CONTROL_DEVICE,
            target_device=device_id,
            requested_action=action.upper(),
            confidence=ir.confidence,
            reason=f"Valid command with identified device '{device.name}' and action '{action.upper()}'.",
            message=f"Turning {action.upper()} the {device.name}.",
            entities=ir.entities,
        )

    def _get_device_states(self) -> dict[str, str]:
        """Collect current states of all known devices from the database."""
        devices = self.device_service.list_devices()
        return {d.id: d.state for d in devices}

    def _handle_indirect_statement(self, ir: IntentResult, session_id: str) -> Decision:
        """
        Handle indirect natural-language statements using the ContextInterpreter.

        The ContextInterpreter inspects current device states, conversation
        context, and linguistic cues to produce a structured ContextProposal.
        This method translates that proposal into a Decision.
        """
        interpreter = ContextInterpreter()
        device_states = self._get_device_states()
        known_devices = self.device_service.list_devices()

        proposal = interpreter.interpret(
            text=ir.raw_text,
            context=self.context,
            session_id=session_id,
            device_states=device_states,
            known_devices=known_devices,
        )

        # If the interpreter has no opinion, fall back to generic clarification
        if proposal is None:
            prompt = "Would you like me to adjust the fan or the lights?"
            self.context.set_pending(
                session_id,
                PendingClarification(
                    interaction_id=None,
                    question=prompt,
                    intent=CONTROL_DEVICE,
                    needed_slot="device",
                    candidates=["fan", "bedroom_light", "living_room_light"],
                ),
            )
            return Decision(
                outcome=CLARIFY,
                intent=CONTROL_DEVICE,
                confidence=ir.confidence,
                reason="General comfort or settings request. Clarification required to identify target device.",
                clarification_question=prompt,
                message=prompt,
                entities=ir.entities,
            )

        # ── Proposal: no_action_needed (device already in desired state) ──
        if proposal.no_action_needed:
            return Decision(
                outcome=REJECT,
                intent=CONTROL_DEVICE,
                target_device=proposal.device,
                requested_action=proposal.action,
                confidence=proposal.confidence,
                reason=proposal.reason,
                message=proposal.reason,
                entities={**ir.entities, "context_proposal": proposal.to_dict()},
            )

        # ── Proposal: unknown device ─────────────────────────────────────
        if proposal.is_unknown_device:
            all_devices = self.device_service.list_devices()
            known_names = ", ".join(d.name for d in all_devices)
            return Decision(
                outcome=REJECT,
                intent=CONTROL_DEVICE,
                target_device=proposal.device,
                requested_action=proposal.action,
                confidence=proposal.confidence,
                reason=proposal.reason,
                message=f"I don't have a registered device called '{proposal.device}'. I can control: {known_names}.",
                entities={**ir.entities, "context_proposal": proposal.to_dict()},
            )

        # ── Proposal: unsupported action ──────────────────────────────────
        if proposal.is_unsupported_action:
            return Decision(
                outcome=REJECT,
                intent=CONTROL_DEVICE,
                target_device=proposal.device,
                requested_action=proposal.action,
                confidence=proposal.confidence,
                reason=proposal.reason,
                message=proposal.reason,
                entities={**ir.entities, "context_proposal": proposal.to_dict()},
            )

        # ── Proposal: requires clarification ─────────────────────────────
        if proposal.requires_clarification:
            prompt = proposal.clarification_prompt or "Could you clarify what you'd like me to do?"
            candidates = ["fan", "bedroom_light", "living_room_light"]
            action = proposal.action
            needed_slot = "device"
            if proposal.device and proposal.device not in ("lights", "light", "device", None):
                candidates = [proposal.device]
                needed_slot = "action"

            self.context.set_pending(
                session_id,
                PendingClarification(
                    interaction_id=None,
                    question=prompt,
                    intent=CONTROL_DEVICE,
                    action=action,
                    device_id=proposal.device if proposal.device not in ("lights", "light", None) else None,
                    needed_slot=needed_slot,
                    candidates=candidates,
                ),
            )
            return Decision(
                outcome=CLARIFY,
                intent=CONTROL_DEVICE,
                target_device=proposal.device,
                requested_action=proposal.action,
                confidence=proposal.confidence,
                reason=proposal.reason,
                clarification_question=prompt,
                message=prompt,
                entities={**ir.entities, "context_proposal": proposal.to_dict()},
            )

        # ── Proposal: clear action on a known device ─────────────────────
        # Validate the device exists in the DB before executing
        device = self.device_service.get_device(proposal.device)
        if device is None:
            all_devices = self.device_service.list_devices()
            known_names = ", ".join(d.name for d in all_devices)
            return Decision(
                outcome=REJECT,
                intent=CONTROL_DEVICE,
                target_device=proposal.device,
                requested_action=proposal.action,
                confidence=proposal.confidence,
                reason=f"Interpreted device '{proposal.device}' does not exist.",
                message=f"I couldn't find a device called '{proposal.device}'. I can control: {known_names}.",
                entities={**ir.entities, "context_proposal": proposal.to_dict()},
            )

        # Validate action is supported
        try:
            supported = json.loads(device.supported_actions)
        except Exception:
            supported = ["ON", "OFF"]

        if proposal.action and proposal.action.upper() not in supported:
            return Decision(
                outcome=REJECT,
                intent=CONTROL_DEVICE,
                target_device=proposal.device,
                requested_action=proposal.action,
                confidence=proposal.confidence,
                reason=f"Action '{proposal.action}' not supported for {device.name}. Supported: {supported}.",
                message=f"The {device.name} doesn't support '{proposal.action}'. Supported: {', '.join(supported)}.",
                entities={**ir.entities, "context_proposal": proposal.to_dict()},
            )

        # Valid context-interpreted command → EXECUTE
        action_str = proposal.action.upper() if proposal.action else "OFF"
        return Decision(
            outcome=EXECUTE,
            intent=CONTROL_DEVICE,
            target_device=proposal.device,
            requested_action=action_str,
            confidence=proposal.confidence,
            reason=proposal.reason,
            message=f"Understood. Turning {action_str} the {device.name}.",
            entities={**ir.entities, "context_proposal": proposal.to_dict()},
        )

    def _handle_unknown(self, ir: IntentResult) -> Decision:
        return Decision(
            outcome=REJECT,
            intent=UNKNOWN,
            confidence=0.0,
            reason="Intent could not be determined.",
            message=(
                "I didn't understand that command. "
                "Try 'turn on the bedroom light', 'fan off', or say 'help' for options."
            ),
            entities=ir.entities,
        )
