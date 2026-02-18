#!/usr/bin/env python3
"""
Script to apply earnings system migrations.
Runs all migration SQL files in order.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from shared.db.db_config import engine
from psqlmodel import AsyncSession


async def run_migrations():
    """Execute all earnings system migrations."""

    # Migration files in order
    migrations = [
        "migrations/add_driver_pay_fields.sql",
        "migrations/create_driver_shifts_table.sql",
        "migrations/create_driver_expenses_table.sql",
        "migrations/create_driver_tax_information_table.sql",
        "migrations/create_form_1099_archive_table.sql"
    ]

    print("🚀 Starting earnings system migrations...\n")

    await engine.startup_async()

    async with AsyncSession(engine) as session:
        try:
            for migration_file in migrations:
                file_path = project_root / migration_file

                if not file_path.exists():
                    print(f"❌ Migration file not found: {migration_file}")
                    continue

                print(f"📝 Applying: {migration_file}")

                # Read migration SQL
                with open(file_path, 'r') as f:
                    sql_content = f.read()

                # Execute migration
                await session.exec(sql_content)
                await session.commit()

                print(f"✅ Successfully applied: {migration_file}\n")

            print("🎉 All migrations completed successfully!")

        except Exception as e:
            print(f"\n❌ Error applying migrations: {str(e)}")
            raise

        finally:
            await engine.dispose_async()


if __name__ == "__main__":
    asyncio.run(run_migrations())
