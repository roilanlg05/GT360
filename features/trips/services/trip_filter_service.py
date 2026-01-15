"""
Trip Filter Service

Implements the filtering logic for Outbound trips with status SCHEDULED:
- Reduce: Subtract fixed minutes from pickup_time
- Combine: Move pairs of trips to their midpoint
- Expand: Separate pairs of trips while respecting No-Collision Rule

Eligibility criteria:
- trip_type = OUTBOUND only
- status = SCHEDULED only
- Filtered by location_id and airline

Rules:
- Rule A: A modified trip cannot be modified again in the same run
- Rule B: No-Collision Rule - Expand must not create gaps that fall into Combine range
- All results are rounded to multiples of 5 minutes
"""

from __future__ import annotations

import logging
from datetime import time, datetime
from typing import Optional
from uuid import UUID, uuid4

from psqlmodel import AsyncSession, Select

from shared.db.schemas import Trip, TripType, TripStatus, FilterType
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
)

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
    - Execute filters in order: Reduce → Combine → Expand
    - Respect Rule A: a modified trip is not modified again
    - Respect Rule B: No-Collision Rule for Expand
    - Round results to multiples of 5 minutes
    - Generate detailed logs
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.modified_trip_ids: set[UUID] = set()  # Rule A tracking
        self.changes: list[TripChange] = []
        self.exclusions: list[FilterExclusion] = []
        self.log: list[dict] = []

    async def preview(
        self,
        location_id: UUID,
        airline: str,
        config: FilterRequest,
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

        # Get eligible trips
        trips = await self._get_eligible_trips(location_id, airline)
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

        return FilterPreviewResult(
            location_id=location_id,
            airline=airline,
            changes=self.changes,
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

        # Get eligible trips
        trips = await self._get_eligible_trips(location_id, airline)

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

                self.log.append({
                    "trip_id": str(trip.id),
                    "action": "modified",
                    "filter": change.filter_applied,
                    "original_time": str(change.original_time),
                    "new_time": str(change.new_time),
                    "hotel": change.hotel_name,
                    "airline": trip.airline,
                })

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
                reverted_count += 1

        await self.session.commit()

        return FilterRevertResult(
            trips_reverted=reverted_count,
            batch_ids_reverted=list(batch_ids_reverted),
        )

    # =========================================================================
    # Private Methods
    # =========================================================================

    def _reset_state(self):
        """Reset internal state for new operation."""
        self.modified_trip_ids.clear()
        self.changes.clear()
        self.exclusions.clear()
        self.log.clear()

    async def _get_eligible_trips(
        self,
        location_id: UUID,
        airline: str,
    ) -> list[Trip]:
        """
        Get trips eligible for filtering.

        Criteria:
        - trip_type = OUTBOUND only
        - status = SCHEDULED only
        - Matches location_id and airline
        """
        query = (
            Select(Trip)
            .Where(Trip.location_id == location_id)
            .Where(Trip.airline == airline)
            .Where(Trip.trip_type == TripType.OUTBOUND)
            .Where(Trip.status == TripStatus.SCHEDULED)
        )

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
        Apply Reduce filter: subtract fixed minutes from pickup_time.
        """
        for trip in trips:
            if trip.id in self.modified_trip_ids:
                continue

            original_time = trip.pick_up_time
            new_time = self._subtract_minutes(original_time, config.minutes_to_reduce)
            new_time = self._round_to_5_minutes(new_time)

            self._record_change(trip, original_time, new_time, FilterType.REDUCE)
            self.modified_trip_ids.add(trip.id)

    def _apply_combine(self, trips: list[Trip], config: CombineFilterConfig):
        """
        Apply Combine filter: move pairs to their midpoint.
        """
        # Sort by pickup time
        sorted_trips = sorted(trips, key=lambda t: self._time_to_minutes(t.pick_up_time))

        i = 0
        while i < len(sorted_trips) - 1:
            trip_a = sorted_trips[i]
            trip_b = sorted_trips[i + 1]

            # Skip if either already modified (Rule A)
            if trip_a.id in self.modified_trip_ids or trip_b.id in self.modified_trip_ids:
                i += 1
                continue

            gap = self._minutes_between(trip_a.pick_up_time, trip_b.pick_up_time)

            if config.min_gap <= gap <= config.max_gap:
                midpoint = self._calculate_midpoint(trip_a.pick_up_time, trip_b.pick_up_time)
                midpoint = self._round_to_5_minutes(midpoint)

                self._record_change(trip_a, trip_a.pick_up_time, midpoint, FilterType.COMBINE)
                self._record_change(trip_b, trip_b.pick_up_time, midpoint, FilterType.COMBINE)

                self.modified_trip_ids.add(trip_a.id)
                self.modified_trip_ids.add(trip_b.id)

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
        """
        # Sort by pickup time
        sorted_trips = sorted(trips, key=lambda t: self._time_to_minutes(t.pick_up_time))

        for i in range(len(sorted_trips) - 1):
            trip_a = sorted_trips[i]
            trip_b = sorted_trips[i + 1]

            # Skip if either already modified (Rule A)
            if trip_a.id in self.modified_trip_ids or trip_b.id in self.modified_trip_ids:
                continue

            gap = self._minutes_between(trip_a.pick_up_time, trip_b.pick_up_time)

            if config.min_gap <= gap <= config.max_gap:
                # Simulate expansion
                new_time_a, new_time_b = self._simulate_expand(
                    trip_a.pick_up_time,
                    trip_b.pick_up_time,
                    config.max_shift,
                )

                # No-Collision Rule (Rule B)
                if combine_config and combine_config.enabled:
                    collision = False

                    # Check gap with previous neighbor (i-1)
                    if i > 0:
                        prev_trip = sorted_trips[i - 1]
                        # Use the potentially modified time if it was changed
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

                    # Check gap with next neighbor (i+2)
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

                # Apply expansion
                self._record_change(trip_a, trip_a.pick_up_time, new_time_a, FilterType.EXPAND)
                self._record_change(trip_b, trip_b.pick_up_time, new_time_b, FilterType.EXPAND)

                self.modified_trip_ids.add(trip_a.id)
                self.modified_trip_ids.add(trip_b.id)

    def _get_effective_time(self, trip: Trip) -> time:
        """
        Get the effective pickup time for a trip.
        If it was modified in this run, return the new time.
        """
        for change in self.changes:
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

        return self._round_to_5_minutes(new_time_a), self._round_to_5_minutes(new_time_b)

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
