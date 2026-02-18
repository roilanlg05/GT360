-- Migration: Create form_1099_archive table
-- Date: 2026-02-16
-- Description: Creates table to archive generated 1099 forms

-- Create form_1099_archive table
CREATE TABLE IF NOT EXISTS drivers.form_1099_archive (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL REFERENCES entities.drivers(id) ON DELETE CASCADE,
    tax_year INT NOT NULL,

    -- Form data
    form_type VARCHAR(20) DEFAULT '1099-NEC' NOT NULL,
    box_1_amount DECIMAL(10, 2) NOT NULL,
    box_4_federal_withholding DECIMAL(10, 2) DEFAULT 0.00 NOT NULL,

    -- PDF document
    pdf_url TEXT,
    pdf_generated_at TIMESTAMPTZ,

    -- IRS submission
    submitted_to_irs BOOLEAN DEFAULT FALSE NOT NULL,
    submitted_at TIMESTAMPTZ,
    confirmation_number VARCHAR(100),

    -- Driver delivery
    sent_to_driver BOOLEAN DEFAULT FALSE NOT NULL,
    sent_to_driver_at TIMESTAMPTZ,
    delivery_method VARCHAR(20),
    -- Values: 'email', 'mail', 'portal'

    -- Metadata
    generated_by UUID REFERENCES entities.users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Constraints
    CONSTRAINT unique_driver_year UNIQUE(driver_id, tax_year),
    CONSTRAINT valid_tax_year CHECK (tax_year >= 2020 AND tax_year <= 2100)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_1099_archive_driver_year
ON drivers.form_1099_archive(driver_id, tax_year DESC);

CREATE INDEX IF NOT EXISTS idx_1099_archive_year
ON drivers.form_1099_archive(tax_year DESC);

CREATE INDEX IF NOT EXISTS idx_1099_archive_submission_status
ON drivers.form_1099_archive(submitted_to_irs, tax_year)
WHERE NOT submitted_to_irs;

-- Add comments
COMMENT ON TABLE drivers.form_1099_archive IS 'Archive of generated 1099-NEC forms';
COMMENT ON COLUMN drivers.form_1099_archive.box_1_amount IS 'Nonemployee compensation (gross earnings only)';
COMMENT ON COLUMN drivers.form_1099_archive.box_4_federal_withholding IS 'Federal income tax withheld';
COMMENT ON COLUMN drivers.form_1099_archive.submitted_to_irs IS 'Whether form has been submitted to IRS';
COMMENT ON COLUMN drivers.form_1099_archive.sent_to_driver IS 'Whether copy has been delivered to driver';
