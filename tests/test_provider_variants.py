"""Integration coverage for the reusable provider-adapter template."""

import hashlib
import hmac
import json


def _hmac_headers(payload: dict, secret: str) -> dict:
    raw = json.dumps(payload).encode("utf-8")
    return {
        "content-type": "application/json",
        "x-mock-signature": hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(),
    }


def test_mock_token_provider_variant(client):
    payload = {
        "transaction_id": "TOKEN-001", "amount": 2_000_000, "customer_id": "1",
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
        "transaction_id": "MAJOR-001", "amount": "20000.00", "customer_id": "1",
        "status": "success", "event_type": "payment", "metadata": {},
    }
    response = client.post(
        "/webhooks/payments/mock_major", content=json.dumps(payload),
        headers=_hmac_headers(payload, "mock-major-secret-for-testing"),
    )
    assert response.status_code == 200
    assert response.json()["reconciliation"]["gross_amount"] == "20000"
    assert client.get("/loans/1").json()["outstanding"] == 36_000


def test_core_banking_provider_template(client):
    payload = {
        "notification_id": "CORE-001", "account_id": "1", "amount": "20000.00",
        "currency": "NGN", "status": "posted", "event": "payment.posted", "metadata": {},
    }
    response = client.post(
        "/webhooks/payments/core_banking", content=json.dumps(payload),
        headers={"content-type": "application/json", "x-core-banking-token": "core-banking-token-for-testing"},
    )
    assert response.status_code == 200
    assert response.json()["event"]["status"] == "applied"
    assert client.get("/loans/1").json()["outstanding"] == 36_000
