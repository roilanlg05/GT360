#!/bin/bash
# Setup cron job for auto-closing shifts
# This script adds a cron job that runs every 30 minutes

# Get the absolute path to the project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_PATH="$(which python3)"

# Cron job command
CRON_CMD="*/30 * * * * cd $PROJECT_DIR && $PYTHON_PATH -m shared.utils.auto_close_shifts_job >> /var/log/auto_close_shifts.log 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "auto_close_shifts_job"; then
    echo "Cron job already exists"
    exit 0
fi

# Add cron job
(crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -

echo "Cron job added successfully:"
echo "$CRON_CMD"
echo ""
echo "The job will run every 30 minutes to auto-close stale shifts."
echo "Logs will be written to /var/log/auto_close_shifts.log"
