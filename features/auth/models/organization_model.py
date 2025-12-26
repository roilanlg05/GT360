from pydantic import BaseModel

class CreateOrganization(BaseModel):
    name: str
    address: str
    website: str | None = None

class UpdateOrganization(BaseModel):
    name: str | None = None
    address: str | None = None
    website: str | None = None


class OrganizationResponse(BaseModel):
    id: str
    manager_id: str
    name: str
    address: str
    website: str | None = None
    created_at: str
    updated_at: str
    is_active: bool

