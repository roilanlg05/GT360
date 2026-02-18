from __future__ import annotations

from psqlmodel import AsyncSession


ARCHIVE_TRIP_ON_DROPOFF_SQL = r'''-- Ensure trips_history has same columns as trips (idempotent)
ALTER TABLE trips.trips_history
    ADD COLUMN IF NOT EXISTS trip_type TEXT,
    ADD COLUMN IF NOT EXISTS original_pick_up_time TIME,
    ADD COLUMN IF NOT EXISTS reduce_applied BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS combine_applied BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS expand_applied BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS filtered_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS current_step_id UUID,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'scheduled';

-- Make riders nullable to match trips
ALTER TABLE trips.trips_history
    ALTER COLUMN riders DROP NOT NULL;

-- Ensure FK exists for current_step_id (matches trips.trips)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_trips_history_current_step_id'
          AND table_schema = 'trips'
          AND table_name = 'trips_history'
    ) THEN
        ALTER TABLE trips.trips_history
            ADD CONSTRAINT fk_trips_history_current_step_id
            FOREIGN KEY (current_step_id)
            REFERENCES trips.filter_steps(id)
            ON DELETE SET NULL;
    END IF;
END $$;

-- Create/replace archive trigger function
CREATE OR REPLACE FUNCTION trips.archive_trip_on_dropoff_fn()
RETURNS trigger AS $$
BEGIN
    -- Only archive on NULL -> NOT NULL transition
    IF (OLD.dropped_off_at IS NULL AND NEW.dropped_off_at IS NOT NULL)
       OR (OLD.status IS DISTINCT FROM NEW.status AND NEW.status = 'canceled') THEN
        INSERT INTO trips.trips_history (
            id,
            assigned_driver,
            location_id,
            trip_hash,
            pick_up_date,
            pick_up_time,
            pick_up_location,
            drop_off_location,
            airline,
            flight_number,
            trip_type,
            riders,
            started_at,
            picked_up_at,
            dropped_off_at,
            arrived_pickup_at,
            arrived_dropoff_at,
            created_at,
            updated_at,
            original_pick_up_time,
            reduce_applied,
            combine_applied,
            expand_applied,
            filtered_at,
            current_step_id,
            status
        ) VALUES (
            NEW.id,
            NEW.assigned_driver,
            NEW.location_id,
            NEW.trip_hash,
            NEW.pick_up_date,
            NEW.pick_up_time,
            NEW.pick_up_location,
            NEW.drop_off_location,
            NEW.airline,
            NEW.flight_number,
            NEW.trip_type,
            NEW.riders,
            NEW.started_at,
            NEW.picked_up_at,
            NEW.dropped_off_at,
            NEW.arrived_pickup_at,
            NEW.arrived_dropoff_at,
            NEW.created_at,
            NEW.updated_at,
            NEW.original_pick_up_time,
            COALESCE(NEW.reduce_applied, FALSE),
            COALESCE(NEW.combine_applied, FALSE),
            COALESCE(NEW.expand_applied, FALSE),
            NEW.filtered_at,
            NEW.current_step_id,
            COALESCE(NEW.status, 'scheduled')
        )
        ON CONFLICT (id) DO NOTHING;

        DELETE FROM trips.trips WHERE id = NEW.id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger (idempotent)
DROP TRIGGER IF EXISTS trips_archive_on_dropoff ON trips.trips;
CREATE TRIGGER trips_archive_on_dropoff
AFTER UPDATE OF dropped_off_at, status ON trips.trips
FOR EACH ROW
WHEN ((OLD.dropped_off_at IS NULL AND NEW.dropped_off_at IS NOT NULL)
   OR (OLD.status IS DISTINCT FROM NEW.status AND NEW.status = 'canceled'))
EXECUTE FUNCTION trips.archive_trip_on_dropoff_fn();
'''


async def ensure_trips_archive_trigger(session: AsyncSession) -> None:
    # Execute as one batch so it's idempotent.
    await session.exec(ARCHIVE_TRIP_ON_DROPOFF_SQL)
