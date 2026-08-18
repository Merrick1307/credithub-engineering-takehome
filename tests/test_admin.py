"""Admin reconciliation API coverage."""

import json

from app.adapters.persistence.db import SessionLocal
from app.adapters.persistence.sqlalchemy_backend.models import ProviderLookupRetry
from conftest import ACTIVE_LOAN_ID, CLOSED_LOAN_ID


ADMIN = {"X-Admin-Token": "dev-admin-secret"}
WEBHOOK = {"X-Webhook-Token": "dev-webhook-secret"}


def test_admin_endpoints_require_staff_token(client):
    assert client.get("/admin/reconciliation/summary").status_code == 401


def test_admin_summary_issues_events_and_detail(client):
    client.post("/webhooks/payments", json={"external_ref": "ADMIN-PAID", "loan_id": ACTIVE_LOAN_ID, "amount": 20_000}, headers=WEBHOOK)
    client.post("/webhooks/payments", json={"external_ref": "ADMIN-CLOSED", "loan_id": CLOSED_LOAN_ID, "amount": 100}, headers=WEBHOOK)

    summary = client.get("/admin/reconciliation/summary", headers=ADMIN)
    assert summary.status_code == 200
    assert summary.json()["counts"]["applied"] == 1
    assert summary.json()["counts"]["rejected"] == 1
    assert summary.json()["amounts"]["applied"] == "20000.00"

    issues = client.get("/admin/reconciliation/issues", headers=ADMIN).json()["items"]
    assert issues[0]["reason"] == "closed_loan_payment"

    events = client.get("/admin/reconciliation/events?provider=paystack", headers=ADMIN).json()["items"]
    assert len(events) == 2
    detail = client.get(f"/admin/reconciliation/events/{events[0]['id']}", headers=ADMIN)
    assert detail.status_code == 200
    assert "ledger" in detail.json()


def test_admin_can_trigger_a_persisted_lookup_retry(client):
    payload = {
        "event_kind": "transaction.credit", "event_reference": "RETRY-001",
        "original_payment_reference": None, "gross_amount": "100.00", "currency": "NGN",
        "provider_status": "succeeded", "merchant_scope": ACTIVE_LOAN_ID,
        "timestamp": "2026-08-17T10:00:00+00:00", "provider_metadata": {},
        "provider_event_type": "payment",
    }
    db = SessionLocal()
    retry = ProviderLookupRetry(provider="mock", canonical_payload=json.dumps(payload))
    db.add(retry); db.commit(); retry_id = retry.id; db.close()

    response = client.post(f"/admin/reconciliation/provider-lookups/{retry_id}/retry", headers=ADMIN)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["attempts"] == 1
    assert response.json()["payment_event_id"] is not None
