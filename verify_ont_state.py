#!/usr/bin/env python3
"""
Verification script to check the actual state of filters and trips in ONT location.
This will help diagnose if Bug #2 is backend or frontend.
"""

import asyncio
import sys
from datetime import datetime, date
from uuid import UUID

# Add parent directory to path
sys.path.insert(0, '/home/backend/GT360')

from shared.db.db_config import engine, AsyncSession
from shared.db.schemas import Location, FilterStep, Trip
from psqlmodel import Select


async def find_ont_location():
    """Find ONT location ID."""
    async with AsyncSession(engine) as session:
        query = Select(Location).Where(Location.name == "ONT")
        location = await session.exec(query).first()

        if not location:
            # Try variations
            query = Select(Location).Where(Location.name.ilike("%ONT%"))
            locations = await session.exec(query).all()

            if locations:
                print("Found locations matching ONT:")
                for loc in locations:
                    print(f"  - {loc.name} ({loc.id})")
                return locations[0] if len(locations) == 1 else None

            return None

        return location


async def check_filter_steps(location_id: UUID):
    """Check filter steps for ONT location."""
    async with AsyncSession(engine) as session:
        # Get all filter steps (active and inactive)
        query = (
            Select(FilterStep)
            .Where(FilterStep.location_id == location_id)
            .OrderBy(FilterStep.pick_up_date.Desc(), FilterStep.step_order.Asc())
        )
        steps = await session.exec(query).all()

        if not steps:
            print("\n❌ No filter steps found for ONT location")
            return None

        print(f"\n📊 Filter Steps for ONT (Total: {len(steps)}):")
        print("=" * 100)

        # Group by date
        by_date = {}
        for step in steps:
            date_str = str(step.pick_up_date)
            if date_str not in by_date:
                by_date[date_str] = []
            by_date[date_str].append(step)

        # Show most recent dates
        recent_dates = sorted(by_date.keys(), reverse=True)[:5]

        for date_str in recent_dates:
            date_steps = by_date[date_str]
            active_count = sum(1 for s in date_steps if s.is_active)

            print(f"\n📅 Date: {date_str} (Active: {active_count}/{len(date_steps)})")
            print(f"{'Order':<7} {'Type':<10} {'Active':<8} {'Trips':<7} {'Created':<20} {'Step ID'}")
            print("-" * 100)

            for step in sorted(date_steps, key=lambda s: s.step_order):
                status = "✅ YES" if step.is_active else "❌ NO"
                created = step.created_at.strftime("%Y-%m-%d %H:%M:%S")
                print(f"{step.step_order:<7} {step.filter_type:<10} {status:<8} {step.trips_affected:<7} {created:<20} {str(step.id)[:8]}...")

        return recent_dates[0] if recent_dates else None


async def check_trip_states(location_id: UUID, pick_up_date: str):
    """Check actual trip filter states."""
    async with AsyncSession(engine) as session:
        date_obj = date.fromisoformat(pick_up_date)

        query = (
            Select(Trip)
            .Where(Trip.location_id == location_id)
            .Where(Trip.pick_up_date == date_obj)
            .Where(Trip.original_pick_up_time != None)  # Only filtered trips
            .OrderBy(Trip.pick_up_time.Asc())
        )
        trips = await session.exec(query).all()

        if not trips:
            print(f"\n❌ No filtered trips found for date {pick_up_date}")
            return

        print(f"\n🚗 Filtered Trips for {pick_up_date} (Total: {len(trips)}):")
        print("=" * 120)
        print(f"{'Flight':<8} {'Hotel':<25} {'Original':<10} {'Current':<10} {'Reduce':<8} {'Combine':<9} {'Expand':<8} {'Step ID'}")
        print("-" * 120)

        # Count filter combinations
        reduce_only = 0
        combine_only = 0
        expand_only = 0
        reduce_combine = 0
        reduce_expand = 0
        all_false = 0

        for trip in trips[:20]:  # Show first 20
            orig = str(trip.original_pick_up_time)[:5] if trip.original_pick_up_time else "N/A"
            curr = str(trip.pick_up_time)[:5] if trip.pick_up_time else "N/A"
            hotel = (trip.pick_up_location or "Unknown")[:25]
            reduce = "✅" if trip.reduce_applied else "❌"
            combine = "✅" if trip.combine_applied else "❌"
            expand = "✅" if trip.expand_applied else "❌"
            step_id = str(trip.current_step_id)[:8] + "..." if trip.current_step_id else "None"

            print(f"{trip.flight_number:<8} {hotel:<25} {orig:<10} {curr:<10} {reduce:<8} {combine:<9} {expand:<8} {step_id}")

            # Count combinations
            if trip.reduce_applied and trip.combine_applied:
                reduce_combine += 1
            elif trip.reduce_applied and trip.expand_applied:
                reduce_expand += 1
            elif trip.reduce_applied:
                reduce_only += 1
            elif trip.combine_applied:
                combine_only += 1
            elif trip.expand_applied:
                expand_only += 1
            else:
                all_false += 1

        if len(trips) > 20:
            print(f"\n... and {len(trips) - 20} more trips")

        print(f"\n📈 Filter Combination Stats:")
        print(f"  - Reduce only: {reduce_only}")
        print(f"  - Combine only: {combine_only}")
        print(f"  - Expand only: {expand_only}")
        print(f"  - Reduce + Combine: {reduce_combine}")
        print(f"  - Reduce + Expand: {reduce_expand}")
        print(f"  - All flags FALSE (should not happen!): {all_false}")

        # Diagnosis
        print(f"\n🔍 DIAGNOSIS:")
        if all_false > 0:
            print(f"  ⚠️  WARNING: {all_false} trips have original_pick_up_time but NO filter flags!")
            print(f"  This suggests a BACKEND BUG in the revert process.")
        elif reduce_only > 0 or combine_only > 0 or expand_only > 0:
            print(f"  ✅ Trip filter flags look CORRECT - some have single filters applied.")
            print(f"  If frontend shows NO filters, it's a FRONTEND bug.")
        elif reduce_combine > 0 or reduce_expand > 0:
            print(f"  ✅ Trip filter flags show MULTIPLE filters active.")
            print(f"  If frontend shows different state, it's a FRONTEND bug.")


async def main():
    print("🔍 Checking ONT Location Filter State...\n")

    # Find ONT location
    location = await find_ont_location()

    if not location:
        print("❌ Could not find ONT location in database")
        return

    print(f"✅ Found location: {location.name} (ID: {location.id})")
    print(f"   Timezone: {location.timezone}")

    # Check filter steps
    recent_date = await check_filter_steps(location.id)

    if recent_date:
        # Check trip states for most recent date
        await check_trip_states(location.id, recent_date)

    print("\n" + "=" * 120)
    print("✅ Verification complete!")
    print("\nNext steps:")
    print("1. Compare filter_steps.is_active with what frontend shows")
    print("2. Compare trip filter flags with frontend trip data")
    print("3. If database is correct but frontend is wrong → Frontend bug")
    print("4. If database is wrong → Backend bug")


if __name__ == "__main__":
    asyncio.run(main())
