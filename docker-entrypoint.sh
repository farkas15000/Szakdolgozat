#!/usr/bin/env bash
set -e

# Wait for Postgres
echo "Waiting for Postgres at $DB_HOST:$DB_PORT..."

until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$POSTGRES_USER"; do
  sleep 1
done

echo "Postgres is up!"

# Run Alembic migrations
echo "Running Alembic migrations..."
cd ./src/backend
alembic upgrade head
cd ../..

# Start the application
echo "Starting app..."
exec "$@"
