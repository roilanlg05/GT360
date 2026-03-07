from fastapi import APIRouter, HTTPException, Depends, Query, Request
from psqlmodel import Select, Delete, AsyncSession
from shared.db.db_config import get_db
from shared.db.schemas import Driver, User, Organization, Location, Trip as TripDB, TripStatus
from features.auth.utils import verify_role, encode_token, revoke_all_user_refresh
from features.billing.utils.subscription_guard import ActiveSubscription
from features.auth.utils.smtp import send_email, get_confirmation_email_template
from features.drivers.models.driver_models import DriverActiveUpdate, DriverDetailsUpdate, DriverResponse, DriverStatusResponse, DriverLocationSharingUpdate, DriverLocationUpdate
from features.drivers.utils.location_ws_manager import driver_location_manager
from shared.settings import settings
from typing import Optional
from uuid import UUID
from datetime import timedelta
import secrets


router = APIRouter(tags=["Drivers"])

@router.get("/v1/drivers/me/status", response_model=DriverStatusResponse)
async def get_my_driver_status(
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    user_data = request.state.user_data
    user_id = user_data.get("id")
    org_id = user_data.get("organization_id")

    try:
        driver_uuid = UUID(str(user_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de usuario inválido")

    driver = await session.exec(
        Select(Driver).Where(Driver.id == driver_uuid)
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver no encontrado")

    if org_id and driver.organization_id and str(driver.organization_id) != str(org_id):
        raise HTTPException(status_code=403, detail="Driver no pertenece a esta organización")

    return DriverStatusResponse(id=str(driver.id), is_active=driver.is_active)


@router.post("/v1/drivers/me/location", status_code=204)
async def update_my_location(
    request: Request,
    data: DriverLocationUpdate,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    """
    HTTP endpoint for driver location updates (used by background tasks
    when WebSocket is unavailable, e.g. iOS background mode).

    Writes to the same Redis hash and publishes to the same channel as the
    WebSocket handler, so managers on Mapbox see updates identically.
    """
    user_data = request.state.user_data
    driver_id = str(user_data.get("id"))
    org_id = str(user_data.get("organization_id"))

    driver_uuid = UUID(driver_id)
    row = await session.exec(
        Select(Driver.location_id, User.first_name, User.last_name)
        .From(Driver)
        .Join(User).On(Driver.id == User.id)
        .Where(Driver.id == driver_uuid)
    ).first()

    if not row:
        raise HTTPException(status_code=404, detail="Driver not found")

    location_data = {
        "driver_id": driver_id,
        "first_name": row.first_name,
        "last_name": row.last_name,
        "location_id": str(row.location_id) if row.location_id else None,
        "lat": data.lat,
        "lng": data.lng,
    }

    await driver_location_manager.store_driver_location(org_id, driver_id, location_data)


@router.patch("/v1/drivers/me/active", response_model=DriverStatusResponse)
async def set_my_driver_active_status(
    request: Request,
    data: DriverActiveUpdate,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["driver"]))
):
    user_data = request.state.user_data
    user_id = user_data.get("id")
    org_id = user_data.get("organization_id")

    try:
        driver_uuid = UUID(str(user_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="ID de usuario inválido")

    driver = await session.exec(
        Select(Driver).Where(Driver.id == driver_uuid)
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver no encontrado")

    if org_id and driver.organization_id and str(driver.organization_id) != str(org_id):
        raise HTTPException(status_code=403, detail="Driver no pertenece a esta organización")

    # Si el driver quiere ponerse offline, validar que no tenga trips activos
    if not data.is_active:
        active_trips = await session.exec(
            Select(TripDB).Where(
                (TripDB.assigned_driver == driver_uuid) &
                (TripDB.status == TripStatus.EN_ROUTE)
            )
        ).all()
        
        if active_trips:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot go offline with {len(active_trips)} active trip(s). Complete all trips before going offline."
            )

    driver.is_active = data.is_active
    session.add(driver)
    await session.commit()
    await session.refresh(driver)

    # When going offline, remove location from Redis so driver
    # disappears from the manager's Mapbox map immediately.
    if not data.is_active and org_id:
        await driver_location_manager.remove_driver_location(str(org_id), str(user_id))

    return DriverStatusResponse(id=str(driver.id), is_active=driver.is_active)


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
            Driver.pay_frequency,
            Driver.rate,
            Driver.location_id,
            Driver.organization_id,
            Driver.shift_start_time,
            Driver.shift_end_time,
            Driver.work_days,
            User.first_name,
            User.last_name,
            User.email,
            User.phone,
            User.profile_pic,
            User.created_at,
            User.email_verified_at
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
            "pay_frequency": row.pay_frequency,
            "rate": float(row.rate) if row.rate is not None else None,
            "location_id": str(row.location_id) if row.location_id else None,
            "organization_id": str(row.organization_id) if row.organization_id else None,
            "shift_start_time": row.shift_start_time.strftime("%H:%M") if row.shift_start_time else None,
            "shift_end_time": row.shift_end_time.strftime("%H:%M") if row.shift_end_time else None,
            "work_days": row.work_days,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "email_verified_at": row.email_verified_at.isoformat() if row.email_verified_at else None
        })

    return {
        "data": drivers,
        "total": len(drivers)
    }


@router.patch("/v1/drivers/{driver_id}", response_model=DriverResponse)
async def update_driver_details(
    driver_id: UUID,
    data: DriverDetailsUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager", "driver"]))
):
    user_data = request.state.user_data
    user_id = user_data.get("id")
    user_role = user_data.get("role")
    user_org_id = user_data.get("organization_id")

    # Fetch driver
    driver = await session.exec(
        Select(Driver).Where(Driver.id == driver_id)
    ).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    update_dict = data.model_dump(exclude_unset=True)

    if not update_dict:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Validate shift_start_time and shift_end_time must both be set or both null
    has_start = "shift_start_time" in update_dict
    has_end = "shift_end_time" in update_dict
    if has_start or has_end:
        start_val = update_dict.get("shift_start_time")
        end_val = update_dict.get("shift_end_time")
        # If only one is provided, check the other from the existing driver record
        if has_start and not has_end:
            end_val = driver.shift_end_time
        elif has_end and not has_start:
            start_val = driver.shift_start_time
        # Both must be set or both null
        if (start_val is None) != (end_val is None):
            raise HTTPException(
                status_code=400,
                detail="shift_start_time and shift_end_time must both be set or both null"
            )

    # Validate work_days values
    if "work_days" in update_dict and update_dict["work_days"] is not None:
        valid_days = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
        for day in update_dict["work_days"]:
            if day.lower() not in valid_days:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid work day '{day}'. Must be one of: mon, tue, wed, thu, fri, sat, sun"
                )
        # Normalize to lowercase
        update_dict["work_days"] = [d.lower() for d in update_dict["work_days"]]

    # Permission checks based on role
    if user_role == "driver":
        # Drivers can only edit themselves
        if str(user_id) != str(driver_id):
            raise HTTPException(status_code=403, detail="You can only edit your own profile")
        # Drivers can only change profile_pic_url
        disallowed = set(update_dict.keys()) - {"profile_pic_url"}
        if disallowed:
            raise HTTPException(
                status_code=403,
                detail="Drivers can only update profile_pic_url"
            )
    elif user_role == "manager":
        # Managers can only edit drivers in their organization
        if str(driver.organization_id) != str(user_org_id):
            raise HTTPException(
                status_code=403,
                detail="Driver does not belong to your organization"
            )

    # Validate location_id belongs to the driver's organization
    if "location_id" in update_dict and update_dict["location_id"] is not None:
        try:
            loc_uuid = UUID(update_dict["location_id"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid location_id format")

        location = await session.exec(
            Select(Location).Where(
                (Location.id == loc_uuid) &
                (Location.organization_id == driver.organization_id)
            )
        ).first()
        if not location:
            raise HTTPException(
                status_code=400,
                detail="Location not found or does not belong to this organization"
            )

    # Apply updates
    for field, value in update_dict.items():
        if field == "location_id" and value is not None:
            setattr(driver, field, UUID(value))
        elif field in ("pay_type", "pay_frequency") and value is not None:
            setattr(driver, field, value.value if hasattr(value, "value") else value)
        else:
            setattr(driver, field, value)

    session.add(driver)
    await session.commit()
    await session.refresh(driver)

    # Fetch user info for response
    user = await session.exec(
        Select(User).Where(User.id == driver.id)
    ).first()

    return DriverResponse(
        id=str(driver.id),
        first_name=user.first_name if user else None,
        last_name=user.last_name if user else None,
        email=user.email if user else "",
        phone=user.phone if user else None,
        profile_pic=user.profile_pic if user else None,
        is_active=driver.is_active,
        pay_type=driver.pay_type,
        pay_frequency=driver.pay_frequency,
        rate=float(driver.rate) if driver.rate is not None else None,
        location_id=str(driver.location_id) if driver.location_id else None,
        organization_id=str(driver.organization_id) if driver.organization_id else None,
        shift_start_time=driver.shift_start_time.strftime("%H:%M") if driver.shift_start_time else None,
        shift_end_time=driver.shift_end_time.strftime("%H:%M") if driver.shift_end_time else None,
        work_days=driver.work_days,
        created_at=user.created_at if user else None
    )


# ─── Driver Location Sharing Settings ──────────────────────────────────────

@router.get("/v1/organizations/{organization_id}/settings/driver-location-sharing")
async def get_driver_location_sharing(
    organization_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """Get the driver location sharing setting for an organization."""
    user_data = request.state.user_data
    user_org_id = user_data.get("organization_id")

    if str(user_org_id) != str(organization_id):
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    org = await session.exec(
        Select(Organization).Where(Organization.id == organization_id)
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    return {
        "driver_location_sharing": org.driver_location_sharing,
        "organization_id": str(org.id),
    }


@router.patch("/v1/organizations/{organization_id}/settings/driver-location-sharing")
async def update_driver_location_sharing(
    organization_id: UUID,
    data: DriverLocationSharingUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"])),
    _sub=Depends(ActiveSubscription),
):
    """Toggle driver-to-driver location sharing for an organization."""
    user_data = request.state.user_data
    user_org_id = user_data.get("organization_id")

    if str(user_org_id) != str(organization_id):
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    org = await session.exec(
        Select(Organization).Where(Organization.id == organization_id)
    ).first()

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    org.driver_location_sharing = data.driver_location_sharing
    session.add(org)
    await session.commit()
    await session.refresh(org)

    # Publish toggle event so all WebSocket connections react immediately
    await driver_location_manager.publish_sharing_toggle(
        str(organization_id),
        data.driver_location_sharing,
    )

    return {
        "driver_location_sharing": org.driver_location_sharing,
        "organization_id": str(org.id),
    }


# ─── Resend Verification Email ─────────────────────────────────────────────

@router.post("/v1/organizations/{organization_id}/drivers/{driver_id}/resend-verification")
async def resend_driver_verification_email(
    organization_id: UUID,
    driver_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"]))
):
    """Resend the verification email to a driver who hasn't verified yet."""
    user_data = request.state.user_data
    user_org_id = user_data.get("organization_id")

    if str(user_org_id) != str(organization_id):
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    # Fetch driver and verify it belongs to the org
    driver = await session.exec(
        Select(Driver).Where(Driver.id == driver_id)
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if str(driver.organization_id) != str(organization_id):
        raise HTTPException(status_code=403, detail="Driver does not belong to your organization")

    # Fetch user record
    user = await session.exec(
        Select(User).Where(User.id == driver_id)
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.email_verified_at:
        raise HTTPException(status_code=400, detail="Email already verified")

    # Generate new nonce and verification token
    user.password_reset_nonce = secrets.token_urlsafe(16)
    session.add(user)
    await session.commit()

    metadata = {
        "email": user.email,
        "purpose": "email_verification",
        "nonce": user.password_reset_nonce
    }

    token = encode_token(str(user.id), metadata, expires_in=timedelta(hours=24))
    confirmation_url = f"{settings.BASE_URL}/auth/verify-email/?token={token['access_token']}"
    html_content = get_confirmation_email_template(confirmation_url)

    await send_email(
        user.email,
        "Confirm Your Api360 Account",
        html_content,
        confirmation_url
    )

    return {"message": "Verification email resent successfully"}


# ─── Delete Driver from Organization ───────────────────────────────────────

@router.delete("/v1/organizations/{organization_id}/drivers/{driver_id}")
async def delete_driver_from_organization(
    organization_id: UUID,
    driver_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _role=Depends(verify_role(["manager"])),
    _sub=Depends(ActiveSubscription),
):
    """Remove a driver from the organization. This permanently deletes the driver's account."""
    user_data = request.state.user_data
    user_org_id = user_data.get("organization_id")

    if str(user_org_id) != str(organization_id):
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    # Fetch driver and verify it belongs to the org
    driver = await session.exec(
        Select(Driver).Where(Driver.id == driver_id)
    ).first()

    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    if str(driver.organization_id) != str(organization_id):
        raise HTTPException(status_code=403, detail="Driver does not belong to your organization")

    # Check driver has no active trips
    active_trips = await session.exec(
        Select(TripDB).Where(
            (TripDB.assigned_driver == driver_id) &
            (TripDB.status == TripStatus.EN_ROUTE)
        )
    ).all()

    if active_trips:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete driver with {len(active_trips)} active trip(s). Complete all trips first."
        )

    # Revoke all refresh tokens
    await revoke_all_user_refresh(session, str(driver_id))

    # Delete driver record first (FK constraint), then user
    await session.exec(
        Delete(Driver).Where(Driver.id == driver_id)
    )
    await session.exec(
        Delete(User).Where(User.id == driver_id)
    )

    await session.commit()

    return {"message": "Driver removed from organization successfully"}
