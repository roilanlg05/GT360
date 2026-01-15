-- Migration: Add batch insert mode detection to prevent 1000s of WebSocket events
-- Date: 2026-01-15
-- Purpose: Modify trigger to detect batch mode and skip individual notifications during bulk uploads

-- Step 1: Create helper function to detect batch mode
CREATE OR REPLACE FUNCTION is_batch_insert_mode()
RETURNS boolean AS $$
BEGIN
    -- Check if the session variable app.batch_insert_mode is set to 'true'
    -- Returns false by default if the variable is not set
    RETURN current_setting('app.batch_insert_mode', true) = 'true';
EXCEPTION
    WHEN OTHERS THEN
        -- If anything fails, default to false (normal mode)
        RETURN false;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

COMMENT ON FUNCTION is_batch_insert_mode() IS
'Helper function to detect if we are in batch insert mode. Used by triggers to skip individual notifications during bulk operations.';

-- Step 2: Modify the insert trigger function to respect batch mode
CREATE OR REPLACE FUNCTION public.__sub_trips_insert_17b502_fn()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    -- ONLY notify if NOT in batch mode
    -- During bulk uploads, batch_insert_mode will be 'true' and this will be skipped
    -- After commit, batch_insert_mode resets and a single batch event is sent via Redis
    IF NOT is_batch_insert_mode() THEN
        PERFORM pg_notify(
            '__sub_0c38de5ce14948d68861226bbd17b502',
            json_build_object(
                'event', lower(TG_OP),
                'schema', TG_TABLE_SCHEMA,
                'table', TG_TABLE_NAME,
                'pk_name', 'id',
                'old', CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN row_to_json(OLD) END,
                'new', CASE WHEN TG_OP IN ('UPDATE','INSERT') THEN row_to_json(NEW) END
            )::text
        );
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$function$;

COMMENT ON FUNCTION public.__sub_trips_insert_17b502_fn() IS
'Trigger function for trips table insert events. Respects batch_insert_mode to avoid sending 1000s of individual notifications during bulk uploads.';

-- Optional: Also modify UPDATE and DELETE triggers for consistency
-- (though the main issue is with INSERT during uploads)

CREATE OR REPLACE FUNCTION public.__sub_trips_update_17b502_fn()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    -- Respect batch mode for UPDATE operations too
    IF NOT is_batch_insert_mode() THEN
        PERFORM pg_notify(
            '__sub_0c38de5ce14948d68861226bbd17b502',
            json_build_object(
                'event', lower(TG_OP),
                'schema', TG_TABLE_SCHEMA,
                'table', TG_TABLE_NAME,
                'pk_name', 'id',
                'old', CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN row_to_json(OLD) END,
                'new', CASE WHEN TG_OP IN ('UPDATE','INSERT') THEN row_to_json(NEW) END
            )::text
        );
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$function$;

CREATE OR REPLACE FUNCTION public.__sub_trips_delete_17b502_fn()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
    -- Respect batch mode for DELETE operations too
    IF NOT is_batch_insert_mode() THEN
        PERFORM pg_notify(
            '__sub_0c38de5ce14948d68861226bbd17b502',
            json_build_object(
                'event', lower(TG_OP),
                'schema', TG_TABLE_SCHEMA,
                'table', TG_TABLE_NAME,
                'pk_name', 'id',
                'old', CASE WHEN TG_OP IN ('UPDATE','DELETE') THEN row_to_json(OLD) END,
                'new', CASE WHEN TG_OP IN ('UPDATE','INSERT') THEN row_to_json(NEW) END
            )::text
        );
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$function$;
