"""
Database triggers for driver earnings system.
Sets up updated_at triggers for all earnings-related tables.
"""
from __future__ import annotations

from psqlmodel import AsyncSession


DRIVER_EARNINGS_TRIGGERS_SQL = r'''
-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION drivers.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for driver_shifts
DROP TRIGGER IF EXISTS update_driver_shifts_updated_at ON drivers.driver_shifts;
CREATE TRIGGER update_driver_shifts_updated_at
    BEFORE UPDATE ON drivers.driver_shifts
    FOR EACH ROW
    EXECUTE FUNCTION drivers.update_updated_at_column();

-- Trigger for driver_expenses
DROP TRIGGER IF EXISTS update_driver_expenses_updated_at ON drivers.driver_expenses;
CREATE TRIGGER update_driver_expenses_updated_at
    BEFORE UPDATE ON drivers.driver_expenses
    FOR EACH ROW
    EXECUTE FUNCTION drivers.update_updated_at_column();

-- Trigger for driver_tax_information
DROP TRIGGER IF EXISTS update_driver_tax_information_updated_at ON drivers.driver_tax_information;
CREATE TRIGGER update_driver_tax_information_updated_at
    BEFORE UPDATE ON drivers.driver_tax_information
    FOR EACH ROW
    EXECUTE FUNCTION drivers.update_updated_at_column();

-- Trigger for form_1099_archive
DROP TRIGGER IF EXISTS update_form_1099_archive_updated_at ON drivers.form_1099_archive;
CREATE TRIGGER update_form_1099_archive_updated_at
    BEFORE UPDATE ON drivers.form_1099_archive
    FOR EACH ROW
    EXECUTE FUNCTION drivers.update_updated_at_column();
'''


async def ensure_driver_earnings_triggers(session: AsyncSession) -> None:
    """
    Ensure all driver earnings triggers are set up.
    This is idempotent - can be run multiple times safely.
    """
    await session.exec(DRIVER_EARNINGS_TRIGGERS_SQL)
