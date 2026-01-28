from fastapi import APIRouter, HTTPException, Depends, Query, Request
from psqlmodel import Select, AsyncSession
from shared.db.db_config import get_db
from shared.db.schemas import Driver, User, Organization
from features.auth.utils import verify_role
from typing import Optional
from uuid import UUID


router = APIRouter(tags=["Drivers"])


@router.get("/v1/organizations/{organization_id}/drivers")
async def get_drivers(
    organization_id: UUID,
    request: Request,
    location_id: Optional[UUID] = Query(default=None, description="Filter by location ID"),
    pay_type: Optional[str] = Query(default=None, description="Filter by pay type: day, hour, trip"),
    driver_id: Optional[UUID] = Query(default=None, description="Get specific driver by ID"),
    name: Optional[str] = Query(default=None, description="Search by driver name (first or last)"),
    is_active: Optional[bool] = Query(default=None, description="Filter by active/inactive status"),
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
) -> dict:
    """
    Get list of drivers for an organization with optional filters.

    - **organization_id** (required): The organization ID (path parameter)
    - **location_id** (optional): Filter drivers by location
    - **pay_type** (optional): Filter by payment type (day, hour, trip)
    - **driver_id** (optional): Get a specific driver's complete info
    - **name** (optional): Search by name (uses ILIKE for case-insensitive partial match)
    - **is_active** (optional): Filter by active (true) or inactive (false) status
    """
    # Verify user belongs to the organization
    user_data = request.state.user_data
    user_org_id = user_data.get("organization_id")

    if str(user_org_id) != str(organization_id):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to access this organization's drivers"
        )

    # Verify organization exists
    org = await session.exec(
        Select(Organization).Where(Organization.id == organization_id)
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Validate pay_type if provided
    valid_pay_types = ["day", "hour", "trip"]
    if pay_type and pay_type.lower() not in valid_pay_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pay_type. Must be one of: {', '.join(valid_pay_types)}"
        )

    # Build query with JOIN to users table
    query = (
        Select(
            Driver.id,
            Driver.is_active,
            Driver.pay_type,
            Driver.location_id,
            Driver.organization_id,
            User.first_name,
            User.last_name,
            User.email,
            User.phone,
            User.profile_pic,
            User.created_at
        )
        .From(Driver)
        .Join(User).On(Driver.id == User.id)
        .Where(Driver.organization_id == organization_id)
    )

    # Apply filters
    if location_id:
        query = query.And(Driver.location_id == location_id)

    if pay_type:
        query = query.And(Driver.pay_type == pay_type.lower())

    if driver_id:
        query = query.And(Driver.id == driver_id)

    if name:
        # Case-insensitive search on first_name or last_name
        name_pattern = f"%{name}%"
        query = query.And(
            (User.first_name.ilike(name_pattern)) | (User.last_name.ilike(name_pattern))
        )

    if is_active is not None:
        query = query.And(Driver.is_active == is_active)

    # Order by created_at descending (newest first)
    query = query.OrderBy(User.created_at.Desc())

    # Execute query
    results = await session.exec(query).all()

    # Build response
    drivers = []
    for row in results:
        drivers.append({
            "id": str(row.id),
            "first_name": row.first_name,
            "last_name": row.last_name,
            "email": row.email,
            "phone": row.phone,
            "profile_pic": row.profile_pic,
            "is_active": row.is_active,
            "pay_type": row.pay_type,
            "location_id": str(row.location_id) if row.location_id else None,
            "organization_id": str(row.organization_id) if row.organization_id else None,
            "created_at": row.created_at.isoformat() if row.created_at else None
        })

    return {
        "data": drivers,
        "total": len(drivers)
    }
