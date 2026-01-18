"""
Trip Filter Service

Implements the filtering logic for Outbound trips with status SCHEDULED:
- Reduce (Priority 0): Subtract fixed minutes from ORIGINAL pickup_time
- Combine (Priority 1): Move pairs of trips to their midpoint
- Expand (Priority 1): Separate pairs of trips while respecting No-Collision Rule

Filter Priority:
- Reduce has Priority 0 and ALWAYS operates on original_pick_up_time
- When Reduce changes, Combine/Expand automatically re-apply on the new reduced times
- Reduce is NOT subject to Rule A (doesn't block Combine/Expand)

Eligibility criteria:
- trip_type = OUTBOUND only
- status = SCHEDULED only
- Filtered by location_id and airline

Rules:
- Rule A: A trip modified by Combine/Expand cannot be modified again by Combine/Expand
- Rule B: No-Collision Rule - Expand must not create gaps that fall into Combine range
- Rounding: Configurable (multiple_of_5 or odd_minutes)
"""

from __future__ import annotations

import logging
from datetime import time, datetime, date
from typing import Optional
from uuid import UUID, uuid4

from psqlmodel import AsyncSession, Select

from shared.db.schemas import Trip, TripType, TripStatus, FilterType, FilterBatch
from features.trips.models.filter_models import (
    FilterRequest,
    ReduceFilterConfig,
    CombineFilterConfig,
    ExpandFilterConfig,
    TimeRange,
    TripChange,
    FilterExclusion,
    FilterPreviewResult,
    FilterApplyResult,
    FilterRevertResult,
    FilterRevertPartialResult,
    RoundingMode,
)
from shared.utils.time_formatter import format_time

logger = logging.getLogger(__name__)


class TripFilterService:
    """
    Service for filtering trips pickup times.

    Eligibility criteria:
    - trip_type = OUTBOUND only
    - status = SCHEDULED only
    - Filtered by location_id and airline

    Responsibilities:
    - Get eligible trips (outbound + scheduled)
    - Apply pre-selection filters (hotel, time_range)
    - Execute filters in order: Reduce (Priority 0) → Combine (Priority 1) → Expand (Priority 1)
    - Reduce: Always operates on original_pick_up_time, not subject to Rule A
    - Combine/Expand: Operate on effective times (after Reduce), subject to Rule A
    - Respect Rule A: trips modified by Combine/Expand cannot be modified again by Combine/Expand
    - Respect Rule B: No-Collision Rule for Expand
    - Round results based on configured rounding mode (multiple_of_5 or odd_minutes)
    - Generate detailed logs
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.modified_by_combine_expand: set[UUID] = set()  # Rule A tracking (only for Combine/Expand)
        self.changes: list[TripChange] = []
        self.exclusions: list[FilterExclusion] = []
        self.log: list[dict] = []
        self.rounding_mode: RoundingMode = RoundingMode.MULTIPLE_OF_5  # Default rounding mode

    async def preview(
        self,
        location_id: UUID,
        airline: str,
        config: FilterRequest,
        time_format: str = "24h",
    ) -> FilterPreviewResult:
        """
        Simulate filters without applying changes.
        Returns proposed changes for user review.

        Args:
            location_id: UUID of the location
            airline: Airline code (e.g., "WN", "AA")
            config: Filter configuration
        """
        # Reset state
        self._reset_state()

        # Set rounding mode from config
        self.rounding_mode = config.rounding_mode

        # Parse date filters
        date_from = date.fromisoformat(config.pick_up_date_from) if config.pick_up_date_from else None
        date_to = date.fromisoformat(config.pick_up_date_to) if config.pick_up_date_to else None

        # Get eligible trips
        trips = await self._get_eligible_trips(location_id, airline, date_from, date_to)
        total_evaluated = len(trips)

        logger.info(f"[FILTER] Eligible trips found: {total_evaluated} for location={location_id}, airline={airline}")
        logger.info(f"[FILTER] Config: reduce={config.reduce}, combine={config.combine}, expand={config.expand}")

        if not trips:
            return FilterPreviewResult(
                location_id=location_id,
                airline=airline,
                changes=[],
                exclusions=[],
                summary={"reduce": 0, "combine": 0, "expand": 0, "excluded": 0},
                total_trips_evaluated=0,
                eligible_trips=0,
            )

        # Apply filters in order (simulation only)
        if config.reduce and config.reduce.enabled:
            filtered_trips = self._filter_by_options(trips, config.reduce)
            logger.info(f"[FILTER] Reduce: {len(filtered_trips)} trips after filter_by_options (minutes={config.reduce.minutes_to_reduce})")
            self._apply_reduce(filtered_trips, config.reduce)
            logger.info(f"[FILTER] Reduce: {len(self.changes)} changes recorded")

        if config.combine and config.combine.enabled:
            filtered_trips = self._filter_by_options(trips, config.combine)
            logger.info(f"[FILTER] Combine: {len(filtered_trips)} trips after filter_by_options (gap={config.combine.min_gap}-{config.combine.max_gap})")
            self._apply_combine(filtered_trips, config.combine)
            logger.info(f"[FILTER] Combine: {len(self.changes)} total changes")

        if config.expand and config.expand.enabled:
            filtered_trips = self._filter_by_options(trips, config.expand)
            self._apply_expand(filtered_trips, config.expand, config.combine)

        # Build summary
        summary = self._build_summary()

        # Format time fields according to user preference
        formatted_changes = self._format_changes(self.changes, time_format)

        return FilterPreviewResult(
            location_id=location_id,
            airline=airline,
            changes=formatted_changes,
            exclusions=self.exclusions,
            summary=summary,
            total_trips_evaluated=total_evaluated,
            eligible_trips=len(trips),
        )

    async def apply(
        self,
        location_id: UUID,
        airline: str,
        config: FilterRequest,
        time_format: str = "24h",
    ) -> FilterApplyResult:
        """
        Apply filters and persist changes to database.

        Args:
            location_id: UUID of the location
            airline: Airline code (e.g., "WN", "AA")
            config: Filter configuration
        """
        # Reset state
        self._reset_state()
        batch_id = uuid4()

        # Set rounding mode from config
        self.rounding_mode = config.rounding_mode

        # Parse date filters
        date_from = date.fromisoformat(config.pick_up_date_from) if config.pick_up_date_from else None
        date_to = date.fromisoformat(config.pick_up_date_to) if config.pick_up_date_to else None

        # Get eligible trips
        trips = await self._get_eligible_trips(location_id, airline, date_from, date_to)

        if not trips:
            return FilterApplyResult(
                batch_id=batch_id,
                location_id=location_id,
                airline=airline,
                changes_applied=0,
                exclusions=[],
                log=[{"message": "No eligible trips found"}],
                summary={"reduce": 0, "combine": 0, "expand": 0, "excluded": 0},
            )

        # Build trip lookup for DB updates
        trip_lookup = {t.id: t for t in trips}

        # Apply filters in order
        if config.reduce and config.reduce.enabled:
            filtered_trips = self._filter_by_options(trips, config.reduce)
            self._apply_reduce(filtered_trips, config.reduce)

        if config.combine and config.combine.enabled:
            filtered_trips = self._filter_by_options(trips, config.combine)
            self._apply_combine(filtered_trips, config.combine)

        if config.expand and config.expand.enabled:
            filtered_trips = self._filter_by_options(trips, config.expand)
            self._apply_expand(filtered_trips, config.expand, config.combine)

        # Persist changes to database
        now = datetime.utcnow()
        for change in self.changes:
            trip = trip_lookup.get(change.trip_id)
            if trip:
                # Store original if not already stored
                if trip.original_pick_up_time is None:
                    trip.original_pick_up_time = trip.pick_up_time

                # Apply new time
                trip.pick_up_time = change.new_time
                trip.filter_applied = change.filter_applied
                trip.filter_batch_id = batch_id
                trip.filtered_at = now
                trip.updated_at = now

                # Add trip to session to ensure changes are tracked
                self.session.add(trip)

                self.log.append({
                    "trip_id": str(trip.id),
                    "action": "modified",
                    "filter": change.filter_applied,
                    "original_time": str(change.original_time),
                    "new_time": str(change.new_time),
                    "hotel": change.hotel_name,
                    "airline": trip.airline,
                })

        # Create FilterBatch record for tracking and partial revert
        filters_applied = []
        if config.reduce and config.reduce.enabled:
            filters_applied.append("reduce")
        if config.combine and config.combine.enabled:
            filters_applied.append("combine")
        if config.expand and config.expand.enabled:
            filters_applied.append("expand")

        filter_batch = FilterBatch(
            id=batch_id,
            location_id=location_id,
            airline=airline,
            config=config.model_dump(mode="json"),  # Store full config as JSON
            filters_applied=filters_applied,
            trips_affected=len(self.changes),
        )
        self.session.add(filter_batch)

        # Commit changes
        await self.session.commit()

        summary = self._build_summary()

        return FilterApplyResult(
            batch_id=batch_id,
            location_id=location_id,
            airline=airline,
            changes_applied=len(self.changes),
            exclusions=self.exclusions,
            log=self.log,
            summary=summary,
        )

    async def revert(
        self,
        location_id: UUID,
        airline: str,
        batch_id: Optional[UUID] = None,
    ) -> FilterRevertResult:
        """
        Revert filtered trips to their original pickup times.

        Args:
            location_id: Location scope
            airline: Airline code to filter
            batch_id: If provided, only revert trips from this batch.
                      If None, revert all filtered trips for this location+airline.
        """
        # Build query
        query = (
            Select(Trip)
            .Where(Trip.location_id == location_id)
            .Where(Trip.airline == airline)
            .Where(Trip.filter_applied != None)
            .Where(Trip.original_pick_up_time != None)
        )

        if batch_id:
            query = query.Where(Trip.filter_batch_id == batch_id)

        trips = await self.session.exec(query).all()

        reverted_count = 0
        batch_ids_reverted: set[UUID] = set()

        for trip in trips:
            if trip.original_pick_up_time:
                trip.pick_up_time = trip.original_pick_up_time
                trip.original_pick_up_time = None
                trip.filter_applied = None
                if trip.filter_batch_id:
                    batch_ids_reverted.add(trip.filter_batch_id)
                trip.filter_batch_id = None
                trip.filtered_at = None
                trip.updated_at = datetime.utcnow()

                # Add trip to session to ensure changes are tracked
                self.session.add(trip)

                reverted_count += 1

        await self.session.commit()

        return FilterRevertResult(
            trips_reverted=reverted_count,
            batch_ids_reverted=list(batch_ids_reverted),
        )

    async def revert_partial(
        self,
        batch_id: UUID,
        filter_type: str,
    ) -> FilterRevertPartialResult:
        """
        Revert a specific filter type from a batch while keeping other filters applied.

        This method:
        1. Fetches the original batch configuration
        2. Reverts all trips in that batch to original_pick_up_time
        3. Re-applies remaining filters (excluding the one being reverted)
        4. Updates the FilterBatch revert_history

        Args:
            batch_id: UUID of the filter batch
            filter_type: Which filter to revert ("reduce", "combine", or "expand")

        Returns:
            FilterRevertPartialResult with details of the operation

        Raises:
            ValueError: If batch not found or filter was not applied in this batch
        """
        # Validate filter_type
        valid_filters = {"reduce", "combine", "expand"}
        if filter_type not in valid_filters:
            raise ValueError(f"filter_type must be one of {valid_filters}, got: {filter_type}")

        # Fetch FilterBatch record
        batch_query = Select(FilterBatch).Where(FilterBatch.id == batch_id)
        filter_batch = await self.session.exec(batch_query).first()

        if not filter_batch:
            raise ValueError(f"FilterBatch with id {batch_id} not found")

        # Check if this filter was actually applied
        if filter_type not in filter_batch.filters_applied:
            raise ValueError(
                f"Filter '{filter_type}' was not applied in batch {batch_id}. "
                f"Applied filters were: {filter_batch.filters_applied}"
            )

        # Get all trips affected by this batch
        trips_query = (
            Select(Trip)
            .Where(Trip.filter_batch_id == batch_id)
            .Where(Trip.original_pick_up_time != None)
        )
        trips = await self.session.exec(trips_query).all()

        if not trips:
            raise ValueError(f"No trips found for batch {batch_id}")

        # Step 1: Revert all trips to original_pick_up_time
        for trip in trips:
            if trip.original_pick_up_time:
                trip.pick_up_time = trip.original_pick_up_time
                trip.original_pick_up_time = None
                trip.filter_applied = None
                trip.filter_batch_id = None
                trip.filtered_at = None
                trip.updated_at = datetime.utcnow()
                self.session.add(trip)

        await self.session.commit()

        # Step 2: Reconstruct config without the filter being reverted
        original_config = FilterRequest(**filter_batch.config)
        modified_config = original_config.model_copy(deep=True)

        # Disable the filter being reverted
        if filter_type == "reduce" and modified_config.reduce:
            modified_config.reduce.enabled = False
        elif filter_type == "combine" and modified_config.combine:
            modified_config.combine.enabled = False
        elif filter_type == "expand" and modified_config.expand:
            modified_config.expand.enabled = False

        # Determine which filters remain enabled
        remaining_filters = []
        if modified_config.reduce and modified_config.reduce.enabled:
            remaining_filters.append("reduce")
        if modified_config.combine and modified_config.combine.enabled:
            remaining_filters.append("combine")
        if modified_config.expand and modified_config.expand.enabled:
            remaining_filters.append("expand")

        # Step 3: Re-apply remaining filters if any
        changes_applied = 0
        summary = {"reduce": 0, "combine": 0, "expand": 0, "excluded": 0}

        if remaining_filters:
            # Re-apply using the existing apply logic
            result = await self.apply(
                location_id=filter_batch.location_id,
                airline=filter_batch.airline,
                config=modified_config,
            )
            changes_applied = result.changes_applied
            summary = result.summary

            # Delete the new batch created by apply() since we're reusing the old batch_id
            # The trips now have a new batch_id from the apply() call
            new_batch_id = result.batch_id

            # Fetch and delete the new batch
            new_batch_query = Select(FilterBatch).Where(FilterBatch.id == new_batch_id)
            new_batch = await self.session.exec(new_batch_query).first()
            if new_batch:
                self.session.delete(new_batch)

            # Update trips to reference the original batch_id
            updated_trips_query = (
                Select(Trip)
                .Where(Trip.filter_batch_id == new_batch_id)
            )
            updated_trips = await self.session.exec(updated_trips_query).all()
            for trip in updated_trips:
                trip.filter_batch_id = batch_id
                self.session.add(trip)

            await self.session.commit()

        # Step 4: Update FilterBatch with new config and revert history
        filter_batch.config = modified_config.model_dump(mode="json")
        filter_batch.filters_applied = remaining_filters
        filter_batch.trips_affected = changes_applied

        # Track revert in history
        if filter_batch.revert_history is None:
            filter_batch.revert_history = {}

        filter_batch.revert_history[filter_type] = {
            "reverted_at": datetime.utcnow().isoformat(),
            "trips_affected": len(trips),
            "filters_reapplied": remaining_filters,
        }

        self.session.add(filter_batch)
        await self.session.commit()

        return FilterRevertPartialResult(
            batch_id=batch_id,
            filter_reverted=filter_type,
            trips_affected=len(trips),
            filters_reapplied=remaining_filters,
            changes_applied=changes_applied,
            summary=summary,
        )

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _reset_state(self):
        """Reset internal state for new operation."""
        self.modified_by_combine_expand.clear()
        self.changes.clear()
        self.exclusions.clear()
        self.log.clear()

    async def _get_eligible_trips(
        self,
        location_id: UUID,
        airline: str,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> list[Trip]:
        """
        Get trips eligible for filtering.

        Criteria:
        - trip_type = OUTBOUND only
        - status = SCHEDULED only
        - Matches location_id and airline
        - Optionally filters by pick_up_date range
        """
        query = (
            Select(Trip)
            .Where(Trip.location_id == location_id)
            .Where(Trip.airline == airline)
            .Where(Trip.trip_type == TripType.OUTBOUND)
            .Where(Trip.status == TripStatus.SCHEDULED)
        )

        # Apply date filters if provided
        if date_from:
            query = query.Where(Trip.pick_up_date >= date_from)
        if date_to:
            query = query.Where(Trip.pick_up_date <= date_to)

        return await self.session.exec(query).all()

    def _filter_by_options(
        self,
        trips: list[Trip],
        config: ReduceFilterConfig | CombineFilterConfig | ExpandFilterConfig,
    ) -> list[Trip]:
        """
        Apply pre-selection filters (hotel names, time range).
        """
        result = trips

        # Filter by hotel names
        if config.hotel_names:
            hotel_set = set(h.lower() for h in config.hotel_names)
            result = [
                t for t in result
                if t.pick_up_location and t.pick_up_location.lower() in hotel_set
            ]

        # Filter by time range
        if config.time_range:
            result = [
                t for t in result
                if self._is_time_in_range(t.pick_up_time, config.time_range)
            ]

        return result

    def _is_time_in_range(self, t: time, time_range: TimeRange) -> bool:
        """
        Check if a time falls within a range.
        Handles midnight crossing (e.g., 22:00 - 02:00).
        """
        start = time_range.start
        end = time_range.end

        if start <= end:
            # Normal range (e.g., 05:00 - 10:00)
            return start <= t <= end
        else:
            # Midnight crossing (e.g., 22:00 - 02:00)
            return t >= start or t <= end

    def _apply_reduce(self, trips: list[Trip], config: ReduceFilterConfig):
        """
        Apply Reduce filter: subtract fixed minutes from ORIGINAL pickup_time.

        Priority 0: Always operates on original_pick_up_time, not modified times.
        Does NOT block Combine/Expand (not subject to Rule A).

        When Reduce changes configuration, Combine/Expand will automatically
        re-apply on the new reduced times.
        """
        for trip in trips:
            # Use original_pick_up_time if it exists, otherwise use current pick_up_time
            base_time = trip.original_pick_up_time if trip.original_pick_up_time else trip.pick_up_time

            new_time = self._subtract_minutes(base_time, config.minutes_to_reduce)
            new_time = self._round_time(new_time)  # Use configurable rounding

            # Record using base_time as original (the true original)
            self._record_change(trip, base_time, new_time, FilterType.REDUCE)

            # NOTE: Do NOT add to modified_by_combine_expand
            # Reduce does not block Combine/Expand from modifying the same trip

    def _apply_combine(self, trips: list[Trip], config: CombineFilterConfig):
        """
        Apply Combine filter: move pairs to their midpoint.
        Only combines trips on the same pick_up_date.

        Priority 1: Operates AFTER Reduce (uses effective times with Reduce applied).
        Subject to Rule A: A trip modified by Combine cannot be modified again by Combine/Expand.
        """
        # Group trips by pick_up_date
        from collections import defaultdict
        trips_by_date = defaultdict(list)
        for trip in trips:
            if trip.pick_up_date:
                trips_by_date[trip.pick_up_date].append(trip)

        # Process each date separately
        for pick_up_date, day_trips in trips_by_date.items():
            # Sort by effective pickup time (with Reduce applied if exists)
            sorted_trips = sorted(day_trips, key=lambda t: self._time_to_minutes(self._get_effective_time(t)))

            i = 0
            while i < len(sorted_trips) - 1:
                trip_a = sorted_trips[i]
                trip_b = sorted_trips[i + 1]

                # Skip if either already modified by Combine/Expand (Rule A)
                if trip_a.id in self.modified_by_combine_expand or trip_b.id in self.modified_by_combine_expand:
                    i += 1
                    continue

                # Get effective times (with Reduce applied if exists)
                time_a = self._get_effective_time(trip_a)
                time_b = self._get_effective_time(trip_b)

                gap = self._minutes_between(time_a, time_b)

                if config.min_gap <= gap <= config.max_gap:
                    midpoint = self._calculate_midpoint(time_a, time_b)
                    midpoint = self._round_time(midpoint)  # Use configurable rounding

                    # Record using effective times as original
                    self._record_change(trip_a, time_a, midpoint, FilterType.COMBINE)
                    self._record_change(trip_b, time_b, midpoint, FilterType.COMBINE)

                    self.modified_by_combine_expand.add(trip_a.id)
                    self.modified_by_combine_expand.add(trip_b.id)

                    i += 2  # Skip both
                else:
                    i += 1

    def _apply_expand(
        self,
        trips: list[Trip],
        config: ExpandFilterConfig,
        combine_config: Optional[CombineFilterConfig],
    ):
        """
        Apply Expand filter: separate pairs while respecting No-Collision Rule.
        Only expands trips on the same pick_up_date.

        Priority 1: Operates AFTER Reduce (uses effective times with Reduce applied).
        Subject to Rule A: A trip modified by Expand cannot be modified again by Combine/Expand.
        Subject to Rule B: No-Collision Rule with Combine.
        """
        # Group trips by pick_up_date
        from collections import defaultdict
        trips_by_date = defaultdict(list)
        for trip in trips:
            if trip.pick_up_date:
                trips_by_date[trip.pick_up_date].append(trip)

        # Process each date separately
        for pick_up_date, day_trips in trips_by_date.items():
            # Sort by effective pickup time (with Reduce applied if exists)
            sorted_trips = sorted(day_trips, key=lambda t: self._time_to_minutes(self._get_effective_time(t)))

            for i in range(len(sorted_trips) - 1):
                trip_a = sorted_trips[i]
                trip_b = sorted_trips[i + 1]

                # Skip if either already modified by Combine/Expand (Rule A)
                if trip_a.id in self.modified_by_combine_expand or trip_b.id in self.modified_by_combine_expand:
                    continue

                # Get effective times (with Reduce applied if exists)
                time_a = self._get_effective_time(trip_a)
                time_b = self._get_effective_time(trip_b)

                gap = self._minutes_between(time_a, time_b)

                if config.min_gap <= gap <= config.max_gap:
                    # Simulate expansion on effective times
                    new_time_a, new_time_b = self._simulate_expand(
                        time_a,
                        time_b,
                        config.max_shift,
                    )

                    # No-Collision Rule (Rule B)
                    if combine_config and combine_config.enabled:
                        collision = False

                        # Check gap with previous neighbor (i-1) within same date
                        if i > 0:
                            prev_trip = sorted_trips[i - 1]
                            prev_time = self._get_effective_time(prev_trip)
                            gap_with_prev = self._minutes_between(prev_time, new_time_a)

                            if combine_config.min_gap <= gap_with_prev <= combine_config.max_gap:
                                self._record_exclusion(
                                    f"expand({trip_a.id}, {trip_b.id})",
                                    [trip_a.id, trip_b.id],
                                    f"Collision: gap with previous trip would enter Combine range ({gap_with_prev} min)",
                                    gap,
                                    gap_with_prev,
                                )
                                collision = True

                        # Check gap with next neighbor (i+2) within same date
                        if not collision and i + 2 < len(sorted_trips):
                            next_trip = sorted_trips[i + 2]
                            next_time = self._get_effective_time(next_trip)
                            gap_with_next = self._minutes_between(new_time_b, next_time)

                            if combine_config.min_gap <= gap_with_next <= combine_config.max_gap:
                                self._record_exclusion(
                                    f"expand({trip_a.id}, {trip_b.id})",
                                    [trip_a.id, trip_b.id],
                                    f"Collision: gap with next trip would enter Combine range ({gap_with_next} min)",
                                    gap,
                                    gap_with_next,
                                )
                                collision = True

                        if collision:
                            continue

                    # Apply expansion using effective times as original
                    self._record_change(trip_a, time_a, new_time_a, FilterType.EXPAND)
                    self._record_change(trip_b, time_b, new_time_b, FilterType.EXPAND)

                    self.modified_by_combine_expand.add(trip_a.id)
                    self.modified_by_combine_expand.add(trip_b.id)

    def _get_effective_time(self, trip: Trip) -> time:
        """
        Get the effective pickup time for a trip.

        Priority: Most recent change > original pick_up_time

        This ensures Combine/Expand operate on times AFTER Reduce has been applied.
        When multiple filters modify the same trip, the last change is used.
        """
        # Look for the most recent change (iterate backwards)
        for change in reversed(self.changes):
            if change.trip_id == trip.id:
                return change.new_time

        return trip.pick_up_time

    def _simulate_expand(
        self,
        time_a: time,
        time_b: time,
        max_shift: int,
    ) -> tuple[time, time]:
        """
        Simulate expansion of a pair.
        Distribution: 1/3 to earlier (backwards), 2/3 to later (forwards).
        """
        shift_a = max_shift // 3  # Earlier moves backwards
        shift_b = max_shift - shift_a  # Later moves forwards

        new_time_a = self._subtract_minutes(time_a, shift_a)
        new_time_b = self._add_minutes(time_b, shift_b)

        return self._round_time(new_time_a), self._round_time(new_time_b)

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
        ))

    def _record_exclusion(
        self,
        operation: str,
        trip_ids: list[UUID],
        reason: str,
        gap_before: int,
        gap_after: int,
    ):
        """Record an excluded operation."""
        self.exclusions.append(FilterExclusion(
            operation=operation,
            trip_ids=trip_ids,
            reason=reason,
            gap_before=gap_before,
            gap_after=gap_after,
        ))

        self.log.append({
            "action": "exclusion",
            "operation": operation,
            "reason": reason,
            "gap_before": gap_before,
            "gap_after": gap_after,
        })

    def _build_summary(self) -> dict:
        """Build summary of changes."""
        summary = {
            "reduce": 0,
            "combine": 0,
            "expand": 0,
            "excluded": len(self.exclusions),
        }

        for change in self.changes:
            if change.filter_applied in summary:
                summary[change.filter_applied] += 1

        return summary

    def _format_changes(self, changes: list[TripChange], time_format: str) -> list[TripChange]:
        """
        Format time fields in TripChange objects according to user preference.

        Args:
            changes: List of TripChange objects with time objects
            time_format: "24h" or "12h"

        Returns:
            List of TripChange objects with formatted time strings
        """
        formatted_changes = []
        for change in changes:
            # Create a new TripChange with formatted times
            formatted_change = TripChange(
                trip_id=change.trip_id,
                original_time=format_time(change.original_time, time_format),
                new_time=format_time(change.new_time, time_format),
                filter_applied=change.filter_applied,
                hotel_name=change.hotel_name,
                pick_up_date=change.pick_up_date,
                airline=change.airline,
            )
            formatted_changes.append(formatted_change)
        return formatted_changes

    # =========================================================================
    # Time Utility Methods
    # =========================================================================

    def _time_to_minutes(self, t: time) -> int:
        """Convert time to minutes from midnight."""
        return t.hour * 60 + t.minute

    def _minutes_to_time(self, minutes: int, tzinfo=None) -> time:
        """Convert minutes from midnight to time."""
        # Handle negative or overflow
        minutes = minutes % (24 * 60)
        return time(hour=minutes // 60, minute=minutes % 60, tzinfo=tzinfo)

    def _minutes_between(self, t1: time, t2: time) -> int:
        """Calculate absolute minutes between two times."""
        m1 = self._time_to_minutes(t1)
        m2 = self._time_to_minutes(t2)
        return abs(m2 - m1)

    def _round_time(self, t: time) -> time:
        """
        Round time based on configured rounding mode.

        Modes:
        - MULTIPLE_OF_5: Round to nearest 5-minute multiple (10:15, 1:25)
        - ODD_MINUTES: Keep odd minutes, no rounding (2:11, 5:27)
        """
        if self.rounding_mode == RoundingMode.MULTIPLE_OF_5:
            return self._round_to_5_minutes(t)
        elif self.rounding_mode == RoundingMode.ODD_MINUTES:
            # No rounding, return as-is
            return t
        else:
            # Default to multiple of 5 for backwards compatibility
            return self._round_to_5_minutes(t)

    def _round_to_5_minutes(self, t: time) -> time:
        """Round time to nearest 5-minute multiple."""
        total_minutes = self._time_to_minutes(t)
        rounded = round(total_minutes / 5) * 5
        # Handle overflow (e.g., 23:58 rounded to 24:00 -> 00:00)
        rounded = rounded % (24 * 60)
        return time(hour=rounded // 60, minute=rounded % 60, tzinfo=t.tzinfo)

    def _subtract_minutes(self, t: time, minutes: int) -> time:
        """Subtract minutes from a time."""
        total = self._time_to_minutes(t) - minutes
        return self._minutes_to_time(total, t.tzinfo)

    def _add_minutes(self, t: time, minutes: int) -> time:
        """Add minutes to a time."""
        total = self._time_to_minutes(t) + minutes
        return self._minutes_to_time(total, t.tzinfo)

    def _calculate_midpoint(self, t1: time, t2: time) -> time:
        """Calculate midpoint between two times."""
        m1 = self._time_to_minutes(t1)
        m2 = self._time_to_minutes(t2)
        mid = (m1 + m2) // 2
        return self._minutes_to_time(mid, t1.tzinfo)
