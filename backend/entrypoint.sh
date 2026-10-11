#!/bin/sh
set -e

echo "[STARTUP] Applying database migrations (Alembic upgrade head)..."
alembic upgrade head

echo "[STARTUP] Launching Hospital Automation Platform (Uvicorn)..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
