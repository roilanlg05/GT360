"""
Manager Profile Models - Pydantic models for manager profile endpoints.
"""

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class LocationInfo(BaseModel):
    """Basic location information."""
    id: str
    name: str
    address: Optional[str] = None
    timezone: str = "America/New_York"


class ManagerProfileResponse(BaseModel):
    """
    Complete manager profile response.
    Combines data from: users, managers, organizations, locations.
    """
    # User data
    id: str = Field(..., description="UUID del usuario/manager")
    profile_pic: Optional[str] = Field(None, description="URL de la foto de perfil")
    manager_name: str = Field(..., description="first_name + last_name concatenados")
    email: str = Field(..., description="Email principal del manager")
    phone: Optional[str] = Field(None, description="Telefono de contacto")
    created_at: str = Field(..., description="Fecha de registro ISO 8601")

    # Organization data
    organization_id: str = Field(..., description="UUID de la organizacion")
    organization_name: str = Field(..., description="Nombre de la organizacion")
    organization_address: Optional[str] = Field(None, description="Direccion fisica de la org")
    organization_website: Optional[str] = Field(None, description="Website de la org")
    membership_status: str = Field(default="freemium", description="Plan: freemium, pro, enterprise")

    # Locations data
    locations: List[LocationInfo] = Field(default_factory=list, description="Locations de la org")


class ManagerProfileUpdate(BaseModel):
    """
    Fields that can be updated by the manager.
    Only sent fields will be updated (PATCH semantics).
    """
    # User fields
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None)

    # Organization fields
    organization_name: Optional[str] = Field(None, min_length=1, max_length=200)
    organization_address: Optional[str] = Field(None, max_length=500)
    organization_website: Optional[str] = Field(None, max_length=255)

    @field_validator("organization_website")
    @classmethod
    def validate_website(cls, v):
        if v is not None and v != "" and not v.startswith(("http://", "https://")):
            raise ValueError("Website debe comenzar con http:// o https://")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v is not None and v != "":
            # Basic validation: remove spaces and check format
            cleaned = v.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            if not cleaned.startswith("+"):
                cleaned = "+" + cleaned
            if len(cleaned) < 8 or len(cleaned) > 16:
                raise ValueError("Telefono debe tener entre 8 y 15 digitos")
            if not cleaned[1:].isdigit():
                raise ValueError("Telefono solo debe contener digitos")
        return v


class ProfilePhotoUploadResponse(BaseModel):
    """Response after uploading profile photo."""
    profile_pic_url: str = Field(..., description="URL publica de la imagen")
    message: str = Field(default="Foto de perfil actualizada correctamente")
