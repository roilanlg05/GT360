"""
Driver Profile Service - Business logic for driver profile operations.

Aggregates data from: users, drivers, organizations, locations.
"""

import logging
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from psqlmodel import AsyncSession, Select

from shared.db.schemas import User, Driver, Organization, Location
from features.profile.models.driver_profile_models import (
    DriverProfileResponse,
    DriverLocationInfo,
)

logger = logging.getLogger(__name__)


async def get_driver_profile(
    session: AsyncSession,
    user_id: UUID
) -> Optional[DriverProfileResponse]:
    """
    Retrieves complete driver profile by user_id.

    Aggregates:
    - entities.users (name, email, phone, profile_pic)
    - entities.drivers (is_active, pay_type, pay_frequency, rate, location_id)
    - entities.organizations (name)
    - entities.locations (name, address, timezone)
    """
    user = await session.exec(
        Select(User).Where(User.id == user_id)
    ).first()

    if not user:
        logger.warning(f"[DRIVER_PROFILE] User not found: {user_id}")
        return None

    driver = await session.exec(
        Select(Driver).Where(Driver.id == user_id)
    ).first()

    if not driver:
        logger.warning(f"[DRIVER_PROFILE] Driver record not found: {user_id}")
        return None

    # Location info
    location_info = None
    if driver.location_id:
        location = await session.exec(
            Select(Location).Where(Location.id == driver.location_id)
        ).first()
        if location:
            location_info = DriverLocationInfo(
                id=str(location.id),
                name=location.name,
                address=location.address,
                timezone=location.timezone or "America/New_York"
            )

    # Organization info
    org_name = None
    org_id = None
    if driver.organization_id:
        org = await session.exec(
            Select(Organization).Where(Organization.id == driver.organization_id)
        ).first()
        if org:
            org_id = str(org.id)
            org_name = org.name

    return DriverProfileResponse(
        id=str(user.id),
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        phone=user.phone,
        profile_pic=user.profile_pic,
        created_at=user.created_at.isoformat() if user.created_at else datetime.now(timezone.utc).isoformat(),
        is_active=driver.is_active,
        pay_type=driver.pay_type,
        pay_frequency=driver.pay_frequency,
        rate=float(driver.rate) if driver.rate is not None else None,
        shift_start_time=driver.shift_start_time.strftime("%H:%M") if driver.shift_start_time else None,
        shift_end_time=driver.shift_end_time.strftime("%H:%M") if driver.shift_end_time else None,
        work_days=driver.work_days,
        location=location_info,
        organization_id=org_id,
        organization_name=org_name,
    )
