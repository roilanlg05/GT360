from pydantic import BaseModel, EmailStr
from enum import Enum


class SupportCategory(str, Enum):
    BUG = "bug"
    FEATURE = "feature"
    QUESTION = "question"
    OTHER = "other"


class SupportContactRequest(BaseModel):
    name: str
    email: EmailStr
    category: SupportCategory
    subject: str
    message: str


class SupportContactResponse(BaseModel):
    success: bool
    message: str
