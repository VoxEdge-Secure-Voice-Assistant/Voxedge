"""User authentication, registration, token, and data isolation service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """
    Hash a password using PBKDF2-HMAC-SHA256 with 100,000 iterations.
    Returns (hex_hash, salt_hex).
    """
    if salt is None:
        salt = secrets.token_hex(16)
    salt_bytes = salt.encode("utf-8")
    key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        100_000,
    )
    return key.hex(), salt


def verify_password(password: str, hashed_password: str, salt: str) -> bool:
    """Verify password against stored hash and salt."""
    computed_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(computed_hash, hashed_password)


def create_access_token(user_id: int, username: str, expires_in_seconds: int = 86400 * 7) -> str:
    """
    Create a cryptographically signed user bearer token.
    Default validity: 7 days.
    """
    expires_at = int(time.time()) + expires_in_seconds
    nonce = secrets.token_hex(8)
    payload = f"{user_id}:{username}:{expires_at}:{nonce}"
    signature = hmac.new(
        settings.auth_secret_key.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    raw = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def verify_access_token(token: str) -> tuple[bool, int | None, str | None]:
    """
    Validate a user bearer token.
    Returns (is_valid, user_id, username).
    """
    if not token:
        return False, None, None
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        parts = raw.split(":")
        if len(parts) != 5:
            return False, None, None
        user_id_str, username, expires_at_str, nonce, signature = parts
        expires_at = int(expires_at_str)
        if time.time() > expires_at:
            return False, None, None

        expected_payload = f"{user_id_str}:{username}:{expires_at_str}:{nonce}"
        expected_sig = hmac.new(
            settings.auth_secret_key.encode("utf-8"),
            expected_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return False, None, None

        return True, int(user_id_str), username
    except Exception:
        return False, None, None


class UserService:
    """Service handling multi-user registration, authentication, and isolation."""

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_user_by_username(db: Session, username: str) -> User | None:
        normalized = username.strip().lower()
        return db.query(User).filter(User.username == normalized).first()

    @staticmethod
    def register_user(
        db: Session,
        username: str,
        password: str,
        full_name: str | None = None,
        email: str | None = None,
    ) -> User:
        """Register a new user account with hashed credentials."""
        normalized = username.strip().lower()
        if not normalized or len(normalized) < 3:
            raise ValueError("Username must be at least 3 characters long.")
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters long.")

        existing = UserService.get_user_by_username(db, normalized)
        if existing:
            raise ValueError(f"Username '{normalized}' is already registered.")

        hashed, salt = hash_password(password)
        user = User(
            username=normalized,
            hashed_password=hashed,
            salt=salt,
            full_name=full_name.strip() if full_name else None,
            email=email.strip() if email else None,
            voice_profile_path=None,
            preferences_json=json.dumps({
                "theme": "dark",
                "speech_rate": 1.0,
                "preferred_room": "bedroom",
                "emergency_alert_contacts": ["Dr. Sharma (Primary Caregiver)", "Local Clinic Assist"],
            }),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def authenticate_user(db: Session, username: str, password: str) -> User | None:
        """Verify user credentials and return User if valid."""
        user = UserService.get_user_by_username(db, username)
        if not user:
            return None
        if not verify_password(password, user.hashed_password, user.salt):
            return None
        return user

    @staticmethod
    def is_voice_enrolled(user: User) -> bool:
        """Check if user has an enrolled voice profile."""
        if not user.voice_profile_path:
            return False
        p = Path(user.voice_profile_path)
        return p.is_file() and p.stat().st_size > 0

    @staticmethod
    def get_user_voice_profile_path(user: User) -> Path:
        """Return user-specific voice profile file path."""
        if user.voice_profile_path:
            p = Path(user.voice_profile_path)
            if p.exists():
                return p.resolve()

        # Dedicated user voice profile directory
        profile_dir = Path("data/voice_profiles")
        profile_dir.mkdir(parents=True, exist_ok=True)
        return (profile_dir / f"user_{user.id}_voice.npy").resolve()

    @staticmethod
    def get_preferences(user: User) -> dict[str, Any]:
        """Return user preferences as dictionary."""
        if not user.preferences_json:
            return {}
        try:
            return json.loads(user.preferences_json)
        except Exception:
            return {}

    @staticmethod
    def update_preferences(db: Session, user: User, prefs: dict[str, Any]) -> dict[str, Any]:
        """Update and persist user preferences."""
        current = UserService.get_preferences(user)
        current.update(prefs)
        user.preferences_json = json.dumps(current)
        db.commit()
        db.refresh(user)
        return current

