import hashlib
import hmac
import json

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

import httpx

from fastapi import HTTPException, Request, APIRouter
from pydantic import BaseModel, Field

router = APIRouter()

class SimulateCoreBankingWebhookRequest(BaseModel):
    account_id: str
    amount: Decimal

    event: Literal[
        "payment.posted",
        "payment.reversed",
        "overpayment.refunded",
    ] = "payment.posted"

    status: str = "posted"

    notification_id: str | None = None
    original_notification_id: str | None = None

    currency: str = "NGN"
    occurred_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


@router.post("/dev/simulate/core-banking", status_code=200)
async def simulate_core_banking_webhook(
    body: SimulateCoreBankingWebhookRequest,
    request: Request,
):
    """
    Build a provider-native core-banking callback, sign it using the
    configured core-banking secret, and send it through the real
    /webhooks/payments/core_banking endpoint.

    Intended for local/dev testing from Postman.
    """

    try:
        provider_registry = request.app.state.provider_registry
        config = provider_registry.get_provider_config("core_banking")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    secret = config.get("secret_key")

    if not secret:
        raise HTTPException(
            status_code=500,
            detail="core_banking has no secret_key configured",
        )

    notification_id = (
        body.notification_id
        or f"CORE-SIM-{uuid4().hex[:12].upper()}"
    )

    occurred_at = (
        body.occurred_at
        or datetime.now(timezone.utc)
    )

    payload = {
        "notification_id": notification_id,
        "account_id": body.account_id,
        "amount": str(body.amount),
        "status": body.status,
        "event": body.event,
        "currency": body.currency,
        "occurred_at": occurred_at.isoformat(),
        "metadata": body.metadata,
    }

    if body.original_notification_id:
        payload["original_notification_id"] = (
            body.original_notification_id
        )

    # Serialize once.
    #
    # The exact bytes signed here MUST be the exact bytes sent to
    # /webhooks/payments/core_banking.
    raw_body = json.dumps(
        payload,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    signature = hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    webhook_headers = {
        "Content-Type": "application/json",
        "X-Core-Banking-Signature": signature,
    }

    # Send the synthetic callback through the ACTUAL FastAPI endpoint.
    # No external network call is necessary.
    transport = httpx.ASGITransport(app=request.app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://internal", # a dummy placeholder to enable httpx construct a url
    ) as client:
        response = await client.post(
            "/webhooks/payments/core_banking",
            content=raw_body,
            headers=webhook_headers,
        )

    try:
        webhook_result = response.json()
    except Exception:
        webhook_result = response.text

    return {
        "simulation": {
            "provider": "core_banking",
            "notification_id": notification_id,
            "forwarded_to": "/webhooks/payments/core_banking",
        },
        "generated_webhook": {
            "headers": {
                "Content-Type": "application/json",
                "X-Core-Banking-Signature": signature,
            },
            "body": payload,
        },
        "webhook_response": {
            "status_code": response.status_code,
            "body": webhook_result,
        },
    }