-- Migration: Add driver_location_sharing to organizations
-- Date: 2026-02-21
-- Description: Boolean toggle for driver-to-driver location visibility (per organization)

ALTER TABLE entities.organizations
ADD COLUMN IF NOT EXISTS driver_location_sharing BOOLEAN NOT NULL DEFAULT FALSE;
