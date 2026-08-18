"""Behaviour spec for the payment webhook you're building.

Contract (see README): POST /webhooks/payments with an X-Webhook-Token header
and a JSON body {external_ref, loan_id, amount, channel?}. A payment is
reconciled ON RECEIPT — recorded and immediately applied or rejected.

- 401 without a valid token.
- On success: the event is "applied", a repayment is recorded, the loan
  balance drops, and the loan closes when fully repaid. Return {event, loan}.
- An overpayment follows ADR-001: apply up to the loan outstanding,
  record the remainder as overpayment, and return partially_applied.

These fail against the stub — make them pass, then add your own.
"""

TOK = {"X-Webhook-Token": "dev-webhook-secret"}

from conftest import ACTIVE_LOAN_ID, CLOSED_LOAN_ID, MISSING_LOAN_ID


def _pay(ref, loan_id, amount, channel="paystack"):
    return {"external_ref": ref, "loan_id": loan_id, "amount": amount, "channel": channel}


def test_webhook_applies_payment_and_reduces_outstanding(client):
    r = client.post("/webhooks/payments", json=_pay("R-1", ACTIVE_LOAN_ID, 20000), headers=TOK)
    assert r.status_code == 200
    assert r.json()["event"]["status"] == "applied"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == 36000


def test_exact_payoff_closes_loan(client):
    client.post("/webhooks/payments", json=_pay("R-2", ACTIVE_LOAN_ID, 56000), headers=TOK)
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["status"] == "paid_off"


def test_duplicate_external_ref_is_rejected(client):
    client.post("/webhooks/payments", json=_pay("R-1", ACTIVE_LOAN_ID, 20000), headers=TOK)
    r = client.post("/webhooks/payments", json=_pay("R-1", ACTIVE_LOAN_ID, 20000), headers=TOK)  # redelivery
    assert r.json()["event"]["status"] == "rejected"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == 36000  # applied once only


def test_payment_for_cancelled_loan_is_rejected(client):
    r = client.post("/webhooks/payments", json=_pay("R-3", CLOSED_LOAN_ID, 100), headers=TOK)  # cancelled loan
    assert r.json()["event"]["status"] == "rejected"
    assert client.get(f"/loans/{CLOSED_LOAN_ID}").json()["outstanding"] == 11000  # untouched


def test_unknown_loan_is_rejected(client):
    r = client.post("/webhooks/payments", json=_pay("R-4", MISSING_LOAN_ID, 100), headers=TOK)
    assert r.json()["event"]["status"] == "rejected"


def test_overpayment_is_partially_applied(client):
    # Per ADR-001: active loans apply as much as outstanding, record remainder as overpayment
    r = client.post("/webhooks/payments", json=_pay("R-5", ACTIVE_LOAN_ID, 999999), headers=TOK)
    assert r.json()["event"]["status"] == "partially_applied"
    # Loan should be paid off with remaining amount as overpayment
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["status"] == "paid_off"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == 0


def test_webhook_requires_a_valid_token(client):
    r = client.post("/webhooks/payments", json=_pay("R-6", ACTIVE_LOAN_ID, 100))  # no token
    assert r.status_code == 401


def test_negative_credit_is_rejected_not_treated_as_a_reversal(client):
    r = client.post("/webhooks/payments", json=_pay("R-NEG", ACTIVE_LOAN_ID, -100), headers=TOK)
    assert r.json()["event"]["status"] == "rejected"
    assert r.json()["reconciliation"]["reason"] == "invalid_amount"
    assert client.get(f"/loans/{ACTIVE_LOAN_ID}").json()["outstanding"] == 56000


# --- provided endpoint (this already passes) ---

def test_feed_endpoint_lists_events(client):
    assert client.get("/payment-events").status_code == 200
