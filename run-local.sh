#!/usr/bin/env bash
# One-command non-Docker development run: migrate, seed, start the API,
# refund orchestrator, durable workers, and the Vite frontend.
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

CORE_BANKING_LOOPBACK_URL="http://127.0.0.1:8137/webhooks/payments/core_banking" \
  .venv/bin/uvicorn app.workers.overpayment_refund_runner:app --host 127.0.0.1 --port 8138 &
REFUND_PID=$!

OUTBOX_EVENT_URLS='{"overpayment.refund.requested":"http://127.0.0.1:8138/webhooks/outbox/overpayment-refunds"}' \
  .venv/bin/python -m app.workers.outbox_publisher &
OUTBOX_PID=$!

.venv/bin/python -m app.workers.lookup_retry_runner &
LOOKUP_PID=$!

trap 'kill $BACKEND_PID $REFUND_PID $OUTBOX_PID $LOOKUP_PID 2>/dev/null || true' EXIT

# --- frontend ---
cd frontend
npm install
npm run dev
