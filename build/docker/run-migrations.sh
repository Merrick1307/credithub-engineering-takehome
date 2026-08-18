#!/bin/sh
set -eu

if [ "${RUN_MIGRATIONS:-1}" = "0" ]; then
    echo "RUN_MIGRATIONS=0; skipping database migrations."
    exit 0
fi

echo "Applying database migrations..."
exec python /usr/local/bin/run-migrations.py
