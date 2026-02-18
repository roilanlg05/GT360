"""
Manager Profile Service - Business logic for manager profile operations.

Aggregates data from multiple tables: users, managers, organizations, locations.
"""

import logging
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from psqlmodel import AsyncSession, Select

from shared.db.schemas import User, Manager, Organization, Location
from features.profile.models import (
    ManagerProfileResponse,
    ManagerProfileUpdate,
    LocationInfo,
)

logger = logging.getLogger(__name__)


class ManagerProfileService:
    """
    Service for managing manager profile data.

    Aggregates data from:
    - entities.users
    - entities.managers
    - entities.organizations
    - entities.locations
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_manager_profile(self, user_id: UUID) -> Optional[ManagerProfileResponse]:
        """
        Retrieves complete manager profile by user_id.

        Args:
            user_id: UUID of the user (same as manager.id)

        Returns:
            ManagerProfileResponse if found, None otherwise
        """
        # Query user
        user = await self.session.exec(
            Select(User).Where(User.id == user_id)
        ).first()

        if not user:
            logger.warning(f"[MANAGER_PROFILE] User not found: {user_id}")
            return None

        # Get manager record
        manager = await self.session.exec(
            Select(Manager).Where(Manager.id == user_id)
        ).first()

        if not manager:
            logger.warning(f"[MANAGER_PROFILE] Manager record not found for user: {user_id}")
            return None

        if not manager.organization_id:
            logger.warning(f"[MANAGER_PROFILE] Manager has no organization: {user_id}")
            return None

        # Get organization
        organization = await self.session.exec(
            Select(Organization).Where(Organization.id == manager.organization_id)
        ).first()

        if not organization:
            logger.warning(f"[MANAGER_PROFILE] Organization not found: {manager.organization_id}")
            return None

        # Get all locations for this organization
        locations_result = await self.session.exec(
            Select(Location).Where(Location.organization_id == organization.id)
        ).all()

        locations_info = [
            LocationInfo(
                id=str(loc.id),
                name=loc.name,
                address=loc.address,
                timezone=loc.timezone or "America/New_York"
            )
            for loc in locations_result
        ]

        # Build manager name
        manager_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        if not manager_name:
            manager_name = user.email.split('@')[0]  # Fallback to email username

        return ManagerProfileResponse(
            id=str(user.id),
            profile_pic=user.profile_pic,
            manager_name=manager_name,
            email=user.email,
            phone=user.phone,
            created_at=user.created_at.isoformat() if user.created_at else datetime.now(timezone.utc).isoformat(),
            organization_id=str(organization.id),
            organization_name=organization.name,
            organization_address=organization.address,
            organization_website=organization.website,
            organization_pay_frequency=organization.pay_frequency or "weekly",
            membership_status=organization.plan or "freemium",
            locations=locations_info
        )

    async def update_manager_profile(
        self,
        user_id: UUID,
        update_data: ManagerProfileUpdate
    ) -> Optional[ManagerProfileResponse]:
        """
        Updates manager profile fields.

        Args:
            user_id: UUID of the user/manager
            update_data: Fields to update

        Returns:
            Updated ManagerProfileResponse
        """
        # Get user
        user = await self.session.exec(
            Select(User).Where(User.id == user_id)
        ).first()

        if not user:
            return None

        # Get manager and organization
        manager = await self.session.exec(
            Select(Manager).Where(Manager.id == user_id)
        ).first()

        if not manager or not manager.organization_id:
            return None

        organization = await self.session.exec(
            Select(Organization).Where(Organization.id == manager.organization_id)
        ).first()

        if not organization:
            return None

        # Apply updates
        update_dict = update_data.model_dump(exclude_unset=True)

        # User fields
        if "first_name" in update_dict:
            user.first_name = update_dict["first_name"]
        if "last_name" in update_dict:
            user.last_name = update_dict["last_name"]
        if "phone" in update_dict:
            user.phone = update_dict["phone"]

        # Organization fields
        if "organization_name" in update_dict:
            organization.name = update_dict["organization_name"]
        if "organization_address" in update_dict:
            organization.address = update_dict["organization_address"]
        if "organization_website" in update_dict:
            organization.website = update_dict["organization_website"]
        if "organization_pay_frequency" in update_dict:
            organization.pay_frequency = update_dict["organization_pay_frequency"]

        # Update timestamps
        user.updated_at = datetime.now(timezone.utc)
        organization.updated_at = datetime.now(timezone.utc)

        # Save changes
        self.session.add(user)
        self.session.add(organization)
        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(organization)

        logger.info(f"[MANAGER_PROFILE] Updated profile for user: {user_id}")

        # Return updated profile
        return await self.get_manager_profile(user_id)

    async def update_profile_pic(self, user_id: UUID, profile_pic_url: str) -> bool:
        """
        Updates the profile picture URL for a user.

        Args:
            user_id: UUID of the user
            profile_pic_url: URL of the uploaded image

        Returns:
            True if successful, False otherwise
        """
        user = await self.session.exec(
            Select(User).Where(User.id == user_id)
        ).first()

        if not user:
            return False

        user.profile_pic = profile_pic_url
        user.updated_at = datetime.now(timezone.utc)

        self.session.add(user)
        await self.session.commit()

        logger.info(f"[MANAGER_PROFILE] Updated profile pic for user: {user_id}")
        return True
