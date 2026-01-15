-- Migration: Add batch insert mode detection to prevent 1000s of WebSocket events
-- Date: 2026-01-15
-- Purpose: Modify trigger to detect batch mode and skip individual notifications

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

-- Step 2: Get current trigger function definition to understand the structure
-- (We'll need to modify __sub_trips_insert_17b502_fn)

-- Step 3: Create new version of trigger function that respects batch mode
-- NOTE: This is a template - the actual function may have different structure
-- You need to inspect the current function and add the batch mode check

-- Example of how the trigger function should be modified:
-- CREATE OR REPLACE FUNCTION public.__sub_trips_insert_17b502_fn()
-- RETURNS trigger
-- LANGUAGE plpgsql
-- AS $function$
-- BEGIN
--     -- ONLY notify if NOT in batch mode
--     IF NOT is_batch_insert_mode() THEN
--         PERFORM pg_notify('__sub_trips_insert_17b502', json_build_object(...)::text);
--     END IF;
--
--     RETURN NEW;
-- END;
-- $function$;

-- To apply this migration:
-- 1. First, get the current trigger function definition:
--    \df+ public.__sub_trips_insert_17b502_fn
-- 2. Copy the function definition
-- 3. Add the IF NOT is_batch_insert_mode() check
-- 4. Run CREATE OR REPLACE FUNCTION with the modified definition

COMMENT ON FUNCTION is_batch_insert_mode() IS
'Helper function to detect if we are in batch insert mode. Used by triggers to skip individual notifications during bulk operations.';
