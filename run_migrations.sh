#!/bin/bash
# Script to apply earnings system migrations

# Database connection details
PGHOST="postgres"
PGPORT="5432"
PGDATABASE="gt360_dev"
PGUSER="gt360_dev"
export PGPASSWORD="gt360_dev_password"

echo "🚀 Starting earnings system migrations..."
echo "Database: $PGDATABASE@$PGHOST:$PGPORT"
echo ""

# Migration files in order
migrations=(
    "migrations/add_driver_pay_fields.sql"
    "migrations/create_driver_shifts_table.sql"
    "migrations/create_driver_expenses_table.sql"
    "migrations/create_driver_tax_information_table.sql"
    "migrations/create_form_1099_archive_table.sql"
)

# Run each migration
for migration in "${migrations[@]}"; do
    if [ ! -f "$migration" ]; then
        echo "❌ Migration file not found: $migration"
        continue
    fi

    echo "📝 Applying: $migration"

    if psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -f "$migration" > /dev/null 2>&1; then
        echo "✅ Successfully applied: $migration"
    else
        echo "❌ Error applying: $migration"
        echo "   Check the error above for details"
        exit 1
    fi
    echo ""
done

echo "🎉 All migrations completed successfully!"

# Unset password
unset PGPASSWORD
