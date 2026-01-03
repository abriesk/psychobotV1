#!/bin/bash
set -e

echo "🔄 Running database migrations..."
alembic upgrade head

echo "✅ Migrations complete. Starting application..."
exec python -m app.main
