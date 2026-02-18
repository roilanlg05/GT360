"""
Auto-close shifts job - Background task to auto-close stale shifts.
This job should run every 30 minutes via cron or scheduler.

Usage:
    python -m shared.utils.auto_close_shifts_job
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from shared.settings import settings
from features.drivers.services.shift_service import auto_close_stale_shifts


# Database setup
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def run_auto_close_job():
    """
    Main job function to auto-close stale shifts.
    """
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting auto-close shifts job...")

    async with AsyncSessionLocal() as session:
        try:
            # Auto-close shifts active for more than 6 hours
            auto_closed_shifts = await auto_close_stale_shifts(
                session,
                hours_threshold=6
            )

            if auto_closed_shifts:
                print(f"  ✓ Auto-closed {len(auto_closed_shifts)} shifts:")
                for shift in auto_closed_shifts:
                    print(f"    - Shift {shift.id} (Driver: {shift.driver_id})")
                    print(f"      Started: {shift.started_at.isoformat()}")
                    print(f"      Closed at: {shift.ended_at.isoformat()}")

                    # TODO: Send notifications
                    # await notify_driver(shift.driver_id, "Your shift was auto-closed")
                    # await notify_managers("New shift pending review", shift.id)

            else:
                print("  ✓ No stale shifts found")

            print(f"[{datetime.now(timezone.utc).isoformat()}] Job completed successfully\n")

        except Exception as e:
            print(f"  ✗ Error running auto-close job: {str(e)}")
            print(f"[{datetime.now(timezone.utc).isoformat()}] Job failed\n")
            raise


async def main():
    """Entry point for the job."""
    try:
        await run_auto_close_job()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
