"""Seed synthetic loans + a little payment history.

Run safely on every startup:  python -m app.seed

The seeded events are already reconciled (applied/rejected) — they're history,
so the feed isn't empty on first load. New payments arrive via the webhook (the
"Simulate incoming payment" button).
"""

import uuid

from .db import Base, SessionLocal, engine
from .models import Loan, LoanStatus, PaymentEvent, PaymentStatus, ProviderLookupRetry


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    loan_ids = [uuid.UUID(f"00000000-0000-0000-0000-00000000000{number}") for number in range(1, 7)]
    loans = [
        Loan(id=loan_ids[0], borrower_name="Adaeze Okafor", principal=100000, total_repayable=112000, total_paid=0, status=LoanStatus.active),
        Loan(id=loan_ids[1], borrower_name="Bola Adeyemi", principal=50000, total_repayable=56000, total_paid=28000, status=LoanStatus.active),
        Loan(id=loan_ids[2], borrower_name="Chidi Nwosu", principal=200000, total_repayable=224000, total_paid=224000, status=LoanStatus.paid_off),
        Loan(id=loan_ids[3], borrower_name="Fatima Bello", principal=75000, total_repayable=84000, total_paid=0, status=LoanStatus.cancelled),
        Loan(id=loan_ids[4], borrower_name="Emeka Obi", principal=300000, total_repayable=339000, total_paid=100000, status=LoanStatus.written_off),
        Loan(id=loan_ids[5], borrower_name="Ngozi Eze", principal=33333, total_repayable=37333.33, total_paid=0, status=LoanStatus.active),
    ]
    # History — already reconciled (consistent with the loan balances above).
    events = [
        PaymentEvent(external_ref="PSK-8001", loan_id=loan_ids[1], amount=28000, channel="paystack", status=PaymentStatus.applied),
        PaymentEvent(external_ref="PSK-8002", loan_id=loan_ids[2], amount=224000, channel="gsi", status=PaymentStatus.applied),
        PaymentEvent(external_ref="PSK-8003", loan_id=loan_ids[3], amount=5000, channel="cbs",
                     status=PaymentStatus.rejected, reason="loan is cancelled, not active"),
    ]
    retries = [
        ProviderLookupRetry(provider="mock", canonical_payload=f'{{"event_kind":"transaction.credit","event_reference":"SEED-MOCK-RETRY","gross_amount":"1000.00","currency":"NGN","provider_status":"succeeded","merchant_scope":"{loan_ids[0]}","timestamp":"2026-08-17T12:00:00Z","provider_event_type":"payment"}}'),
        ProviderLookupRetry(provider="core_banking", canonical_payload=f'{{"event_kind":"transaction.credit","event_reference":"SEED-CORE-RETRY","gross_amount":"2000.00","currency":"NGN","provider_status":"succeeded","merchant_scope":"{loan_ids[1]}","timestamp":"2026-08-17T12:01:00Z","provider_event_type":"payment.posted"}}'),
    ]
    try:
        inserted_loans = 0
        inserted_events = 0
        for loan in loans:
            if db.get(Loan, loan.id) is None:
                db.add(loan)
                inserted_loans += 1

        # Flush the parent rows before adding events that reference them.
        db.flush()
        for event in events:
            existing = db.query(PaymentEvent.id).filter_by(external_ref=event.external_ref).first()
            if existing is None:
                db.add(event)
                inserted_events += 1

        inserted_retries = 0
        for retry in retries:
            exists = db.query(ProviderLookupRetry.id).filter_by(provider=retry.provider, canonical_payload=retry.canonical_payload).first()
            if exists is None:
                db.add(retry)
                inserted_retries += 1

        db.commit()
        print(f"seed complete: added {inserted_loans} loans, {inserted_events} historical payment events, and {inserted_retries} manual retries")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
