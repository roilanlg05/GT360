-- Migration: Create driver_tax_information table
-- Date: 2026-02-16
-- Description: Creates table to store W-9 tax information for 1099 generation

-- Create driver_tax_information table
CREATE TABLE IF NOT EXISTS drivers.driver_tax_information (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id UUID NOT NULL UNIQUE REFERENCES entities.drivers(id) ON DELETE CASCADE,

    -- TIN (Taxpayer Identification Number)
    -- NOTE: TIN should be encrypted at application level before storing
    tin_type VARCHAR(10) NOT NULL,
    -- Values: 'SSN', 'EIN'

    tin VARCHAR(20) NOT NULL,

    -- Legal name for 1099
    legal_first_name VARCHAR(100) NOT NULL,
    legal_middle_name VARCHAR(100),
    legal_last_name VARCHAR(100) NOT NULL,

    -- Address for 1099
    address_street VARCHAR(255) NOT NULL,
    address_city VARCHAR(100) NOT NULL,
    address_state VARCHAR(2) NOT NULL,
    address_zip VARCHAR(10) NOT NULL,
    address_country VARCHAR(2) DEFAULT 'US' NOT NULL,

    -- W-9 document
    w9_submitted BOOLEAN DEFAULT FALSE NOT NULL,
    w9_submitted_at TIMESTAMPTZ,
    w9_document_url TEXT,

    -- Backup withholding
    backup_withholding_rate DECIMAL(5, 2) DEFAULT 0.00 NOT NULL,

    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,

    -- Constraints
    CONSTRAINT valid_tin_type CHECK (tin_type IN ('SSN', 'EIN')),
    CONSTRAINT valid_state CHECK (LENGTH(address_state) = 2)
);

-- Create indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_tax_info_driver
ON drivers.driver_tax_information(driver_id);

-- Add comments
COMMENT ON TABLE drivers.driver_tax_information IS 'Driver W-9 tax information for 1099 reporting';
COMMENT ON COLUMN drivers.driver_tax_information.tin IS 'Encrypted TIN (SSN or EIN)';
COMMENT ON COLUMN drivers.driver_tax_information.tin_type IS 'Type of TIN: SSN or EIN';
COMMENT ON COLUMN drivers.driver_tax_information.w9_submitted IS 'Whether driver has submitted W-9 form';

-- Create updated_at trigger
CREATE OR REPLACE FUNCTION drivers.update_tax_info_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_tax_info_timestamp
    BEFORE UPDATE ON drivers.driver_tax_information
    FOR EACH ROW
    EXECUTE FUNCTION drivers.update_tax_info_updated_at();

-- Security: Add row-level security to prevent unauthorized access
ALTER TABLE drivers.driver_tax_information ENABLE ROW LEVEL SECURITY;

-- Grant necessary permissions
GRANT SELECT, INSERT, UPDATE ON drivers.driver_tax_information TO authenticated;
