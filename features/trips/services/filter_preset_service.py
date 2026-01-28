"""
Filter Preset Service

Manages global filter presets per Location + Airline and auto-application on import.
"""

import logging
from datetime import date, datetime
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
            # Update existing
            update_stmt = (
                Update(FilterPresetDB)
                .Where(FilterPresetDB.location_id == location_id)
                .Where(FilterPresetDB.airline == airline)
                .Set(FilterPresetDB.stack_template, stack_template)
                .Set(FilterPresetDB.updated_at, datetime.utcnow())
            )
            await self.session.exec(update_stmt)
            await self.session.commit()

            # Fetch updated
            preset = await self.get_preset(location_id, airline)
            logger.info(
                f"[PRESET] Updated preset for location={location_id}, airline={airline}"
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
        pick_up_dates: list[date],
    ) -> AutoApplyResult:
        """
        Auto-apply preset to new days.

        Logic:
        1. Get preset for location+airline
        2. For each pick_up_date:
           - If day has NO stack → clone preset and apply
           - If day HAS stack → skip (respect existing config)
        3. Return summary

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

        logger.info(
            f"[AUTO_PRESET] Preset found for location={location_id}, airline={airline}. "
            f"Processing {len(pick_up_dates)} dates"
        )

        # 2. Filter days that DON'T have stack yet
        days_to_process = []
        days_skipped = []

        for pick_up_date in pick_up_dates:
            # Check if day already has steps
            existing_query = (
                Select(FilterStep.id)
                .Where(FilterStep.location_id == location_id)
                .Where(FilterStep.airline == airline)
                .Where(FilterStep.pick_up_date == pick_up_date)
                .Where(FilterStep.is_active == True)
                .Limit(1)
            )
            existing_step = await self.session.exec(existing_query).first()

            if existing_step:
                days_skipped.append(pick_up_date)
                logger.debug(
                    f"[AUTO_PRESET] Skipping {pick_up_date} (already has stack)"
                )
            else:
                days_to_process.append(pick_up_date)

        if not days_to_process:
            logger.info(
                f"[AUTO_PRESET] All days already have stack. Skipped {len(days_skipped)} days"
            )
            return AutoApplyResult(
                applied=False,
                reason="All days already have stack",
                days_skipped=len(days_skipped)
            )

        # 3. Clone preset to each day
        total_trips_affected = 0
        step_filter_service = StepFilterService(self.session)

        for pick_up_date in days_to_process:
            logger.debug(
                f"[AUTO_PRESET] Cloning preset to {pick_up_date}"
            )

            # Apply each step from template in order
            for template in preset.stack_template:
                config = FilterStepConfig(
                    filter_type=template.filter_type,
                    pick_up_date=str(pick_up_date),
                    windows=[TimeWindow(**w) for w in template.windows]
                )

                try:
                    result = await step_filter_service.apply_step(
                        location_id, airline, config
                    )
                    total_trips_affected += result.trips_modified

                    logger.debug(
                        f"[AUTO_PRESET] Applied {template.filter_type} to {pick_up_date}: "
                        f"{result.trips_modified} trips modified"
                    )
                except Exception as e:
                    logger.error(
                        f"[AUTO_PRESET] Error applying {template.filter_type} "
                        f"to {pick_up_date}: {e}"
                    )
                    # Continue with next template

        logger.info(
            f"[AUTO_PRESET] Completed. Processed {len(days_to_process)} days, "
            f"skipped {len(days_skipped)} days, affected {total_trips_affected} trips"
        )

        return AutoApplyResult(
            applied=True,
            days_processed=len(days_to_process),
            days_skipped=len(days_skipped),
            trips_affected=total_trips_affected,
            stack_cloned_from_preset=True,
        )
