"""Webhook consumer that orchestrates core-banking overpayment refunds.

It deliberately does not poll or claim ``outbox_events``. The outbox publisher
is the sole dispatcher and retries delivery to this process when it is down.
"""

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Response
from pydantic import BaseModel

from .work_queue import REFUND_COMMAND


class OutboxWebhookEvent(BaseModel):
    id: str
    type: str
    payload: dict
    correlation_id: str


class CoreBankingRefundLoopback:
    """Development adapter that simulates the provider's signed callback."""

    def __init__(self, url: str | None = None, token: str | None = None):
        self.url = url or os.getenv("CORE_BANKING_LOOPBACK_URL", "http://127.0.0.1:8137/webhooks/payments/core_banking")
        self.token = token or os.getenv("CORE_BANKING_WEBHOOK_TOKEN", "core-banking-token-for-testing")

    def request_refund(self, event_id: str, command: dict) -> None:
        if command.get("provider") != "core_banking":
            raise ValueError("refund command is not eligible for core-banking loopback")
        payload = {
            "notification_id": f"overpayment-refund-{event_id}",
            "account_id": command["account_id"],
            "amount": command["amount"],
            "currency": command.get("currency", "NGN"),
            "status": "posted",
            "event": "overpayment.refunded",
            "original_notification_id": command["original_notification_id"],
            "occurred_at": command.get("occurred_at") or datetime.now(timezone.utc).isoformat(),
            "metadata": {"refund_command_id": event_id, "overpayment_id": command["overpayment_id"]},
        }
        raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        response = httpx.post(
            self.url,
            content=raw_body,
            headers={
                "x-core-banking-signature": hmac.new(self.token.encode(), raw_body, hashlib.sha256).hexdigest(),
                "content-type": "application/json",
            },
            timeout=10,
        )
        response.raise_for_status()
        outcome = response.json()
        if outcome.get("event", {}).get("status") != "applied":
            raise RuntimeError(outcome.get("reconciliation", {}).get("reason", "refund rejected"))


class OverpaymentRefundRunner:
    """Validate a delivered event and dispatch only the refund command."""

    def __init__(self, adapter=None):
        self.adapter = adapter or CoreBankingRefundLoopback()

    def orchestrate(self, event: OutboxWebhookEvent) -> bool:
        if event.type != REFUND_COMMAND:
            return False
        self.adapter.request_refund(event.id, event.payload)
        return True


app = FastAPI(title="CreditHub overpayment refund orchestrator")
app.state.refund_runner = OverpaymentRefundRunner()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhooks/outbox/overpayment-refunds")
def receive_overpayment_refund(event: OutboxWebhookEvent):
    """Accept only the durable refund-command event; other events are ignored."""
    if not app.state.refund_runner.orchestrate(event):
        return Response(status_code=204)
    return {"status": "orchestrated"}
