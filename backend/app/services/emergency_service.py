"""
Emergency service — simulated emergency assistance workflow.

All notifications are simulated.  This service never contacts real
people unless an actual notification integration is configured.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.emergency import EmergencyEvent
from app.schemas.emergency import EmergencyContact


# ── Simulated contacts (configurable in a real deployment) ────────────────────
DEFAULT_CONTACTS: list[dict] = [
    {
        "name": "Dr. Sharma",
        "relationship": "Primary Doctor",
        "phone": "+91-XXXX-XXXX01",
        "notified": False,
        "notified_at": None,
    },
    {
        "name": "Family Member",
        "relationship": "Emergency Contact",
        "phone": "+91-XXXX-XXXX02",
        "notified": False,
        "notified_at": None,
    },
]


class EmergencyService:
    """Manages emergency event lifecycle."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def trigger(
        self,
        trigger_text: str,
        severity: str = "HIGH",
        interaction_id: int | None = None,
        category: str | None = None,
    ) -> EmergencyEvent:
        """
        Create a new emergency event and simulate contact notification.

        IMPORTANT: All notifications are simulated.  No real person is
        contacted by this method.
        """
        # Check for already-active emergencies to prevent duplicates
        active = (
            self.db.query(EmergencyEvent)
            .filter(EmergencyEvent.status == "ACTIVE")
            .first()
        )
        if active:
            return active  # return the existing active event

        now = datetime.now(timezone.utc)

        # Simulate notifying contacts
        contacts = []
        for c in DEFAULT_CONTACTS:
            contact = dict(c)
            contact["notified"] = True
            contact["notified_at"] = now.isoformat()
            contacts.append(contact)

        event = EmergencyEvent(
            interaction_id=interaction_id,
            trigger_text=trigger_text,
            status="ACTIVE",
            severity=severity.upper(),
            category=category,
            contacts_json=json.dumps(contacts),
            notes="[SIMULATED] Contacts have been notified. No real notification was sent.",
        )
        try:
            self.db.add(event)
            self.db.commit()
            self.db.refresh(event)
            return event
        except Exception as e:
            self.db.rollback()
            raise RuntimeError(f"Storage failure: could not record emergency event: {e}") from e

    def update_status(
        self,
        event_id: int,
        new_status: str,
        notes: str | None = None,
    ) -> EmergencyEvent | None:
        """Transition an emergency event to a new status."""
        valid_transitions = {
            "ACTIVE": {"ACKNOWLEDGED", "CANCELLED"},
            "ACKNOWLEDGED": {"COMPLETED", "CANCELLED"},
        }

        event = (
            self.db.query(EmergencyEvent)
            .filter(EmergencyEvent.id == event_id)
            .first()
        )
        if event is None:
            return None

        allowed = valid_transitions.get(event.status, set())
        if new_status.upper() not in allowed:
            return None  # invalid transition

        event.status = new_status.upper()
        if notes:
            existing = event.notes or ""
            event.notes = f"{existing}\n{notes}".strip()
        if new_status.upper() in ("COMPLETED", "CANCELLED"):
            event.resolved_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(event)
        return event

    def get_active(self) -> EmergencyEvent | None:
        """Return the currently active emergency event, if any."""
        return (
            self.db.query(EmergencyEvent)
            .filter(EmergencyEvent.status == "ACTIVE")
            .first()
        )

    def get_all(self, limit: int = 50) -> list[EmergencyEvent]:
        """Return recent emergency events."""
        return (
            self.db.query(EmergencyEvent)
            .order_by(EmergencyEvent.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_by_id(self, event_id: int) -> EmergencyEvent | None:
        return (
            self.db.query(EmergencyEvent)
            .filter(EmergencyEvent.id == event_id)
            .first()
        )

    @staticmethod
    def parse_contacts(event: EmergencyEvent) -> list[EmergencyContact]:
        """Deserialize contacts_json into schema objects."""
        if not event.contacts_json:
            return []
        raw = json.loads(event.contacts_json)
        return [EmergencyContact(**c) for c in raw]
