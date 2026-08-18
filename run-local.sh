#!/usr/bin/env bash
# One-command non-Docker deploy. It uses the already configured DATABASE_URL
# (SQLite by default), applies migrations, seeds, then starts API and workers.
set -euo pipefail
cd "$(dirname "$0")"

# --- backend ---
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/python -m app.scripts.seed
.venv/bin/uvicorn app.main:app --port 8137 &
BACKEND_PID=$!
.venv/bin/python -m app.workers.outbox_publisher &
OUTBOX_PID=$!
.venv/bin/python -m app.workers.overpayment_refund_runner &
REFUND_PID=$!
.venv/bin/python -m app.workers.lookup_retry_runner &
LOOKUP_PID=$!
trap 'kill $BACKEND_PID $OUTBOX_PID $REFUND_PID $LOOKUP_PID 2>/dev/null || true' EXIT

# --- frontend ---
cd frontend
npm install
npm run dev
