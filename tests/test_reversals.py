"""End-to-end coverage for the initial full-payment reversal slice."""

import hashlib
import hmac
import json

from conftest import ACTIVE_LOAN_ID, CLOSED_LOAN_ID


def _sign_mock_payload(payload: dict) -> dict:
    raw_body = json.dumps(payload).encode("utf-8")
    signature = hmac.new(
        b"mock-secret-key-for-testing", raw_body, hashlib.sha256
    ).hexdigest()
    return {"x-mock-signature": signature, "content-type": "application/json"}


def _post_mock(client, payload: dict):
    return client.post(
        "/webhooks/payments/mock",
        content=json.dumps(payload),
        headers=_sign_mock_payload(payload),
    )


def _payment(reference: str, amount: int) -> dict:
    return {
        "transaction_id": reference,
        "amount": amount,
        "customer_id": ACTIVE_LOAN_ID,
        "status": "success",
        "timestamp": "2026-08-17T10:00:00Z",
        "event_type": "payment",
        "metadata": {},
    }


def _reversal(reference: str, original_reference: str | None, amount: int) -> dict:
    payload = {
        "transaction_id": reference,
        "amount": amount,
        "customer_id": ACTIVE_LOAN_ID,
        "status": "success",
        "timestamp": "2026-08-17T10:01:00Z",
        "event_type": "reversal",
        "metadata": {},
    }
    if original_reference is not None:
        payload["original_transaction_id"] = original_reference
    return payload


def test_full_reversal_of_exact_payoff_reopens_loan(client):
    assert _post_mock(client, _payment("TXN-REV-001", 5_600_000)).json()["event"]["status"] == "applied"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["status"] == "paid_off"

    response = _post_mock(client, _reversal("REV-001", "TXN-REV-001", 5_600_000))

    assert response.status_code == 200
    assert response.json()["event"]["status"] == "applied"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["status"] == "active"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == 56_000


def test_full_reversal_of_partial_payment_restores_outstanding(client):
    _post_mock(client, _payment("TXN-REV-002", 2_000_000))
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == 36_000

    response = _post_mock(client, _reversal("REV-002", "TXN-REV-002", 2_000_000))

    assert response.json()["event"]["status"] == "applied"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == 56_000


def test_reversal_without_original_reference_is_rejected(client):
    response = _post_mock(client, _reversal("REV-ORPHAN", None, 1_000_000))

    assert response.status_code == 200
    assert response.json()["event"]["status"] == "rejected"
    assert response.json()["reconciliation"]["reason"] == "reversal_without_original"


def test_reversal_of_unknown_original_payment_is_rejected(client):
    response = _post_mock(client, _reversal("REV-UNKNOWN", "NONEXISTENT", 1_000_000))

    assert response.status_code == 200
    assert response.json()["reconciliation"]["reason"] == "reversal_without_original"


def test_exact_reversal_redelivery_replays_without_second_balance_change(client):
    _post_mock(client, _payment("TXN-IDEM", 2_000_000))
    payload = _reversal("REV-IDEM", "TXN-IDEM", 2_000_000)

    first = _post_mock(client, payload)
    outstanding_after_first = client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"]
    replay = _post_mock(client, payload)

    assert first.json()["event"]["status"] == "applied"
    assert replay.json()["event"]["status"] == "applied"
    assert replay.json()["reconciliation"]["idempotent_replay"] is True
    assert replay.json()["loan"]["outstanding"] == "56000.00"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == outstanding_after_first


def test_partial_reversal_is_quarantined_without_balance_change(client):
    _post_mock(client, _payment("TXN-PARTIAL", 2_000_000))
    outstanding_after_payment = client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"]

    response = _post_mock(client, _reversal("REV-PARTIAL", "TXN-PARTIAL", 1_000_000))

    assert response.json()["event"]["status"] == "rejected"
    assert response.json()["reconciliation"]["reason"] == "reversal_integrity"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == outstanding_after_payment


def test_second_distinct_full_reversal_is_rejected(client):
    _post_mock(client, _payment("TXN-ONCE", 2_000_000))
    _post_mock(client, _reversal("REV-FIRST", "TXN-ONCE", 2_000_000))
    outstanding_after_first = client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"]

    response = _post_mock(client, _reversal("REV-SECOND", "TXN-ONCE", 2_000_000))

    assert response.json()["event"]["status"] == "rejected"
    assert response.json()["reconciliation"]["reason"] == "reversal_already_applied"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == outstanding_after_first


def test_reversal_compensates_repayment_and_overpayment_components(client):
    response = _post_mock(client, _payment("TXN-OVERPAY", 6_000_000))
    assert response.json()["event"]["status"] == "partially_applied"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["status"] == "paid_off"

    reversal = _post_mock(client, _reversal("REV-OVERPAY", "TXN-OVERPAY", 6_000_000))

    assert reversal.json()["event"]["status"] == "applied"
    loan = client.get(f"/loans/{ACTIVE_LOAN_ID}").json()
    assert loan["status"] == "active"
    assert loan["outstanding"] == 56_000


def test_refund_consumes_overpayment_without_changing_loan(client):
    _post_mock(client, _payment("TXN-REFUND", 6_000_000))
    before = client.get(f"/loans/{ACTIVE_LOAN_ID}").json()
    refund = _reversal("REFUND-001", "TXN-REFUND", 200_000)
    refund["event_type"] = "refund"

    response = _post_mock(client, refund)

    assert response.json()["event"]["status"] == "applied"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json() == before


def test_reversal_after_related_refund_is_quarantined(client):
    _post_mock(client, _payment("TXN-REFUND-REV", 6_000_000))
    refund = _reversal("REFUND-REV", "TXN-REFUND-REV", 200_000)
    refund["event_type"] = "refund"
    _post_mock(client, refund)
    before = client.get(f"/loans/{ACTIVE_LOAN_ID}").json()

    response = _post_mock(client, _reversal("REV-AFTER-REFUND", "TXN-REFUND-REV", 6_000_000))

    assert response.json()["event"]["status"] == "rejected"
    assert response.json()["reconciliation"]["reason"] == "reversal_integrity"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json() == before


def test_reversal_of_closed_loan_overpayment_preserves_operational_status(client):
    payment = _payment("TXN-CLOSED", 1_000_000)
    payment["customer_id"] = CLOSED_LOAN_ID
    assert _post_mock(client, payment).json()["event"]["status"] == "rejected"

    reversal = _reversal("REV-CLOSED", "TXN-CLOSED", 1_000_000)
    reversal["customer_id"] = CLOSED_LOAN_ID
    response = _post_mock(client, reversal)

    assert response.json()["event"]["status"] == "applied"
    assert client.get(f"/loans/{CLOSED_LOAN_ID}").json()["status"] == "cancelled"
