#!/bin/bash
set -e

# Start cron in background (must run as root)
echo "Starting cron service..."
service cron start

# Start uvicorn as appuser
echo "Starting FastAPI application..."
exec python -c "import uvicorn; uvicorn.run('main:app', host='0.0.0.0', port=8000, proxy_headers=True, forwarded_allow_ips='127.0.0.1', ws_ping_interval=None, ws_ping_timeout=None)"
