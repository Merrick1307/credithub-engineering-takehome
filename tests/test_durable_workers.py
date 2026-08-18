"""Durable worker coverage using UUID-shaped production identifiers."""

import hashlib
import hmac
import json
import uuid

from fastapi.testclient import TestClient

from app.adapters.persistence.db import Base, SessionLocal, engine
from app.main import app
from app.adapters.persistence.sqlalchemy_backend.models import Loan, LoanStatus, OutboxEvent, Overpayment, ProviderLookupRetry
from app.workers.outbox_publisher import OutboxPublisher
from app.workers.overpayment_refund_runner import OverpaymentRefundRunner, app as refund_runner_app
from app.workers.lookup_retry_runner import LookupRetryRunner


def _core_post(client, payload):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return client.post(
        "/webhooks/payments/core_banking", content=raw,
        headers={
            "content-type": "application/json",
            "x-core-banking-signature": hmac.new(
                b"core-banking-token-for-testing", raw, hashlib.sha256
            ).hexdigest(),
        },
    )


class _CallbackAdapter:
    def __init__(self, client, fail_after_callback=False):
        self.client = client
        self.fail_after_callback = fail_after_callback

    def request_refund(self, command_id, command):
        payload = {
            "notification_id": f"overpayment-refund-{command_id}",
            "account_id": command["account_id"], "amount": command["amount"],
            "currency": command["currency"], "status": "posted",
            "event": "overpayment.refunded",
            "original_notification_id": command["original_notification_id"],
            "occurred_at": command["occurred_at"], "metadata": {},
        }
        response = _core_post(self.client, payload)
        assert response.status_code == 200
        if self.fail_after_callback:
            raise ConnectionError("simulated process crash after provider accepted callback")


class _RefundWebhookPublisher:
    """Test transport for the publisher-to-refund-runner HTTP boundary."""

    def __init__(self, client):
        self.client = client

    def publish(self, event):
        response = self.client.post("/webhooks/outbox/overpayment-refunds", json=event)
        assert response.status_code in {200, 204}


def _setup_core_overpayment():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    loan_id = uuid.uuid4()
    db = SessionLocal()
    db.add(Loan(id=loan_id, borrower_name="Worker", principal=50000, total_repayable=56000,
                total_paid=0, status=LoanStatus.active))
    db.commit(); db.close()
    client = TestClient(app)
    response = _core_post(client, {
        "notification_id": "CORE-WORKER-001", "account_id": str(loan_id),
        "amount": "60000.00", "currency": "NGN", "status": "posted",
        "event": "payment.posted", "occurred_at": "2026-08-18T10:00:00+00:00", "metadata": {},
    })
    assert response.status_code == 200
    return client, loan_id


def test_core_overpayment_creates_one_durable_refund_command_and_callback_refunds_only_overpayment():
    client, loan_id = _setup_core_overpayment()
    db = SessionLocal()
    command = db.query(OutboxEvent).filter(OutboxEvent.event_type == "overpayment.refund.requested").one()
    assert command.status == "pending"
    db.close()

    refund_runner_app.state.refund_runner = OverpaymentRefundRunner(_CallbackAdapter(client))
    refund_client = TestClient(refund_runner_app)
    # The publisher claims the reconciliation notification and refund command;
    # the latter creates the final refund notification in the same run.
    assert OutboxPublisher(SessionLocal, _RefundWebhookPublisher(refund_client)).run_once() == 3

    db = SessionLocal()
    command = db.get(OutboxEvent, command.id)
    overpayment = db.query(Overpayment).one()
    loan = db.get(Loan, loan_id)
    assert command.status == "published"
    assert str(overpayment.refunded_amount) == "4000.00"
    assert str(loan.total_paid) == "56000.00"
    assert loan.status == LoanStatus.paid_off
    db.close()


def test_refund_callback_is_safe_after_crash_and_duplicate_delivery():
    client, loan_id = _setup_core_overpayment()
    db = SessionLocal()
    command = db.query(OutboxEvent).filter(OutboxEvent.event_type == "overpayment.refund.requested").one()
    delivered_event = {
        "id": str(command.id), "type": command.event_type,
        "payload": json.loads(command.payload), "correlation_id": command.correlation_id,
    }
    db.close()

    # The receiver completed the signed callback, but the publisher lost the
    # acknowledgement and delivers the same durable event again.
    refund_runner_app.state.refund_runner = OverpaymentRefundRunner(_CallbackAdapter(client, fail_after_callback=True))
    crashing_client = TestClient(refund_runner_app, raise_server_exceptions=False)
    assert crashing_client.post("/webhooks/outbox/overpayment-refunds", json=delivered_event).status_code == 500

    refund_runner_app.state.refund_runner = OverpaymentRefundRunner(_CallbackAdapter(client))
    recovered_client = TestClient(refund_runner_app)
    assert recovered_client.post("/webhooks/outbox/overpayment-refunds", json=delivered_event).status_code == 200

    db = SessionLocal()
    overpayment = db.query(Overpayment).one()
    loan = db.get(Loan, loan_id)
    assert str(overpayment.refunded_amount) == "4000.00"
    assert str(loan.total_paid) == "56000.00"
    db.close()


def test_refund_runner_ignores_an_event_of_the_wrong_type():
    class RecordingAdapter:
        def __init__(self):
            self.calls = 0

        def request_refund(self, *_):
            self.calls += 1

    adapter = RecordingAdapter()
    refund_runner_app.state.refund_runner = OverpaymentRefundRunner(adapter)
    client = TestClient(refund_runner_app)

    response = client.post("/webhooks/outbox/overpayment-refunds", json={
        "id": "not-a-refund", "type": "payment.reconciled.v1",
        "payload": {}, "correlation_id": "test-correlation",
    })

    assert response.status_code == 204
    assert adapter.calls == 0


def test_lookup_retry_runner_claims_a_lease_and_uses_shared_reconciliation():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    loan_id = uuid.uuid4()
    db = SessionLocal()
    db.add(Loan(id=loan_id, borrower_name="Lookup", principal=50000, total_repayable=56000,
                total_paid=0, status=LoanStatus.active))
    retry = ProviderLookupRetry(provider="mock", canonical_payload=json.dumps({
        "event_kind": "transaction.credit", "event_reference": "LOOKUP-WORKER-001",
        "gross_amount": "1000.00", "currency": "NGN", "provider_status": "succeeded",
        "merchant_scope": str(loan_id), "timestamp": "2026-08-18T10:00:00+00:00",
        "provider_event_type": "payment", "provider_metadata": {},
    }))
    db.add(retry); db.commit(); retry_id = retry.id; db.close()

    assert LookupRetryRunner(SessionLocal).run_once() == 1
    db = SessionLocal()
    retry = db.get(ProviderLookupRetry, retry_id)
    loan = db.get(Loan, loan_id)
    assert retry.status == "completed"
    assert retry.leased_by is None
    assert str(loan.total_paid) == "1000.00"
    db.close()
