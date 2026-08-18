"""Integration coverage for the reusable provider-adapter template."""

import hashlib
import hmac
import json

from conftest import ACTIVE_LOAN_ID


def _hmac_headers(payload: dict, secret: str) -> dict:
    raw = json.dumps(payload).encode("utf-8")
    return {
        "content-type": "application/json",
        "x-mock-signature": hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(),
    }


def test_mock_token_provider_variant(client):
    payload = {
        "transaction_id": "TOKEN-001", "amount": 2_000_000, "customer_id": ACTIVE_LOAN_ID,
        "status": "success", "event_type": "payment", "metadata": {},
    }
    response = client.post(
        "/webhooks/payments/mock_token", content=json.dumps(payload),
        headers={"content-type": "application/json", "x-mock-token": "mock-token-for-testing"},
    )
    assert response.status_code == 200
    assert response.json()["event"]["status"] == "applied"


def test_mock_major_unit_normalization_variant(client):
    payload = {
        "transaction_id": "MAJOR-001", "amount": "20000.00", "customer_id": ACTIVE_LOAN_ID,
        "status": "success", "event_type": "payment", "metadata": {},
    }
    response = client.post(
        "/webhooks/payments/mock_major", content=json.dumps(payload),
        headers=_hmac_headers(payload, "mock-major-secret-for-testing"),
    )
    assert response.status_code == 200
    assert response.json()["reconciliation"]["gross_amount"] == "20000"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == 36_000


def test_core_banking_provider_template(client):
    payload = {
        "notification_id": "CORE-001", "account_id": ACTIVE_LOAN_ID, "amount": "20000.00",
        "currency": "NGN", "status": "posted", "event": "payment.posted", "metadata": {},
    }
    response = client.post(
        "/webhooks/payments/core_banking", content=json.dumps(payload),
        headers={"content-type": "application/json", "x-core-banking-token": "core-banking-token-for-testing"},
    )
    assert response.status_code == 200
    assert response.json()["event"]["status"] == "applied"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == 36_000

def test_non_final_provider_status_does_not_block_later_success(client):
    payload = {
        "transaction_id": "PENDING-THEN-SUCCESS-001",
        "amount": 2_000_000,
        "customer_id": ACTIVE_LOAN_ID,
        "status": "pending",
        "timestamp": "2026-08-18T10:00:00Z",
        "event_type": "payment",
        "metadata": {},
    }

    pending = client.post(
        "/webhooks/payments/mock",
        content=json.dumps(payload),
        headers=_hmac_headers(payload, "mock-secret-key-for-testing"),
    )
    assert pending.status_code == 200
    assert pending.json()["event"]["status"] == "rejected"
    assert pending.json()["event"]["id"] is None
    assert pending.json()["reconciliation"]["reason"] == "provider_status_not_final_success"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == 56_000

    payload["status"] = "success"
    succeeded = client.post(
        "/webhooks/payments/mock",
        content=json.dumps(payload),
        headers=_hmac_headers(payload, "mock-secret-key-for-testing"),
    )
    assert succeeded.status_code == 200
    assert succeeded.json()["event"]["status"] == "applied"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == 36_000

