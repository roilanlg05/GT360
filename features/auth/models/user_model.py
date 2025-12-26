from pydantic import BaseModel, EmailStr, field_validator
from ..models.organization_model import CreateOrganization
from ..utils.validators import validators
import enum
from datetime import datetime


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    CREW_MEMBER = "crew"
    DRIVER = "driver"


class UserBase(BaseModel):
    email: EmailStr
    password: str 
    
    @field_validator("password")
    @classmethod
    def check_password_strength(cls, v):
        return validators.validate_password(v)
    

class UserData(BaseModel):
    email: EmailStr
    phone: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v is not None:
            return validators.validate_us_phone(v)
        return v


class CreateManager(UserBase):
    phone: str | None = None
    organization: CreateOrganization

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v is not None:
            return validators.validate_us_phone(v)
        return v


class CreateCrewMember(UserBase):
    airline: str | None = None 
    

class UpdateUser(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    password: str | None = None
    phone: str | None = None
     

class ManagerResponse(BaseModel):
    id: str
    full_name: str | None = None
    email: EmailStr
    phone: str
    profile_pic: str | None = None
    role: UserRole = UserRole.MANAGER
    organization_id: str
    email_verified_at: datetime | None = None
    created_at: datetime


class CrewResponse(BaseModel):
    id: str
    email: EmailStr
    profile_pic: str | None = None
    role: UserRole = UserRole.CREW_MEMBER
    airline: str 
    email_verified_at: datetime | None = None
    created_at: datetime



