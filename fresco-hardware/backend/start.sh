#!/bin/bash
set -e

echo "Running migrations..."
alembic upgrade head

echo "Starting uvicorn on port ${PORT:-8000}..."
exec uvicorn app.api.routes:app --host 0.0.0.0 --port "${PORT:-8000}"
