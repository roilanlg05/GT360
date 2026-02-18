#!/bin/bash
set -e

# Start cron in background (must run as root)
echo "Starting cron service..."
service cron start

# Start uvicorn as appuser
echo "Starting FastAPI application..."
exec uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "127.0.0.1"
