"""
Filter Preset Service

Manages global filter presets per Location + Airline and auto-application on import.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from psqlmodel import AsyncSession, Select, Update, Delete

from shared.db.schemas import FilterPreset as FilterPresetDB, FilterStep
from features.trips.models.filter_models import (
    FilterPresetResponse,
    FilterPresetTemplate,
    AutoApplyResult,
    FilterStepConfig,
    TimeWindow,
)
from features.trips.services.step_filter_service import StepFilterService

logger = logging.getLogger(__name__)


class FilterPresetService:
    """
    Manages filter presets and auto-application.

    A preset is a "stack template" that gets cloned to new days
    when trips are imported.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    async def create_or_update_preset(
        self,
        location_id: UUID,
        airline: str,
        stack_template: list[dict],
        user_id: Optional[UUID] = None,
    ) -> FilterPresetResponse:
        """
        Create or update a preset for location+airline.

        If preset exists, it's updated. If not, it's created.
        """
        # Check if preset exists
        existing = await self.get_preset(location_id, airline)

        if existing:
            # Update existing using raw UPDATE to avoid ORM JSONB dirty tracking issues
            update_stmt = (
                Update(FilterPresetDB)
                .Where(FilterPresetDB.location_id == location_id)
                .Where(FilterPresetDB.airline == airline)
                .Set(
                    stack_template=stack_template,
                    updated_at=datetime.utcnow(),
                )
            )
            await self.session.exec(update_stmt)
            await self.session.commit()

            # Fetch updated
            preset = await self.get_preset(location_id, airline)
            logger.info(
                f"[PRESET] Updated preset for location={location_id}, airline={airline}: "
                f"{[t['filter_type'] for t in stack_template]}"
            )
            return preset

        else:
            # Create new
            preset_id = uuid4()
            preset = FilterPresetDB(
                id=preset_id,
                location_id=location_id,
                airline=airline,
                stack_template=stack_template,
                created_by=user_id,
            )
            self.session.add(preset)
            await self.session.commit()
            await self.session.refresh(preset)

            logger.info(
                f"[PRESET] Created preset {preset_id} for location={location_id}, airline={airline}"
            )

            return FilterPresetResponse(
                id=preset.id,
                location_id=preset.location_id,
                airline=preset.airline,
                stack_template=[FilterPresetTemplate(**t) for t in preset.stack_template],
                created_at=preset.created_at,
                updated_at=preset.updated_at,
                created_by=preset.created_by,
            )

    async def get_preset(
        self,
        location_id: UUID,
        airline: str,
    ) -> Optional[FilterPresetResponse]:
        """Get preset for location+airline."""
        query = (
            Select(FilterPresetDB)
            .Where(FilterPresetDB.location_id == location_id)
            .Where(FilterPresetDB.airline == airline)
        )
        preset = await self.session.exec(query).first()

        if not preset:
            return None

        return FilterPresetResponse(
            id=preset.id,
            location_id=preset.location_id,
            airline=preset.airline,
            stack_template=[FilterPresetTemplate(**t) for t in preset.stack_template],
            created_at=preset.created_at,
            updated_at=preset.updated_at,
            created_by=preset.created_by,
        )

    async def delete_preset(
        self,
        location_id: UUID,
        airline: str,
    ) -> bool:
        """Delete preset."""
        delete_stmt = (
            Delete(FilterPresetDB)
            .Where(FilterPresetDB.location_id == location_id)
            .Where(FilterPresetDB.airline == airline)
        )
        result = await self.session.exec(delete_stmt)
        await self.session.commit()

        logger.info(
            f"[PRESET] Deleted preset for location={location_id}, airline={airline}"
        )
        return True

    # =========================================================================
    # Auto-Apply Logic
    # =========================================================================

    async def auto_apply_preset(
        self,
        location_id: UUID,
        airline: str,
    ) -> AutoApplyResult:
        """
        Auto-apply preset to a location+airline.

        Logic:
        1. Get preset for location+airline
        2. If no active stack exists → apply preset
        3. If stack already exists → skip (respect existing config)

        This is called after import commits trips to DB.
        """
        # 1. Get preset
        preset = await self.get_preset(location_id, airline)
        if not preset:
            logger.debug(
                f"[AUTO_PRESET] No preset found for location={location_id}, airline={airline}"
            )
            return AutoApplyResult(
                applied=False,
                reason="No preset found for this location+airline"
            )

        # 2. Check if stack already exists
        existing_query = (
            Select(FilterStep.id)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.is_active == True)
            .Limit(1)
        )
        existing_step = await self.session.exec(existing_query).first()

        if existing_step:
            logger.info(
                f"[AUTO_PRESET] Stack already exists for {location_id}/{airline}, skipping"
            )
            return AutoApplyResult(
                applied=False,
                reason="Stack already exists",
                days_skipped=1,
            )

        # 3. Apply preset stack
        total_trips_affected = 0
        step_filter_service = StepFilterService(self.session)

        for template in preset.stack_template:
            config = FilterStepConfig(
                filter_type=template.filter_type,
                windows=[TimeWindow(**w) for w in template.windows]
            )

            try:
                result = await step_filter_service.apply_step(
                    location_id, airline, config
                )
                total_trips_affected += result.trips_modified
                logger.debug(
                    f"[AUTO_PRESET] Applied {template.filter_type}: "
                    f"{result.trips_modified} trips modified"
                )
            except Exception as e:
                logger.error(
                    f"[AUTO_PRESET] Error applying {template.filter_type}: {e}"
                )

        logger.info(
            f"[AUTO_PRESET] Completed for {location_id}/{airline}: "
            f"{total_trips_affected} trips affected"
        )

        return AutoApplyResult(
            applied=True,
            days_processed=1,
            trips_affected=total_trips_affected,
            stack_cloned_from_preset=True,
        )

    async def auto_apply_to_new_trips(
        self,
        location_id: UUID,
        airline: str,
        trip_ids: list[UUID],
    ) -> AutoApplyResult:
        """
        Auto-apply filters to newly imported trips (efficient version).

        Logic:
        1. If active stack exists → apply existing stack to ONLY the new trips
        2. If no stack but preset exists → apply preset (creates new stack for all trips)

        Args:
            location_id: Location UUID
            airline: Airline code
            trip_ids: List of new trip IDs to apply filters to

        Returns:
            AutoApplyResult with summary of what was applied
        """
        if not trip_ids:
            return AutoApplyResult(
                applied=False,
                reason="No trips to process"
            )

        step_filter_service = StepFilterService(self.session)

        # 1. Check if active stack already exists
        existing_query = (
            Select(FilterStep.id)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.is_active == True)
            .Limit(1)
        )
        existing_step = await self.session.exec(existing_query).first()

        if existing_step:
            # Apply existing stack to only the new trips
            logger.info(
                f"[AUTO_TRIPS] Applying existing stack to {len(trip_ids)} new trips "
                f"for {location_id}/{airline}"
            )
            try:
                modified = await step_filter_service.apply_existing_stack_to_trips(
                    location_id, airline, trip_ids
                )
                logger.info(f"[AUTO_TRIPS] Applied stack to {modified} new trips")
                return AutoApplyResult(
                    applied=True,
                    days_processed=0,
                    trips_affected=modified,
                    stack_cloned_from_preset=False,
                    days_with_existing_stack=1,
                )
            except Exception as e:
                logger.error(f"[AUTO_TRIPS] Error applying stack to new trips: {e}")
                return AutoApplyResult(applied=False, reason=str(e))

        # 2. No stack exists — check for preset and apply it
        preset = await self.get_preset(location_id, airline)
        if not preset:
            logger.debug(
                f"[AUTO_TRIPS] No preset found for location={location_id}, airline={airline}"
            )
            return AutoApplyResult(
                applied=False,
                reason="No preset found for this location+airline"
            )

        logger.info(
            f"[AUTO_TRIPS] No stack found, applying preset for {location_id}/{airline}"
        )

        total_trips_affected = 0
        for template in preset.stack_template:
            config = FilterStepConfig(
                filter_type=template.filter_type,
                windows=[TimeWindow(**w) for w in template.windows]
            )
            try:
                result = await step_filter_service.apply_step(
                    location_id, airline, config
                )
                total_trips_affected += result.trips_modified
                logger.debug(
                    f"[AUTO_TRIPS] Applied {template.filter_type}: "
                    f"{result.trips_modified} trips modified"
                )
            except Exception as e:
                logger.error(f"[AUTO_TRIPS] Error applying {template.filter_type}: {e}")

        logger.info(
            f"[AUTO_TRIPS] Completed: {total_trips_affected} total trips affected"
        )

        return AutoApplyResult(
            applied=True,
            days_processed=1,
            trips_affected=total_trips_affected,
            stack_cloned_from_preset=True,
        )
