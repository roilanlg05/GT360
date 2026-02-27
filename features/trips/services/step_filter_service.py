"""
Step-Based Filter Service (V2)

Implements the new step/stack-based filtering system with:
- Order-free filter application (any sequence of reduce/combine/expand)
- Per-day configuration (pick_up_date)
- Time windows per filter (1..N per day, no overlapping, no midnight crossing)
- Minute precision (no rounding to multiples of 5)
- Smart Expand with 3 attempts (both, only A, only B)
- Anti-drift with original_pick_up_time immutable
- Scalable revert by steps

Rules:
- Rule A: A trip modified by Combine/Expand in this step cannot be modified again
- Rule B: No-Collision Rule - Expand must not create gaps that fall into Combine range
"""

from __future__ import annotations

import asyncio
import logging
from datetime import time, datetime, date
from typing import Optional
from uuid import UUID, uuid4
from collections import defaultdict

from psqlmodel import AsyncSession, Select, Update

from shared.db.schemas import Trip, TripType, TripStatus, FilterStep
from shared.redis.redis_safe import safe_redis_call
from features.trips.models.filter_models import (
    FilterStepConfig,
    TimeWindow,
    TripChange,
    FilterExclusion,
    TripExclusionInfo,
    StepResult,
    StepRevertResult,
    StackState,
    FilterStepInfo,
    EligibilityResult,
    BulkFilterConfig,
    BulkStepResult,
    DayResult,
    BulkEligibilityResult,
    BulkRevertConfig,
    BulkRevertResult,
    DayRevertResult,
)

logger = logging.getLogger(__name__)


class StepFilterService:
    """
    Step-based filter service (v2).

    Key differences from v1:
    - Order-free: Apply reduce, combine, expand in any order
    - Per-day: Each step targets a specific pick_up_date
    - Time windows: 1..N windows per step
    - Minute precision: No rounding to multiples of 5
    - Stack-based revert: Pop steps or revert specific ones
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.modified_by_combine_expand: set[UUID] = set()  # Rule A tracking
        self.changes: list[TripChange] = []
        self.exclusions: list[FilterExclusion] = []
        self.log: list[dict] = []

    # =========================================================================
    # Public API
    # =========================================================================

    async def preview_step(
        self,
        location_id: UUID,
        airline: str,
        config: FilterStepConfig,
    ) -> StepResult:
        """
        Preview a step without applying changes.

        Returns proposed changes for user review.
        trips_modified is the count of trips NEWLY affected by this filter.
        """
        self._reset_state()

        # Validate windows
        self._validate_windows(config.windows)

        # Parse date
        pick_up_date = date.fromisoformat(config.pick_up_date)

        # Get eligible trips for the day
        trips = await self._get_eligible_trips(location_id, airline, pick_up_date)

        logger.info(
            f"[STEP_FILTER] Preview: {len(trips)} eligible trips for "
            f"location={location_id}, airline={airline}, date={pick_up_date}"
        )

        if not trips:
            return StepResult(
                step_id=None,
                filter_type=config.filter_type,
                pick_up_date=config.pick_up_date,
                trips_modified=0,
                changes=[],
                exclusions=[],
                summary={"modified": 0, "excluded": 0},
            )

        # Track trips that already had this filter BEFORE applying
        filter_flag = f"{config.filter_type}_applied"
        trips_already_with_filter = {
            t.id for t in trips if getattr(t, filter_flag, False)
        }

        # Apply filter based on type (simulation only)
        if config.filter_type == "reduce":
            self._apply_reduce(trips, config)
        elif config.filter_type == "combine":
            self._apply_combine(trips, config)
        elif config.filter_type == "expand":
            await self._apply_expand(trips, config)

        # Calculate independent trip count (trips newly affected by THIS filter)
        trips_newly_modified = {
            change.trip_id for change in self.changes
            if change.trip_id not in trips_already_with_filter
        }
        independent_count = len(trips_newly_modified)

        return StepResult(
            step_id=None,
            filter_type=config.filter_type,
            pick_up_date=config.pick_up_date,
            trips_modified=independent_count,  # Independent count (only new trips)
            changes=self.changes,
            exclusions=self.exclusions,
            summary={
                "modified": independent_count,
                "total_changes": len(self.changes),  # Total for debugging
                "excluded": len(self.exclusions),
            },
        )

    async def apply_step(
        self,
        location_id: UUID,
        airline: str,
        config: FilterStepConfig,
    ) -> StepResult:
        """
        Apply a step to the stack and persist changes.

        Returns trips_modified as the count of trips NEWLY affected by this filter
        (trips that didn't have this specific filter applied before).
        """
        self._reset_state()

        # Validate windows
        self._validate_windows(config.windows)

        # Parse date
        pick_up_date = date.fromisoformat(config.pick_up_date)

        # Get eligible trips for the day
        trips = await self._get_eligible_trips(location_id, airline, pick_up_date)

        logger.info(
            f"[STEP_FILTER] Apply: {len(trips)} eligible trips for "
            f"location={location_id}, airline={airline}, date={pick_up_date}"
        )

        if not trips:
            return StepResult(
                step_id=None,
                filter_type=config.filter_type,
                pick_up_date=config.pick_up_date,
                trips_modified=0,
                changes=[],
                exclusions=[],
                summary={"modified": 0, "excluded": 0},
            )

        # Track trips that already had this filter BEFORE applying
        # This is used to calculate independent trip counts
        filter_flag = f"{config.filter_type}_applied"
        trips_already_with_filter = {
            t.id for t in trips if getattr(t, filter_flag, False)
        }

        # Apply filter based on type
        if config.filter_type == "reduce":
            self._apply_reduce(trips, config)
        elif config.filter_type == "combine":
            self._apply_combine(trips, config)
        elif config.filter_type == "expand":
            await self._apply_expand(trips, config)

        # Get next step order
        next_order = await self._get_next_step_order(location_id, airline, pick_up_date)

        # Create FilterStep record
        step_id = uuid4()
        filter_step = FilterStep(
            id=step_id,
            location_id=location_id,
            airline=airline,
            pick_up_date=pick_up_date,
            step_order=next_order,
            filter_type=config.filter_type,
            config={"filter_type": config.filter_type},  # Minimal metadata
            windows=[w.model_dump() for w in config.windows],
            trips_affected=len(self.changes),
            is_active=True,
        )
        self.session.add(filter_step)
        await self.session.flush()

        # Build trip lookup and persist changes
        trip_lookup = {t.id: t for t in trips}
        now = datetime.utcnow()

        for change in self.changes:
            trip = trip_lookup.get(change.trip_id)
            if not trip:
                continue

            # Store original if not already stored
            if trip.original_pick_up_time is None:
                trip.original_pick_up_time = trip.pick_up_time

            # Apply new time
            trip.pick_up_time = change.new_time
            trip.current_step_id = step_id
            trip.updated_at = now

            # Update filter flags based on type
            if config.filter_type == "reduce":
                trip.reduce_applied = True
            elif config.filter_type == "combine":
                trip.combine_applied = True
            elif config.filter_type == "expand":
                trip.expand_applied = True

            trip.filtered_at = now

            # Build filter_order string for frontend display
            trip.filter_order = await self._build_filter_order_string(
                trip, location_id, airline, pick_up_date
            )

            self.session.add(trip)

        # Calculate independent trip count (trips newly affected by THIS filter)
        trips_newly_modified = {
            change.trip_id for change in self.changes
            if change.trip_id not in trips_already_with_filter
        }
        independent_count = len(trips_newly_modified)

        # Commit
        try:
            await self.session.commit()
            logger.info(
                f"[STEP_FILTER] Applied step {step_id}: "
                f"{independent_count} trips newly modified by {config.filter_type} "
                f"(total changes: {len(self.changes)})"
            )

            # Send notification with independent count and total changes
            if self.changes:
                await self._send_step_notification(
                    location_id, airline, step_id, config.filter_type,
                    trips_affected=independent_count,
                    total_changes=len(self.changes)
                )

            # AUTO-SAVE PRESET: Update preset with current day's stack
            await self._auto_save_preset(location_id, airline, pick_up_date)

        except Exception as e:
            logger.error(f"[STEP_FILTER] Apply failed: {e}")
            await self.session.rollback()
            raise

        return StepResult(
            step_id=step_id,
            filter_type=config.filter_type,
            pick_up_date=config.pick_up_date,
            trips_modified=independent_count,  # Independent count (only new trips)
            changes=self.changes,
            exclusions=self.exclusions,
            summary={
                "modified": independent_count,
                "total_changes": len(self.changes),  # Total for debugging
                "excluded": len(self.exclusions),
            },
        )

    async def apply_existing_stack_to_trips(
        self,
        location_id: UUID,
        airline: str,
        pick_up_date: date,
        trip_ids: list[UUID],
    ) -> int:
        """
        Apply existing filter stack to specific trips (for newly imported trips).

        This is called when new trips are imported for a date that already has
        a filter stack. Instead of creating new FilterStep records, it applies
        the existing stack's filters to only the specified trips.

        Returns the number of trips affected.
        """
        if not trip_ids:
            return 0

        # Get all active FilterSteps for this date, ordered by step_order
        steps_query = (
            Select(FilterStep)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.pick_up_date == pick_up_date)
            .Where(FilterStep.is_active == True)
            .OrderBy(FilterStep.step_order.Asc())
        )
        active_steps = await self.session.exec(steps_query).all()

        if not active_steps:
            logger.debug(
                f"[STACK_APPLY] No active stack for {location_id}/{airline}/{pick_up_date}"
            )
            return 0

        logger.info(
            f"[STACK_APPLY] Applying {len(active_steps)} steps to {len(trip_ids)} new trips "
            f"for {location_id}/{airline}/{pick_up_date}"
        )

        # Get only the specified trips that are eligible
        trips = await self._get_eligible_trips(
            location_id, airline, pick_up_date, trip_ids=trip_ids
        )

        if not trips:
            logger.debug(f"[STACK_APPLY] No eligible trips found from {len(trip_ids)} IDs")
            return 0

        total_modified = 0
        now = datetime.utcnow()

        # Apply each step in order
        for step in active_steps:
            self._reset_state()

            # Reconstruct config from step
            windows = [TimeWindow(**w) for w in step.windows] if step.windows else []
            config = FilterStepConfig(
                filter_type=step.filter_type,
                pick_up_date=str(pick_up_date),
                windows=windows,
            )

            # Apply filter based on type
            if step.filter_type == "reduce":
                self._apply_reduce(trips, config)
            elif step.filter_type == "combine":
                self._apply_combine(trips, config)
            elif step.filter_type == "expand":
                await self._apply_expand(trips, config)

            # Persist changes for this step
            trip_lookup = {t.id: t for t in trips}
            for change in self.changes:
                trip = trip_lookup.get(change.trip_id)
                if not trip:
                    continue

                # Store original if not already stored
                if trip.original_pick_up_time is None:
                    trip.original_pick_up_time = trip.pick_up_time

                # Apply new time
                trip.pick_up_time = change.new_time
                trip.current_step_id = step.id
                trip.updated_at = now

                # Update filter flags
                if step.filter_type == "reduce":
                    trip.reduce_applied = True
                elif step.filter_type == "combine":
                    trip.combine_applied = True
                elif step.filter_type == "expand":
                    trip.expand_applied = True

                trip.filtered_at = now

                # Update filter_order for frontend display
                trip.filter_order = await self._build_filter_order_string(
                    trip, location_id, airline, pick_up_date
                )

                self.session.add(trip)

            total_modified += len(self.changes)

            logger.debug(
                f"[STACK_APPLY] Step {step.step_order} ({step.filter_type}): "
                f"{len(self.changes)} changes"
            )

        # Commit all changes
        try:
            await self.session.commit()
            logger.info(
                f"[STACK_APPLY] Completed: {total_modified} total modifications "
                f"for {len(trips)} new trips"
            )
        except Exception as e:
            logger.error(f"[STACK_APPLY] Failed: {e}")
            await self.session.rollback()
            raise

        return total_modified

    async def revert_last_step(
        self,
        location_id: UUID,
        airline: str,
        pick_up_date_str: str,
    ) -> StepRevertResult:
        """
        Revert the last active step (pop from stack).
        """
        pick_up_date = date.fromisoformat(pick_up_date_str)

        # Get last active step
        query = (
            Select(FilterStep)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.pick_up_date == pick_up_date)
            .Where(FilterStep.is_active == True)
            .OrderBy(FilterStep.step_order.Desc())
            .Limit(1)
        )
        last_step = await self.session.exec(query).first()

        if not last_step:
            raise ValueError(
                f"No active steps found for location={location_id}, "
                f"airline={airline}, date={pick_up_date_str}"
            )

        return await self._revert_step_internal(last_step, location_id, airline, pick_up_date)

    async def revert_step(
        self,
        step_id: UUID,
    ) -> StepRevertResult:
        """
        Revert a specific step by ID.
        """
        # Get step
        query = Select(FilterStep).Where(FilterStep.id == step_id)
        step = await self.session.exec(query).first()

        if not step:
            raise ValueError(f"Step {step_id} not found")

        if not step.is_active:
            raise ValueError(f"Step {step_id} is already reverted")

        return await self._revert_step_internal(
            step, step.location_id, step.airline, step.pick_up_date
        )

    async def get_stack(
        self,
        location_id: UUID,
        airline: str,
        pick_up_date_str: str,
    ) -> StackState:
        """
        Get current stack state for a day.
        """
        pick_up_date = date.fromisoformat(pick_up_date_str)

        query = (
            Select(FilterStep)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.pick_up_date == pick_up_date)
            .Where(FilterStep.is_active == True)
            .OrderBy(FilterStep.step_order.Asc())
        )
        steps = await self.session.exec(query).all()

        step_infos = []
        total_affected = 0

        for step in steps:
            step_infos.append(FilterStepInfo(
                step_id=step.id,
                step_order=step.step_order,
                filter_type=step.filter_type,
                windows_count=len(step.windows) if step.windows else 0,
                windows=step.windows or [],  # Include full windows for UI rehydration
                trips_affected=step.trips_affected,
                created_at=step.created_at,
                is_active=step.is_active,
                config=step.config,
            ))
            total_affected += step.trips_affected

        return StackState(
            location_id=location_id,
            airline=airline,
            pick_up_date=pick_up_date_str,
            steps=step_infos,
            total_trips_affected=total_affected,
        )

    async def get_eligibility(
        self,
        location_id: UUID,
        airline: str,
        pick_up_date_str: str,
        filter_type: str = None,
    ) -> EligibilityResult:
        """
        Check filter eligibility for a day.

        If filter_type is provided, returns breakdown of trips that:
        - Already have this specific filter applied
        - Would be NEW for this filter
        """
        pick_up_date = date.fromisoformat(pick_up_date_str)

        # Get all outbound scheduled trips for the day
        query = (
            Select(Trip)
            .Where(Trip.location_id == location_id)
            .Where(Trip.airline == airline)
            .Where(Trip.pick_up_date == pick_up_date)
            .Where(Trip.trip_type == TripType.OUTBOUND)
            .Where(Trip.status == TripStatus.SCHEDULED)
        )
        trips = await self.session.exec(query).all()

        # Count by hotel
        by_hotel: dict[str, int] = defaultdict(int)
        already_filtered = 0
        trips_with_filter = 0

        for trip in trips:
            hotel = trip.pick_up_location or "Unknown"
            by_hotel[hotel] += 1

            # General: ¿tiene algún filtro?
            if trip.original_pick_up_time is not None:
                already_filtered += 1

            # Específico: ¿tiene ESTE filtro?
            if filter_type:
                filter_flag = f"{filter_type}_applied"
                if getattr(trip, filter_flag, False):
                    trips_with_filter += 1

        # Calcular trips nuevos para este filtro
        trips_new = None
        if filter_type:
            trips_new = len(trips) - trips_with_filter

        return EligibilityResult(
            location_id=location_id,
            airline=airline,
            pick_up_date=pick_up_date_str,
            filter_type=filter_type,
            total_trips=len(trips),
            eligible_trips=len(trips),  # All outbound scheduled are eligible
            already_filtered=already_filtered,
            trips_with_filter=trips_with_filter if filter_type else None,
            trips_new=trips_new,
            by_hotel=dict(by_hotel),
        )

    # =========================================================================
    # Filter Application Methods
    # =========================================================================

    def _apply_reduce(self, trips: list[Trip], config: FilterStepConfig):
        """
        Apply Reduce filter: subtract fixed minutes from pickup_time.

        Uses minute precision (no rounding).
        Iterates over windows, each with its own config.
        Ventana sin config (enabled=False o minutes_to_reduce=None) se omite.

        NOTE: Track processed trips to prevent duplicates when windows overlap.
        """
        # Track trips already processed to prevent duplicates across overlapping windows
        processed_trips = set()

        for window in config.windows:
            # Skip window if disabled or no config
            if not window.enabled or window.minutes_to_reduce is None:
                continue

            # Filter by hotel names specific to this window
            filtered_trips = self._filter_by_hotel(trips, window.hotel_names)

            for trip in filtered_trips:
                # Skip if already processed in a previous window
                if trip.id in processed_trips:
                    continue

                # Skip trips that already have reduce_applied (re-preview case)
                if trip.reduce_applied:
                    self._record_exclusion(
                        f"reduce({trip.id})",
                        [trip.id],
                        "Already has Reduce applied",
                        0, 0,
                        trips=[trip],
                    )
                    processed_trips.add(trip.id)
                    continue

                # ✅ FIX CASCADA: Usar tiempo efectivo (actual) para cascada verdadera
                # Esto permite que REDUCE funcione en cascada con EXPAND/COMBINE
                # Consistente con _get_effective_time usado por Combine y Expand
                base_time = self._get_effective_time(trip)

                # Check if time is in this specific window
                if not self._is_time_in_window(base_time, window):
                    continue

                try:
                    new_time = self._subtract_minutes(base_time, window.minutes_to_reduce)
                except ValueError as e:
                    # Time would go outside day - skip this trip
                    logger.debug(
                        f"[STEP_FILTER] Skipping Reduce for trip {trip.id}: {e}"
                    )
                    continue

                self._record_change(trip, base_time, new_time, "reduce")
                processed_trips.add(trip.id)

    def _apply_combine(self, trips: list[Trip], config: FilterStepConfig):
        """
        Apply Combine filter: move pairs to their midpoint.

        Rule A: A trip modified by Combine cannot be modified again in this step.
        NUEVO: Requiere pickup_location y drop_off_location idénticos.
        Procesa cada ventana con su propia config.
        """
        for window in config.windows:
            # Skip window if disabled or no config
            if not window.enabled or window.min_gap is None or window.max_gap is None:
                continue

            # Filter by hotel names specific to this window
            filtered_trips = self._filter_by_hotel(trips, window.hotel_names)

            # Filter to trips within this window's time range
            window_trips = [
                t for t in filtered_trips
                if self._is_time_in_window(
                    self._get_effective_time(t),
                    window
                )
            ]

            # Sort by effective pickup time
            sorted_trips = sorted(
                window_trips,
                key=lambda t: self._time_to_minutes(self._get_effective_time(t))
            )

            i = 0
            while i < len(sorted_trips) - 1:
                trip_a = sorted_trips[i]
                trip_b = sorted_trips[i + 1]

                # Rule A check
                if (trip_a.id in self.modified_by_combine_expand or
                    trip_b.id in self.modified_by_combine_expand):
                    i += 1
                    continue

                # SKIP trips that already have combine_applied (re-preview case)
                if trip_a.combine_applied or trip_b.combine_applied:
                    # Record exclusion for trips already combined
                    if trip_a.combine_applied:
                        self._record_exclusion(
                            f"combine({trip_a.id})",
                            [trip_a.id],
                            "Already has Combine applied",
                            0, 0,
                            trips=[trip_a],
                        )
                    if trip_b.combine_applied and trip_b.id != trip_a.id:
                        self._record_exclusion(
                            f"combine({trip_b.id})",
                            [trip_b.id],
                            "Already has Combine applied",
                            0, 0,
                            trips=[trip_b],
                        )
                    i += 1
                    continue

                # PRIORITY RULE: Expand has absolute priority
                if trip_a.expand_applied or trip_b.expand_applied:
                    logger.info(
                        f"[PRIORITY_RULE] Combine skipping pair "
                        f"({trip_a.id}, {trip_b.id}): "
                        f"Expand already claimed these trips "
                        f"(expand_applied: {trip_a.expand_applied}, {trip_b.expand_applied})"
                    )
                    self._record_exclusion(
                        f"combine({trip_a.id}, {trip_b.id})",
                        [trip_a.id, trip_b.id],
                        "Skipped: Expand has priority (applied in earlier step)",
                        0,
                        0,
                        trips=[trip_a, trip_b],
                    )
                    i += 1
                    continue

                # PUNTO 9: Combine requiere pickup y dropoff idénticos
                if (trip_a.pick_up_location != trip_b.pick_up_location or
                    trip_a.drop_off_location != trip_b.drop_off_location):
                    logger.debug(
                        f"[STEP_FILTER] Skipping Combine: location mismatch "
                        f"({trip_a.pick_up_location}→{trip_a.drop_off_location}) vs "
                        f"({trip_b.pick_up_location}→{trip_b.drop_off_location})"
                    )
                    i += 1
                    continue

                time_a = self._get_effective_time(trip_a)
                time_b = self._get_effective_time(trip_b)

                gap = self._minutes_between(time_a, time_b)

                if window.min_gap <= gap <= window.max_gap:
                    midpoint = self._calculate_midpoint(time_a, time_b)

                    self._record_change(trip_a, time_a, midpoint, "combine")
                    self._record_change(trip_b, time_b, midpoint, "combine")

                    self.modified_by_combine_expand.add(trip_a.id)
                    self.modified_by_combine_expand.add(trip_b.id)

                    i += 2  # Skip both
                else:
                    i += 1

    async def _apply_expand(self, trips: list[Trip], config: FilterStepConfig):
        """
        Apply Expand with CHAIN PATTERN approach.

        Identifica cadenas de trips con gaps pequeños y aplica patrones fijos:
        - Cadena de 2: [-max, +max]
        - Cadena de 3: [-max, 0, +max]
        - Cadena de 4+: EXCLUIR (dejaría gaps intermedios problemáticos)

        PRIORITY RULE: If Combine already modified a trip, Expand cannot touch it.
        """
        for window in config.windows:
            # Skip window if disabled or no config
            if (not window.enabled or window.min_gap is None or
                window.max_gap is None or window.max_shift is None):
                continue

            # Filter by hotel names specific to this window
            filtered_trips = self._filter_by_hotel(trips, window.hotel_names)

            # Filter to trips within this window's time range
            window_trips = [
                t for t in filtered_trips
                if self._is_time_in_window(
                    self._get_effective_time(t),
                    window
                )
            ]

            # Sort by effective pickup time
            sorted_trips = sorted(
                window_trips,
                key=lambda t: self._time_to_minutes(self._get_effective_time(t))
            )

            # Filter out trips that already have expand_applied (re-preview case)
            excluded_by_expand = [t for t in sorted_trips if t.expand_applied]
            for trip in excluded_by_expand:
                logger.info(
                    f"[ALREADY_APPLIED] Expand skipping trip {trip.id}: "
                    f"Already has expand_applied=True"
                )
                self._record_exclusion(
                    f"expand({trip.id})",
                    [trip.id],
                    "Already has Expand applied",
                    0,
                    0,
                    trips=[trip],
                )

            # PRIORITY RULE: Filter out trips blocked by Combine
            available_trips = [
                t for t in sorted_trips
                if not t.combine_applied and not t.expand_applied
            ]

            # Record exclusions for trips blocked by Combine (symmetry with Combine's exclusions)
            excluded_by_combine = [t for t in sorted_trips if t.combine_applied and not t.expand_applied]
            for trip in excluded_by_combine:
                logger.info(
                    f"[PRIORITY_RULE] Expand skipping trip {trip.id}: "
                    f"Combine already claimed this trip (combine_applied=True)"
                )
                self._record_exclusion(
                    f"expand({trip.id})",
                    [trip.id],
                    "Skipped: Combine has priority (applied in earlier step)",
                    0,
                    0,
                    trips=[trip],
                )

            if len(available_trips) < 2:
                continue

            # Group by location (pickup_location, drop_off_location)
            from collections import defaultdict
            location_groups = defaultdict(list)
            for trip in available_trips:
                key = (trip.pick_up_location, trip.drop_off_location)
                location_groups[key].append(trip)

            # Process each location group independently
            for (pickup_loc, dropoff_loc), group_trips in location_groups.items():
                if len(group_trips) < 2:
                    continue

                # Identify chains within this location group
                chains = self._identify_expand_chains(
                    group_trips,
                    min_gap=window.min_gap,
                    max_gap=window.max_gap,
                    max_shift=window.max_shift
                )

                # Apply pattern to each chain
                for chain in chains:
                    pattern = self._get_expand_pattern(len(chain), window.max_shift)

                    if pattern is None:
                        # Chain of 7+ trips → EXCLUDE
                        self._record_exclusion(
                            f"expand_chain({len(chain)} trips)",
                            [t.id for t in chain],
                            f"Chain of {len(chain)} trips exceeds maximum allowed (max 6 trips)",
                            0,
                            0,
                            trips=chain,
                        )
                        logger.info(
                            f"[EXPAND_CHAIN] Excluded chain of {len(chain)} trips at {pickup_loc} "
                            f"(max 6 allowed)"
                        )
                        continue

                    # ✅ NEIGHBOR VALIDATION: Validar que no creamos gaps problemáticos con trips externos
                    chain_valid, neighbors_to_move = self._validate_and_adjust_neighbors(
                        chain, pattern, group_trips, window
                    )

                    if not chain_valid:
                        # OPCIÓN B: Cancelar expansión de esta cadena
                        self._record_exclusion(
                            f"expand_chain({len(chain)} trips)",
                            [t.id for t in chain],
                            "Neighbor collision unresolvable - would create gap in problem range",
                            0,
                            0,
                            trips=chain,
                        )
                        logger.warning(
                            f"[NEIGHBOR_COLLISION] Excluded chain of {len(chain)} trips at {pickup_loc} "
                            f"(cannot resolve neighbor collision)"
                        )
                        continue

                    # Apply shifts from pattern to chain
                    for i, trip in enumerate(chain):
                        shift = pattern[i]
                        if shift != 0:
                            old_time = self._get_effective_time(trip)
                            new_time = self._add_minutes(old_time, shift)
                            self._record_change(trip, old_time, new_time, "expand")

                    # Apply shifts to external neighbors (OPCIÓN A succeeded)
                    for neighbor_trip, neighbor_shift in neighbors_to_move:
                        old_time = self._get_effective_time(neighbor_trip)
                        new_time = self._add_minutes(old_time, neighbor_shift)
                        self._record_change(neighbor_trip, old_time, new_time, "expand")

                        # CRITICAL: Mark neighbor as modified by expand
                        # This prevents other chains from trying to move it (trip between two chains case)
                        self.modified_by_combine_expand.add(neighbor_trip.id)

                    logger.debug(
                        f"[EXPAND_CHAIN] Applied pattern {pattern} to chain of {len(chain)} trips "
                        f"at {pickup_loc}→{dropoff_loc}"
                        + (f" (adjusted {len(neighbors_to_move)} neighbors)" if neighbors_to_move else "")
                    )

    def _identify_expand_chains(
        self,
        trips: list[Trip],
        min_gap: int,
        max_gap: int,
        max_shift: int
    ) -> list[list[Trip]]:
        """
        Identifica cadenas de trips con gaps EN EL RANGO [min_gap, max_gap].

        Solo agrupa trips consecutivos si su gap está dentro del rango configurado.
        Trips con gap < min_gap: ya están muy juntos, NO expandir
        Trips con gap > max_gap: ya están suficientemente separados, NO expandir

        Args:
            trips: Lista de trips ordenados por pickup time
            min_gap: Gap mínimo para considerar trips en la misma cadena
            max_gap: Gap máximo para considerar trips en la misma cadena
            max_shift: Máximo desplazamiento permitido por trip

        Returns:
            Lista de cadenas (cada cadena es una lista de trips con gaps en rango)
        """
        if not trips:
            return []

        chains = []
        current_chain = [trips[0]]

        for i in range(1, len(trips)):
            prev_time = self._get_effective_time(trips[i-1])
            curr_time = self._get_effective_time(trips[i])
            gap = self._minutes_between(prev_time, curr_time)

            # ✅ FIX: Verificar que gap esté EN EL RANGO [min_gap, max_gap]
            if min_gap <= gap <= max_gap:
                # Gap dentro del rango → misma cadena
                current_chain.append(trips[i])
            else:
                # Gap fuera del rango → nueva cadena
                if len(current_chain) >= 2:
                    chains.append(current_chain)
                current_chain = [trips[i]]

        # Agregar última cadena si tiene al menos 2 trips
        if len(current_chain) >= 2:
            chains.append(current_chain)

        return chains

    def _get_expand_pattern(self, chain_length: int, max_shift: int) -> Optional[list[int]]:
        """
        Retorna patrón de shifts según tamaño de cadena.

        Patrón "Acordeón": Expande proporcionalmente desde el centro hacia afuera.

        - 2 trips: [-max, +max]
        - 3 trips: [-max, 0, +max]
        - 4 trips: [-max, -max/2, +max/2, +max]
        - 5 trips: [-max, -max/2, 0, +max/2, +max]
        - 6 trips: [-max, -max/2, -max/4, +max/4, +max/2, +max]
        - 7+ trips: None (excluir, cadena muy larga)
        """
        if chain_length < 2:
            return None
        elif chain_length > 6:
            return None  # Cadenas de 7+ trips son muy largas

        half_shift = max_shift // 2
        quarter_shift = max_shift // 4

        if chain_length == 2:
            return [-max_shift, +max_shift]
        elif chain_length == 3:
            return [-max_shift, 0, +max_shift]
        elif chain_length == 4:
            return [-max_shift, -half_shift, +half_shift, +max_shift]
        elif chain_length == 5:
            return [-max_shift, -half_shift, 0, +half_shift, +max_shift]
        elif chain_length == 6:
            return [-max_shift, -half_shift, -quarter_shift, +quarter_shift, +half_shift, +max_shift]

        return None

    def _calculate_neighbor_shift(
        self,
        time_a: time,
        time_b: time,
        max_gap: int,
        max_shift: int,
        direction: str
    ) -> Optional[int]:
        """
        Calcula el shift necesario para mover un neighbor y evitar gap problemático.

        Aplica directamente max_shift al vecino. Esto restaura el gap original
        que existía antes de la expansión de la cadena, el cual por definición
        era > max_gap (de lo contrario el vecino habría sido parte de la cadena).

        Args:
            time_a: Tiempo del primer trip (ya ajustado por expand)
            time_b: Tiempo del segundo trip (neighbor a mover)
            max_gap: Gap máximo del rango problemático
            max_shift: Máximo desplazamiento permitido
            direction: "backward" (neighbor antes de cadena) o "forward" (neighbor después)

        Returns:
            Shift a aplicar al neighbor (negativo o positivo), o None si el tiempo
            resultante cae fuera del rango del día
        """
        if direction == "backward":
            shift = -max_shift
            neighbor_time = time_a
        else:
            shift = max_shift
            neighbor_time = time_b

        try:
            new_neighbor_time = self._add_minutes(neighbor_time, shift)
        except ValueError:
            logger.debug(
                f"[NEIGHBOR_SHIFT] {shift}min: out of day range ❌"
            )
            return None

        if direction == "backward":
            new_gap = self._minutes_between(new_neighbor_time, time_b)
        else:
            new_gap = self._minutes_between(time_a, new_neighbor_time)

        logger.debug(
            f"[NEIGHBOR_SHIFT] {shift}min: gap={new_gap}min > {max_gap} ✅"
        )
        return shift

    def _validate_and_adjust_neighbors(
        self,
        chain: list[Trip],
        pattern: list[int],
        all_trips: list[Trip],
        window: TimeWindow
    ) -> tuple[bool, list[tuple[Trip, int]]]:
        """
        Valida que expandir la cadena no cree gaps problemáticos con neighbors externos.

        Si detecta colisión, intenta mover el neighbor externo progresivamente.

        Args:
            chain: Cadena de trips a expandir
            pattern: Patrón de shifts
            all_trips: Todos los trips del grupo (ordenados por tiempo)
            window: Configuración de ventana

        Returns:
            (chain_valid, neighbors_to_move)
        """
        neighbors_to_move = []

        # Encontrar índices de la cadena en all_trips
        first_chain_idx = all_trips.index(chain[0])
        last_chain_idx = all_trips.index(chain[-1])

        # VALIDAR BORDE IZQUIERDO
        if first_chain_idx > 0 and pattern[0] != 0:
            neighbor_prev = all_trips[first_chain_idx - 1]

            # VALIDACIONES DE BLOQUEO
            if neighbor_prev.combine_applied:
                logger.warning(
                    "[NEIGHBOR_COLLISION] Cannot move prev neighbor (has combine_applied). "
                    "Canceling chain expansion."
                )
                return False, []

            if neighbor_prev.expand_applied:
                logger.warning(
                    "[NEIGHBOR_COLLISION] Cannot move prev neighbor (already expanded). "
                    "Canceling chain expansion."
                )
                return False, []

            # Calcular gap que quedaría
            neighbor_time = self._get_effective_time(neighbor_prev)
            first_trip_old = self._get_effective_time(chain[0])
            first_trip_new = self._add_minutes(first_trip_old, pattern[0])

            gap_after_expand = self._minutes_between(neighbor_time, first_trip_new)

            # Si gap cae en rango problemático, intentar mover neighbor
            if window.min_gap <= gap_after_expand <= window.max_gap:
                neighbor_shift = self._calculate_neighbor_shift(
                    neighbor_time,
                    first_trip_new,
                    window.max_gap,
                    window.max_shift,
                    direction="backward"
                )

                if neighbor_shift is None:
                    logger.warning(
                        f"[NEIGHBOR_COLLISION] Cannot resolve collision with prev neighbor "
                        f"(tried up to max_shift={window.max_shift}). Canceling chain expansion."
                    )
                    return False, []

                neighbors_to_move.append((neighbor_prev, neighbor_shift))
                logger.info(
                    f"[NEIGHBOR_ADJUST] Moving prev neighbor by {neighbor_shift}min "
                    f"to avoid collision (gap will be > {window.max_gap})"
                )

        # VALIDAR BORDE DERECHO
        if last_chain_idx < len(all_trips) - 1 and pattern[-1] != 0:
            neighbor_next = all_trips[last_chain_idx + 1]

            # VALIDACIONES DE BLOQUEO
            if neighbor_next.combine_applied:
                logger.warning(
                    "[NEIGHBOR_COLLISION] Cannot move next neighbor (has combine_applied). "
                    "Canceling chain expansion."
                )
                return False, []

            if neighbor_next.expand_applied:
                logger.warning(
                    "[NEIGHBOR_COLLISION] Cannot move next neighbor (already expanded). "
                    "Canceling chain expansion."
                )
                return False, []

            # Calcular gap que quedaría
            neighbor_time = self._get_effective_time(neighbor_next)
            last_trip_old = self._get_effective_time(chain[-1])
            last_trip_new = self._add_minutes(last_trip_old, pattern[-1])

            gap_after_expand = self._minutes_between(last_trip_new, neighbor_time)

            # Si gap cae en rango problemático, intentar mover neighbor
            if window.min_gap <= gap_after_expand <= window.max_gap:
                neighbor_shift = self._calculate_neighbor_shift(
                    last_trip_new,
                    neighbor_time,
                    window.max_gap,
                    window.max_shift,
                    direction="forward"
                )

                if neighbor_shift is None:
                    logger.warning(
                        f"[NEIGHBOR_COLLISION] Cannot resolve collision with next neighbor "
                        f"(tried up to max_shift={window.max_shift}). Canceling chain expansion."
                    )
                    return False, []

                neighbors_to_move.append((neighbor_next, neighbor_shift))
                logger.info(
                    f"[NEIGHBOR_ADJUST] Moving next neighbor by {neighbor_shift}min "
                    f"to avoid collision (gap will be > {window.max_gap})"
                )

        return True, neighbors_to_move

    # =========================================================================
    # Internal Revert Logic
    # =========================================================================

    async def _revert_step_internal(
        self,
        step: FilterStep,
        location_id: UUID,
        airline: str,
        pick_up_date: date,
    ) -> StepRevertResult:
        """
        Internal method to revert a step.

        1. Mark step as inactive
        2. Reset all trips for this day to original_pick_up_time
        3. Re-apply remaining active steps in order
        4. Single commit at the end (atomic operation)

        PERFORMANCE FIX: Uses single commit pattern instead of multiple commits
        per step to avoid race condition and improve performance from ~15s to <2s.
        """
        step_id = step.id
        filter_type = step.filter_type

        # Mark step as inactive (no commit yet)
        step.is_active = False
        self.session.add(step)

        # Get all trips for this day that have filters applied
        trips_query = (
            Select(Trip)
            .Where(Trip.location_id == location_id)
            .Where(Trip.airline == airline)
            .Where(Trip.pick_up_date == pick_up_date)
            .Where(Trip.original_pick_up_time != None)
        )
        trips = await self.session.exec(trips_query).all()

        # Build in-memory lookup for efficient updates
        trip_lookup = {t.id: t for t in trips}

        # Reset all trips to original (no commit yet)
        for trip in trips:
            if trip.original_pick_up_time:
                trip.pick_up_time = trip.original_pick_up_time
                # Note: Don't clear original_pick_up_time yet, we may re-apply
                trip.reduce_applied = False
                trip.combine_applied = False
                trip.expand_applied = False
                trip.current_step_id = None
                trip.filtered_at = None
                trip.filter_order = None  # Reset filter order
                self.session.add(trip)

        # Get remaining active steps (excluding the one being reverted)
        active_steps_query = (
            Select(FilterStep)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.pick_up_date == pick_up_date)
            .Where(FilterStep.is_active == True)
            .Where(FilterStep.id != step_id)  # Exclude the step being reverted
            .OrderBy(FilterStep.step_order.Asc())
        )
        active_steps = await self.session.exec(active_steps_query).all()

        trips_recalculated = 0

        # Re-apply remaining steps if any (all in memory, single commit at end)
        if active_steps:
            for active_step in active_steps:
                self._reset_state()

                # Rebuild config from stored data
                config = FilterStepConfig(
                    filter_type=active_step.filter_type,
                    pick_up_date=str(pick_up_date),
                    windows=[TimeWindow(**w) for w in active_step.windows],
                )

                # Use trips from in-memory lookup (already updated by previous steps)
                current_trips = list(trip_lookup.values())

                # Apply filter
                if config.filter_type == "reduce":
                    self._apply_reduce(current_trips, config)
                elif config.filter_type == "combine":
                    self._apply_combine(current_trips, config)
                elif config.filter_type == "expand":
                    await self._apply_expand(current_trips, config)

                # Update trips in memory (no commit yet)
                now = datetime.utcnow()
                for change in self.changes:
                    trip = trip_lookup.get(change.trip_id)
                    if trip:
                        if trip.original_pick_up_time is None:
                            trip.original_pick_up_time = trip.pick_up_time
                        trip.pick_up_time = change.new_time
                        trip.current_step_id = active_step.id
                        trip.filtered_at = now

                        if config.filter_type == "reduce":
                            trip.reduce_applied = True
                        elif config.filter_type == "combine":
                            trip.combine_applied = True
                        elif config.filter_type == "expand":
                            trip.expand_applied = True

                        # Update filter_order for this trip
                        trip.filter_order = await self._build_filter_order_string(
                            trip, location_id, airline, pick_up_date
                        )

                        self.session.add(trip)
                        trips_recalculated += 1
        else:
            # No remaining steps, clear original_pick_up_time
            for trip in trips:
                trip.original_pick_up_time = None
                self.session.add(trip)
                trips_recalculated += 1  # Count trips reset to original

        # SINGLE COMMIT: All changes are committed atomically
        # This eliminates race condition where frontend could see intermediate state
        await self.session.commit()

        # AUTO-UPDATE PRESET: Update preset after step revert
        if active_steps:
            # Some filters remain → update preset with current config
            await self._auto_save_preset(location_id, airline, pick_up_date)
        else:
            # No filters remain for this day → check if ANY filters remain globally
            await self._update_preset_after_revert(location_id, airline, filter_type)

        # Get updated stack state
        stack_state = await self.get_stack(location_id, airline, str(pick_up_date))

        # No delay needed - single commit is already fully propagated
        # Send notification immediately
        await self._send_revert_notification(location_id, airline, step_id, filter_type)

        return StepRevertResult(
            step_id=step_id,
            filter_type=filter_type,
            trips_recalculated=trips_recalculated,
            remaining_steps=len(active_steps),
            stack_state=stack_state,
        )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _reset_state(self):
        """Reset internal state for new operation."""
        self.modified_by_combine_expand.clear()
        self.changes.clear()
        self.exclusions.clear()
        self.log.clear()

    def _validate_windows(self, windows: list[TimeWindow]):
        """
        Validate time windows.

        Rules:
        1. No overlapping windows
        2. No midnight crossing (start < end)
        3. At least one window must be enabled
        """
        if not windows:
            return  # Default window will be used

        enabled_windows = [w for w in windows if w.enabled]
        if not enabled_windows:
            raise ValueError("At least one window must be enabled")

        # Sort by start time
        sorted_windows = sorted(enabled_windows, key=lambda w: w.start)

        for i, window in enumerate(sorted_windows):
            # Check midnight crossing (already validated in model but double-check)
            if window.start >= window.end and window.end != "24:00":
                raise ValueError(
                    f"Window {window.start}-{window.end} crosses midnight"
                )

            # Check overlap with next window
            if i < len(sorted_windows) - 1:
                next_window = sorted_windows[i + 1]
                if window.end > next_window.start:
                    raise ValueError(
                        f"Windows overlap: {window.start}-{window.end} and "
                        f"{next_window.start}-{next_window.end}"
                    )

    async def _get_eligible_trips(
        self,
        location_id: UUID,
        airline: str,
        pick_up_date: date,
        trip_ids: Optional[list[UUID]] = None,
    ) -> list[Trip]:
        """
        Get trips eligible for filtering.

        If trip_ids is provided, only returns trips from that list.
        This is used for applying filters to newly imported trips only.
        """
        query = (
            Select(Trip)
            .Where(Trip.location_id == location_id)
            .Where(Trip.airline == airline)
            .Where(Trip.pick_up_date == pick_up_date)
            .Where(Trip.trip_type == TripType.OUTBOUND)
            .Where(Trip.status == TripStatus.SCHEDULED)
        )

        # Filter to specific trips if provided
        if trip_ids:
            query = query.Where(Trip.id.In(trip_ids))

        return await self.session.exec(query).all()

    async def _get_next_step_order(
        self,
        location_id: UUID,
        airline: str,
        pick_up_date: date,
    ) -> int:
        """Get the next step order number."""
        query = (
            Select(FilterStep.step_order)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.pick_up_date == pick_up_date)
            .OrderBy(FilterStep.step_order.Desc())
            .Limit(1)
        )
        result = await self.session.exec(query).first()
        # Handle RowResult from psqlmodel - extract scalar value
        if result is not None:
            step_order = result[0] if hasattr(result, '__getitem__') else result
            return step_order + 1
        return 1

    async def _build_filter_order_string(
        self,
        trip: Trip,
        location_id: UUID,
        airline: str,
        pick_up_date: date,
    ) -> Optional[str]:
        """
        Construye string con el orden cronológico de filtros aplicados (sin duplicados).

        Ejemplo: "expand,reduce" significa expand se aplicó primero, reduce después.

        Maneja correctamente casos con múltiples steps del mismo tipo activos
        (solo incluye cada tipo UNA vez, usando el step_order más bajo).

        Args:
            trip: Trip con flags actualizados
            location_id, airline, pick_up_date: Para buscar steps activos

        Returns:
            String como "expand,reduce" o "reduce,combine,expand" o None si no hay filtros
        """
        # Obtener steps activos para este día
        steps_query = (
            Select(FilterStep)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.pick_up_date == pick_up_date)
            .Where(FilterStep.is_active == True)
            .OrderBy(FilterStep.step_order.Asc())
        )
        active_steps = await self.session.exec(steps_query).all()

        if not active_steps:
            return None

        # Construir mapa: filter_type -> step_order más bajo (sin duplicados)
        filter_step_map = {}
        for step in active_steps:
            # Solo agregar si el trip tiene ese filtro Y no lo hemos agregado antes
            if step.filter_type == "reduce" and trip.reduce_applied:
                if "reduce" not in filter_step_map:
                    filter_step_map["reduce"] = step.step_order
            elif step.filter_type == "combine" and trip.combine_applied:
                if "combine" not in filter_step_map:
                    filter_step_map["combine"] = step.step_order
            elif step.filter_type == "expand" and trip.expand_applied:
                if "expand" not in filter_step_map:
                    filter_step_map["expand"] = step.step_order

        if not filter_step_map:
            return None

        # Ordenar por step_order y crear string (sin duplicados)
        filters_ordered = sorted(filter_step_map.items(), key=lambda x: x[1])
        return ",".join(f[0] for f in filters_ordered)

    def _filter_by_options(
        self,
        trips: list[Trip],
        config: FilterStepConfig,
    ) -> list[Trip]:
        """Filter trips by hotel names if specified (DEPRECATED - use _filter_by_hotel)."""
        if not config.hotel_names:
            return trips

        hotel_set = set(h.lower() for h in config.hotel_names)
        return [
            t for t in trips
            if t.pick_up_location and t.pick_up_location.lower() in hotel_set
        ]

    def _filter_by_hotel(
        self,
        trips: list[Trip],
        hotel_names: Optional[list[str]],
    ) -> list[Trip]:
        """Filter trips by hotel names (per-window version)."""
        if not hotel_names:
            return trips

        hotel_set = set(h.lower() for h in hotel_names)
        return [
            t for t in trips
            if t.pick_up_location and t.pick_up_location.lower() in hotel_set
        ]

    def _get_effective_time(self, trip: Trip) -> time:
        """
        Get effective pickup time for Combine/Expand calculations.

        Uses the CURRENT pick_up_time (already modified by previous filters)
        so that filters stack/accumulate in order of application.

        Example: Reduce → Combine
          - Reduce modifies 08:30 → 08:20
          - Combine uses 08:20 (not original 08:30)
          - Final time reflects both filters
        """
        # Check if we have a pending change (within same request)
        for change in reversed(self.changes):
            if change.trip_id == trip.id:
                return change.new_time

        # Use CURRENT time (already modified by previous filter steps)
        return trip.pick_up_time

    def _is_time_in_windows(self, t: time, windows: list[TimeWindow]) -> bool:
        """Check if time is within any enabled window."""
        if not windows:
            return True  # Default: all times

        for window in windows:
            if not window.enabled:
                continue

            start = self._parse_time_str(window.start)
            end = self._parse_time_str(window.end)

            if start <= t < end:
                return True

        return False

    def _is_time_in_window(self, t: time, window: TimeWindow) -> bool:
        """Check if time is within a specific window."""
        start = self._parse_time_str(window.start)
        end = self._parse_time_str(window.end)
        return start <= t < end

    def _parse_time_str(self, time_str: str) -> time:
        """Parse HH:MM string to time object."""
        if time_str == "24:00":
            return time(23, 59, 59)  # End of day
        parts = time_str.split(":")
        return time(int(parts[0]), int(parts[1]))

    def _is_valid_time(self, t: time) -> bool:
        """Check if time is valid (within 00:00-23:59)."""
        return 0 <= t.hour <= 23 and 0 <= t.minute <= 59

    def _record_change(
        self,
        trip: Trip,
        original_time: time,
        new_time: time,
        filter_type: str,
    ):
        """Record a trip modification."""
        self.changes.append(TripChange(
            trip_id=trip.id,
            original_time=original_time,
            new_time=new_time,
            filter_applied=filter_type,
            hotel_name=trip.pick_up_location or "",
            pick_up_date=str(trip.pick_up_date) if trip.pick_up_date else None,
            airline=trip.airline,
            flight_number=trip.flight_number,
        ))

    def _record_exclusion(
        self,
        operation: str,
        trip_ids: list[UUID],
        reason: str,
        gap_before: int,
        gap_after: int,
        trips: list[Trip] = None,
    ):
        """Record an excluded operation."""
        trips_info = []
        if trips:
            for trip in trips:
                pick_up_time_str = None
                if trip.pick_up_time:
                    pick_up_time_str = trip.pick_up_time.strftime("%H:%M")

                original_time_str = None
                if trip.original_pick_up_time:
                    original_time_str = trip.original_pick_up_time.strftime("%H:%M")

                trips_info.append(TripExclusionInfo(
                    trip_id=trip.id,
                    airline=trip.airline,
                    flight_number=trip.flight_number,
                    hotel_name=trip.pick_up_location or "",
                    pick_up_date=str(trip.pick_up_date) if trip.pick_up_date else None,
                    pick_up_time=pick_up_time_str,
                    original_pick_up_time=original_time_str,
                ))

        self.exclusions.append(FilterExclusion(
            operation=operation,
            trip_ids=trip_ids,
            reason=reason,
            gap_before=gap_before,
            gap_after=gap_after,
            trips_info=trips_info,
        ))

    # =========================================================================
    # Time Utility Methods
    # =========================================================================

    def _time_to_minutes(self, t: time) -> int:
        """Convert time to minutes from midnight."""
        return t.hour * 60 + t.minute

    def _minutes_to_time(self, minutes: int) -> time:
        """Convert minutes from midnight to time.

        V2: NO wrap-around. Raises ValueError if outside [0, 1440).
        """
        if minutes < 0 or minutes >= 24 * 60:
            raise ValueError(
                f"Time {minutes} min is outside day range [0, 1440)"
            )
        return time(hour=minutes // 60, minute=minutes % 60)

    def _minutes_between(self, t1: time, t2: time) -> int:
        """Calculate absolute minutes between two times."""
        m1 = self._time_to_minutes(t1)
        m2 = self._time_to_minutes(t2)
        return abs(m2 - m1)

    def _subtract_minutes(self, t: time, minutes: int) -> time:
        """Subtract minutes from a time.

        V2: Raises ValueError if result is outside day.
        """
        total = self._time_to_minutes(t) - minutes
        if total < 0 or total >= 24 * 60:
            raise ValueError(
                f"Result {total} min is outside day after subtracting {minutes} from {t}"
            )
        return time(hour=total // 60, minute=total % 60)

    def _add_minutes(self, t: time, minutes: int) -> time:
        """Add minutes to a time.

        V2: Raises ValueError if result is outside day.
        """
        total = self._time_to_minutes(t) + minutes
        if total < 0 or total >= 24 * 60:
            raise ValueError(
                f"Result {total} min is outside day after adding {minutes} to {t}"
            )
        return time(hour=total // 60, minute=total % 60)

    def _calculate_midpoint(self, t1: time, t2: time) -> time:
        """Calculate midpoint with round-half-up.

        Example: 08:07 + 08:08 = 487 + 488 = 975 / 2 = 487.5 → 488 (08:08)
        """
        m1 = self._time_to_minutes(t1)
        m2 = self._time_to_minutes(t2)
        mid = (m1 + m2 + 1) // 2  # Round half-up
        return self._minutes_to_time(mid)

    # =========================================================================
    # Auto-Save Preset
    # =========================================================================

    async def _auto_save_preset(
        self,
        location_id: UUID,
        airline: str,
        pick_up_date: date,
    ):
        """
        Auto-save the current day's stack as the preset for this location+airline.

        Called after successfully applying a filter step.
        This ensures the preset always reflects the latest configuration.
        """
        try:
            # Get all active steps for this day (the one we just modified)
            steps_query = (
                Select(FilterStep)
                .Where(FilterStep.location_id == location_id)
                .Where(FilterStep.airline == airline)
                .Where(FilterStep.pick_up_date == pick_up_date)
                .Where(FilterStep.is_active == True)
                .OrderBy(FilterStep.step_order.Asc())
            )
            active_steps = await self.session.exec(steps_query).all()

            if not active_steps:
                logger.debug(
                    f"[AUTO_PRESET] No active steps for {pick_up_date}, skipping preset save"
                )
                return

            # Build stack_template from active steps
            stack_template = []
            for step in active_steps:
                template = {
                    "filter_type": step.filter_type,
                    "windows": step.windows if step.windows else []
                }
                stack_template.append(template)

            # Import here to avoid circular import
            from features.trips.services.filter_preset_service import FilterPresetService

            preset_service = FilterPresetService(self.session)
            await preset_service.create_or_update_preset(
                location_id, airline, stack_template, user_id=None
            )

            logger.info(
                f"[AUTO_PRESET] Saved preset for {location_id}/{airline}: "
                f"{[s['filter_type'] for s in stack_template]}"
            )

        except Exception as e:
            # Don't fail the main operation if preset save fails
            logger.error(f"[AUTO_PRESET] Failed to save preset: {e}")

    async def _update_preset_after_revert(
        self,
        location_id: UUID,
        airline: str,
        filter_type: Optional[str],
    ):
        """
        Update or delete preset after bulk revert.

        - If all filter types were reverted (filter_type=None) → DELETE preset
        - If specific filter type was reverted → UPDATE preset to reflect remaining filters
        """
        try:
            # Import here to avoid circular import
            from features.trips.services.filter_preset_service import FilterPresetService

            preset_service = FilterPresetService(self.session)

            # Check if there are any remaining active steps for this location+airline
            remaining_query = (
                Select(FilterStep)
                .Where(FilterStep.location_id == location_id)
                .Where(FilterStep.airline == airline)
                .Where(FilterStep.is_active == True)
                .Limit(1)
            )
            remaining = await self.session.exec(remaining_query).first()

            if not remaining:
                # No active filters remain → DELETE preset
                await preset_service.delete_preset(location_id, airline)
                logger.info(
                    f"[AUTO_PRESET] Deleted preset for {location_id}/{airline}: "
                    f"No active filters remain after bulk revert"
                )
            else:
                # Some filters remain → UPDATE preset with any day's current config
                # Get the most recent day with active steps
                day_query = (
                    Select(FilterStep.pick_up_date)
                    .Where(FilterStep.location_id == location_id)
                    .Where(FilterStep.airline == airline)
                    .Where(FilterStep.is_active == True)
                    .OrderBy(FilterStep.pick_up_date.Desc())
                    .Limit(1)
                )
                recent_date_row = await self.session.exec(day_query).first()

                if recent_date_row:
                    # Extract date from row result
                    recent_date = recent_date_row[0] if hasattr(recent_date_row, '__getitem__') else recent_date_row

                    # Get that day's stack and save as preset
                    await self._auto_save_preset(location_id, airline, recent_date)
                    logger.info(
                        f"[AUTO_PRESET] Updated preset from {recent_date} after partial revert"
                    )

        except Exception as e:
            # Don't fail the main operation if preset update fails
            logger.error(f"[AUTO_PRESET] Failed to update preset after revert: {e}")

    # =========================================================================
    # Notification Methods
    # =========================================================================

    async def _send_step_notification(
        self,
        location_id: UUID,
        airline: str,
        step_id: UUID,
        filter_type: str,
        trips_affected: int,
        total_changes: int = None,
    ):
        """
        Send notification when a step is applied.

        Args:
            trips_affected: Trips NEWLY affected by this filter
            total_changes: Total trips modified (including re-applications)
        """
        from shared.redis.redis_client import redis_client
        import json

        # If total_changes not provided, use trips_affected
        if total_changes is None:
            total_changes = trips_affected

        # Intelligent message
        if trips_affected == 0 and total_changes > 0:
            message = f"Filter re-applied: {filter_type} ({total_changes} trips updated)"
        else:
            message = f"Filter applied: {filter_type} ({trips_affected} new trips)"

        event = {
            "type": "step_applied",
            "location_id": str(location_id),
            "airline": airline,
            "step_id": str(step_id),
            "filter_type": filter_type,
            "trips_affected": trips_affected,  # Solo nuevos
            "total_changes": total_changes,     # Total modificados
            "timestamp": datetime.utcnow().isoformat(),
            "message": message
        }

        channel = f"loc:{location_id}"
        await safe_redis_call(
            redis_client.publish,
            channel,
            json.dumps(event),
            context=f"publish {channel}",
        )

        logger.info(
            f"[STEP_FILTER] Notification sent: step={step_id}, "
            f"filter={filter_type}, new={trips_affected}, total={total_changes}"
        )

    async def _send_revert_notification(
        self,
        location_id: UUID,
        airline: str,
        step_id: UUID,
        filter_type: str,
    ):
        """Send notification when a step is reverted."""
        from shared.redis.redis_client import redis_client
        import json

        event = {
            "type": "step_reverted",
            "location_id": str(location_id),
            "airline": airline,
            "step_id": str(step_id),
            "filter_type": filter_type,
            "timestamp": datetime.utcnow().isoformat(),
            "message": f"Filter step reverted: {filter_type}"
        }

        channel = f"loc:{location_id}"
        await safe_redis_call(
            redis_client.publish,
            channel,
            json.dumps(event),
            context=f"publish {channel}",
        )

        logger.info(f"[STEP_FILTER] Revert notification sent: step={step_id}")

    # =========================================================================
    # Bulk Operations (Multi-Day)
    # =========================================================================

    async def _get_dates_with_eligible_trips(
        self,
        location_id: UUID,
        airline: str,
        date_from: date,
        date_to: Optional[date] = None,
    ) -> list[date]:
        """
        Get all unique pick_up_dates that have eligible trips in the date range.

        If date_to is None, returns all future dates from date_from.
        """
        from psqlmodel import Select

        query = (
            Select(Trip.pick_up_date)
            .Where(Trip.location_id == location_id)
            .Where(Trip.airline == airline)
            .Where(Trip.pick_up_date >= date_from)
            .Where(Trip.trip_type == TripType.OUTBOUND)
            .Where(Trip.status == TripStatus.SCHEDULED)
            .Distinct()
            .OrderBy(Trip.pick_up_date.Asc())
        )

        if date_to:
            query = query.Where(Trip.pick_up_date <= date_to)

        results = await self.session.exec(query).all()
        # Results come as RowResult objects (date,) when selecting single column
        # Access [0] to extract the actual date value
        return [r[0] if hasattr(r, '__getitem__') else r for r in results]

    async def _day_has_active_stack(
        self,
        location_id: UUID,
        airline: str,
        pick_up_date: date,
        filter_type: str | None = None,
    ) -> bool:
        """
        Check if a day already has active filter steps.

        Args:
            location_id: Location UUID
            airline: Airline code
            pick_up_date: Date to check
            filter_type: If provided, only check for steps of this specific type.
                        This allows stacking different filter types (reduce → combine → expand)
                        while preventing duplicate application of the same filter type.

        Returns:
            True if matching active step(s) exist.
        """
        query = (
            Select(FilterStep.id)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.pick_up_date == pick_up_date)
            .Where(FilterStep.is_active == True)
        )

        if filter_type:
            query = query.Where(FilterStep.filter_type == filter_type)

        query = query.Limit(1)
        result = await self.session.exec(query).first()
        return result is not None

    async def preview_bulk(
        self,
        location_id: UUID,
        airline: str,
        config: BulkFilterConfig,
    ) -> BulkStepResult:
        """
        Preview a filter across multiple days (bulk operation).

        Iterates through all dates with eligible trips and simulates
        the filter for each day.
        """
        date_from = date.fromisoformat(config.date_from)
        date_to = date.fromisoformat(config.date_to) if config.date_to else None

        # Get all dates with eligible trips
        dates = await self._get_dates_with_eligible_trips(
            location_id, airline, date_from, date_to
        )

        logger.info(
            f"[BULK_FILTER] Preview: {len(dates)} dates found for "
            f"location={location_id}, airline={airline}, "
            f"range={date_from} to {date_to or 'future'}"
        )

        if not dates:
            return BulkStepResult(
                filter_type=config.filter_type,
                date_from=config.date_from,
                date_to=config.date_to,
                total_days=0,
                days_processed=0,
                days_skipped=0,
                total_trips_modified=0,
                total_exclusions=0,
                by_date=[],
            )

        by_date = []
        all_changes = []
        all_exclusions = []
        days_processed = 0
        days_skipped = 0

        for pick_up_date in dates:
            # Check if we should skip days with existing stack OF THE SAME TYPE
            if config.skip_days_with_stack:
                has_stack = await self._day_has_active_stack(
                    location_id, airline, pick_up_date,
                    filter_type=config.filter_type  # Only skip if same type exists
                )
                if has_stack:
                    by_date.append(DayResult(
                        pick_up_date=str(pick_up_date),
                        trips_modified=0,
                        exclusions_count=0,
                        skipped=True,
                        skip_reason=f"Day already has active {config.filter_type} filter"
                    ))
                    days_skipped += 1
                    continue

            # Create per-day config
            day_config = FilterStepConfig(
                filter_type=config.filter_type,
                pick_up_date=str(pick_up_date),
                windows=config.windows,
            )

            # Preview for this day
            try:
                result = await self.preview_step(location_id, airline, day_config)

                by_date.append(DayResult(
                    pick_up_date=str(pick_up_date),
                    trips_modified=result.trips_modified,
                    exclusions_count=len(result.exclusions),
                    step_id=None,
                    skipped=False,
                ))

                all_changes.extend(result.changes)
                all_exclusions.extend(result.exclusions)
                days_processed += 1

            except Exception as e:
                logger.error(f"[BULK_FILTER] Error previewing {pick_up_date}: {e}")
                by_date.append(DayResult(
                    pick_up_date=str(pick_up_date),
                    trips_modified=0,
                    exclusions_count=0,
                    skipped=True,
                    skip_reason=f"Error: {str(e)}"
                ))
                days_skipped += 1

        return BulkStepResult(
            filter_type=config.filter_type,
            date_from=config.date_from,
            date_to=config.date_to,
            total_days=len(dates),
            days_processed=days_processed,
            days_skipped=days_skipped,
            total_trips_modified=sum(d.trips_modified for d in by_date if not d.skipped),
            total_exclusions=len(all_exclusions),
            by_date=by_date,
            all_changes=all_changes,
            all_exclusions=all_exclusions,
        )

    async def apply_bulk(
        self,
        location_id: UUID,
        airline: str,
        config: BulkFilterConfig,
    ) -> BulkStepResult:
        """
        Apply a filter across multiple days (bulk operation).

        Iterates through all dates with eligible trips and applies
        the filter for each day, creating one step per day.
        """
        date_from = date.fromisoformat(config.date_from)
        date_to = date.fromisoformat(config.date_to) if config.date_to else None

        # Get all dates with eligible trips
        dates = await self._get_dates_with_eligible_trips(
            location_id, airline, date_from, date_to
        )

        logger.info(
            f"[BULK_FILTER] Apply: {len(dates)} dates found for "
            f"location={location_id}, airline={airline}, "
            f"range={date_from} to {date_to or 'future'}"
        )

        if not dates:
            return BulkStepResult(
                filter_type=config.filter_type,
                date_from=config.date_from,
                date_to=config.date_to,
                total_days=0,
                days_processed=0,
                days_skipped=0,
                total_trips_modified=0,
                total_exclusions=0,
                by_date=[],
            )

        by_date = []
        all_changes = []
        all_exclusions = []
        days_processed = 0
        days_skipped = 0

        for pick_up_date in dates:
            # Check if we should skip days with existing stack OF THE SAME TYPE
            if config.skip_days_with_stack:
                has_stack = await self._day_has_active_stack(
                    location_id, airline, pick_up_date,
                    filter_type=config.filter_type  # Only skip if same type exists
                )
                if has_stack:
                    by_date.append(DayResult(
                        pick_up_date=str(pick_up_date),
                        trips_modified=0,
                        exclusions_count=0,
                        skipped=True,
                        skip_reason=f"Day already has active {config.filter_type} filter"
                    ))
                    days_skipped += 1
                    continue

            # Create per-day config
            day_config = FilterStepConfig(
                filter_type=config.filter_type,
                pick_up_date=str(pick_up_date),
                windows=config.windows,
            )

            # Apply for this day
            try:
                result = await self.apply_step(location_id, airline, day_config)

                by_date.append(DayResult(
                    pick_up_date=str(pick_up_date),
                    trips_modified=result.trips_modified,
                    exclusions_count=len(result.exclusions),
                    step_id=result.step_id,
                    skipped=False,
                ))

                all_changes.extend(result.changes)
                all_exclusions.extend(result.exclusions)
                days_processed += 1

            except Exception as e:
                logger.error(f"[BULK_FILTER] Error applying to {pick_up_date}: {e}")
                by_date.append(DayResult(
                    pick_up_date=str(pick_up_date),
                    trips_modified=0,
                    exclusions_count=0,
                    skipped=True,
                    skip_reason=f"Error: {str(e)}"
                ))
                days_skipped += 1

        # Apply to dates OUTSIDE the requested range that don't have this filter
        # This handles "orphan" dates (e.g., Jan 31 in a Feb upload)
        processed_dates = set(d.date() if hasattr(d, 'date') else d for d in dates)
        all_location_dates = await self._get_dates_with_eligible_trips(
            location_id, airline, date(2000, 1, 1), None
        )

        for pick_up_date in all_location_dates:
            if pick_up_date in processed_dates:
                continue

            has_this_filter = await self._day_has_active_stack(
                location_id, airline, pick_up_date,
                filter_type=config.filter_type
            )
            if has_this_filter:
                continue

            day_config = FilterStepConfig(
                filter_type=config.filter_type,
                pick_up_date=str(pick_up_date),
                windows=config.windows,
            )

            try:
                result = await self.apply_step(location_id, airline, day_config)
                by_date.append(DayResult(
                    pick_up_date=str(pick_up_date),
                    trips_modified=result.trips_modified,
                    exclusions_count=len(result.exclusions),
                    step_id=result.step_id,
                    skipped=False,
                ))
                all_changes.extend(result.changes)
                days_processed += 1

                logger.info(
                    f"[BULK_FILTER] Orphan date {pick_up_date}: applied {config.filter_type}"
                )
            except Exception as e:
                logger.error(f"[BULK_FILTER] Error on orphan {pick_up_date}: {e}")

        logger.info(
            f"[BULK_FILTER] Completed: {days_processed} days processed, "
            f"{days_skipped} skipped, {sum(d.trips_modified for d in by_date)} trips modified"
        )

        return BulkStepResult(
            filter_type=config.filter_type,
            date_from=config.date_from,
            date_to=config.date_to,
            total_days=len(dates),
            days_processed=days_processed,
            days_skipped=days_skipped,
            total_trips_modified=sum(d.trips_modified for d in by_date if not d.skipped),
            total_exclusions=len(all_exclusions),
            by_date=by_date,
            all_changes=all_changes,
            all_exclusions=all_exclusions,
        )

    async def get_bulk_eligibility(
        self,
        location_id: UUID,
        airline: str,
        date_from_str: str,
        date_to_str: Optional[str] = None,
        filter_type: Optional[str] = None,
    ) -> BulkEligibilityResult:
        """
        Check filter eligibility across multiple days.

        Returns summary and per-day breakdown of eligible trips.
        If filter_type is provided, includes filter-specific counts.
        """
        date_from = date.fromisoformat(date_from_str)
        date_to = date.fromisoformat(date_to_str) if date_to_str else None

        # Get all dates with eligible trips
        dates = await self._get_dates_with_eligible_trips(
            location_id, airline, date_from, date_to
        )

        by_date = []
        total_eligible = 0
        total_trips_with_filter = 0
        total_trips_new = 0

        for pick_up_date in dates:
            try:
                result = await self.get_eligibility(
                    location_id, airline, str(pick_up_date), filter_type
                )
                day_data = {
                    "pick_up_date": str(pick_up_date),
                    "total_trips": result.total_trips,
                    "eligible_trips": result.eligible_trips,
                    "already_filtered": result.already_filtered,
                    "by_hotel": result.by_hotel,
                }

                # Add filter-specific fields if filter_type provided
                if filter_type:
                    day_data["filter_type"] = filter_type
                    day_data["trips_with_filter"] = result.trips_with_filter or 0
                    day_data["trips_new"] = result.trips_new or 0
                    total_trips_with_filter += result.trips_with_filter or 0
                    total_trips_new += result.trips_new or 0

                by_date.append(day_data)
                total_eligible += result.eligible_trips
            except Exception as e:
                logger.error(f"[BULK_FILTER] Error getting eligibility for {pick_up_date}: {e}")
                by_date.append({
                    "pick_up_date": str(pick_up_date),
                    "eligible_trips": 0,
                    "error": str(e),
                })

        return BulkEligibilityResult(
            location_id=location_id,
            airline=airline,
            date_from=date_from_str,
            date_to=date_to_str,
            filter_type=filter_type,
            total_days=len(dates),
            total_trips=total_eligible,
            total_eligible=total_eligible,
            trips_with_filter=total_trips_with_filter if filter_type else None,
            trips_new=total_trips_new if filter_type else None,
            by_date=by_date,
        )

    async def revert_bulk(
        self,
        location_id: UUID,
        airline: str,
        config: BulkRevertConfig,
    ) -> BulkRevertResult:
        """
        Revert filter steps across multiple days (bulk operation).

        This allows reverting all steps of a specific filter_type (or all types)
        across a date range or all future dates.

        Args:
            location_id: Location UUID
            airline: Airline code
            config: BulkRevertConfig with date_from, date_to, filter_type

        Returns:
            BulkRevertResult with summary and per-day details
        """
        date_from = date.fromisoformat(config.date_from)
        date_to = date.fromisoformat(config.date_to) if config.date_to else None

        logger.info(
            f"[BULK_REVERT] Starting: location={location_id}, airline={airline}, "
            f"range={config.date_from} to {config.date_to or 'future'}, "
            f"filter_type={config.filter_type or 'all'}"
        )

        # Get all dates with active steps in range
        dates = await self._get_dates_with_active_steps(
            location_id, airline, date_from, date_to, config.filter_type
        )

        if not dates:
            logger.info("[BULK_REVERT] No dates with matching active steps found")
            return BulkRevertResult(
                date_from=config.date_from,
                date_to=config.date_to,
                filter_type=config.filter_type,
                total_days=0,
                days_with_reverts=0,
                days_skipped=0,
                total_steps_reverted=0,
                total_trips_recalculated=0,
                by_date=[],
            )

        by_date = []
        total_steps_reverted = 0
        total_trips_recalculated = 0
        days_with_reverts = 0
        days_skipped = 0

        for pick_up_date in dates:
            try:
                # Get active steps for this day matching filter_type
                steps_to_revert = await self._get_steps_to_revert(
                    location_id, airline, pick_up_date, config.filter_type
                )

                if not steps_to_revert:
                    by_date.append(DayRevertResult(
                        pick_up_date=str(pick_up_date),
                        steps_reverted=0,
                        step_ids=[],
                        trips_recalculated=0,
                        skipped=True,
                        skip_reason="No matching active steps",
                    ))
                    days_skipped += 1
                    continue

                # Revert each step
                step_ids = []
                trips_recalculated = 0

                for step in steps_to_revert:
                    result = await self._revert_step_internal(
                        step, location_id, airline, pick_up_date
                    )
                    step_ids.append(step.id)
                    trips_recalculated += result.trips_recalculated

                by_date.append(DayRevertResult(
                    pick_up_date=str(pick_up_date),
                    steps_reverted=len(step_ids),
                    step_ids=step_ids,
                    trips_recalculated=trips_recalculated,
                    skipped=False,
                ))

                total_steps_reverted += len(step_ids)
                total_trips_recalculated += trips_recalculated
                days_with_reverts += 1

                logger.debug(
                    f"[BULK_REVERT] Reverted {len(step_ids)} steps for {pick_up_date}"
                )

            except Exception as e:
                logger.error(f"[BULK_REVERT] Error reverting {pick_up_date}: {e}")
                by_date.append(DayRevertResult(
                    pick_up_date=str(pick_up_date),
                    steps_reverted=0,
                    step_ids=[],
                    trips_recalculated=0,
                    skipped=True,
                    skip_reason=str(e),
                ))
                days_skipped += 1

        logger.info(
            f"[BULK_REVERT] Completed: {days_with_reverts} days reverted, "
            f"{total_steps_reverted} steps, {total_trips_recalculated} trips"
        )

        # AUTO-UPDATE/DELETE PRESET after bulk revert
        if total_steps_reverted > 0:
            await self._update_preset_after_revert(location_id, airline, config.filter_type)

        return BulkRevertResult(
            date_from=config.date_from,
            date_to=config.date_to,
            filter_type=config.filter_type,
            total_days=len(dates),
            days_with_reverts=days_with_reverts,
            days_skipped=days_skipped,
            total_steps_reverted=total_steps_reverted,
            total_trips_recalculated=total_trips_recalculated,
            by_date=by_date,
        )

    async def _get_dates_with_active_steps(
        self,
        location_id: UUID,
        airline: str,
        date_from: date,
        date_to: Optional[date],
        filter_type: Optional[str] = None,
    ) -> list[date]:
        """
        Get all unique pick_up_dates that have active steps matching criteria.
        """
        query = (
            Select(FilterStep.pick_up_date)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.pick_up_date >= date_from)
            .Where(FilterStep.is_active == True)
            .Distinct()
            .OrderBy(FilterStep.pick_up_date.Asc())
        )

        if date_to:
            query = query.Where(FilterStep.pick_up_date <= date_to)

        if filter_type:
            query = query.Where(FilterStep.filter_type == filter_type)

        results = await self.session.exec(query).all()
        # Results come as RowResult objects, extract the date value
        return [r[0] if hasattr(r, '__getitem__') else r for r in results]

    async def _get_steps_to_revert(
        self,
        location_id: UUID,
        airline: str,
        pick_up_date: date,
        filter_type: Optional[str] = None,
    ) -> list[FilterStep]:
        """
        Get active steps for a day that should be reverted.

        Returns steps in reverse order (highest step_order first) so that
        reverts happen in correct stack order.
        """
        query = (
            Select(FilterStep)
            .Where(FilterStep.location_id == location_id)
            .Where(FilterStep.airline == airline)
            .Where(FilterStep.pick_up_date == pick_up_date)
            .Where(FilterStep.is_active == True)
            .OrderBy(FilterStep.step_order.Desc())
        )

        if filter_type:
            query = query.Where(FilterStep.filter_type == filter_type)

        return await self.session.exec(query).all()
