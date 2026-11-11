"""Pydantic schemas for user registration, login, and profile management."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class UserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, description="Unique username")
    password: str = Field(..., min_length=6, description="Password (at least 6 characters)")
    full_name: str | None = Field(None, max_length=128, description="User's full name")
    email: str | None = Field(None, max_length=128, description="Optional email address")


class UserLoginRequest(BaseModel):
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str | None = None
    email: str | None = None
    voice_enrolled: bool = False
    voice_profile_path: str | None = None
    created_at: datetime


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserPreferencesResponse(BaseModel):
    user_id: int
    username: str
    preferences: dict[str, Any]

