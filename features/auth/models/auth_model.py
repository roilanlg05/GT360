from pydantic import EmailStr, BaseModel, field_validator
from ..utils import validators
from enum import Enum

class PermissionEnum(str, Enum):
    UPLOAD_TRIPS = "upload_trips"
    VIEW_TRIPS = "view_trips"
    CREATE_TRIPS = "create_trips"
    EDIT_TRIPS = "edit_trips"
    DELETE_TRIPS = "delete_trips"
    CREATE_DRIVERS = "create_drivers"
    DELETE_DRIVERS = "delete_drivers"
    EDIT_DRIVERS = "edit_drivers"
    EDIT_ORGANIZATION = "edit_organization"

class EmailPasswordRequestForm(BaseModel):
    email: EmailStr
    password: str


class NewPassword(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password_strength(cls, v):
        return validators.validate_password(v)
    

class PasswordUpdate(NewPassword):
    current_password: str

class Permission(BaseModel):
    name: PermissionEnum
    description: str

class RefreshTokenRequest(BaseModel):
    """
    Request body for refresh token.

    Supports multiple field names to ease integration across clients.
    """

    refresh_token: str | None = None
    refresh: str | None = None
    token: str | None = None
