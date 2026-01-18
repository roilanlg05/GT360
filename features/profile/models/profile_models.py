from typing import Optional
from pydantic import BaseModel, field_validator


class ProfileResponse(BaseModel):
    """User profile data response."""
    id: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str
    phone: Optional[str] = None
    profile_pic: Optional[str] = None
    role: str
    organization_id: Optional[str] = None
    email_verified_at: Optional[str] = None
    created_at: str
    updated_at: str


class ProfileUpdate(BaseModel):
    """Fields that can be updated by the user."""
    profile_pic: Optional[str] = None


class DeleteAccountRequest(BaseModel):
    """Request to delete account - requires password confirmation."""
    password: str


class UserSettingsResponse(BaseModel):
    """User settings response."""
    user_id: str
    time_format: str  # "24h" or "12h"
    created_at: str
    updated_at: str


class UserSettingsUpdate(BaseModel):
    """Fields that can be updated in user settings."""
    time_format: str

    @field_validator("time_format")
    @classmethod
    def validate_time_format(cls, v):
        if v not in ["24h", "12h"]:
            raise ValueError("time_format debe ser '24h' o '12h'")
        return v