"""Optional PostgreSQL races for the money-changing reconciliation path.

Enable with TEST_POSTGRES_DATABASE_URL pointing at an isolated database. These
are intentionally not SQLite tests: they exercise the row locks and uniqueness
constraints relied on by the production transaction model.
"""

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.persistence.db import Base
from app.adapters.persistence.sqlalchemy_backend.models import Loan, LoanStatus, Overpayment, Repayment
from app.adapters.persistence.sqlalchemy_backend.sqlalchemy_repositories import SQLAlchemyUnitOfWork
from app.application.reconcile_payment import ReconcilePaymentUseCase
from app.domain.enums import EventKind
from app.domain.models import CanonicalFinancialEvent, Money
from app.infrastructure.provider_registry import NoOpProviderLookup, SimpleProviderRegistry


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_DATABASE_URL"),
    reason="requires an isolated PostgreSQL database",
)


def _event(loan_id, reference, amount):
    return CanonicalFinancialEvent(
        provider="paystack",
        event_kind=EventKind.transaction_credit,
        event_reference=reference,
        original_payment_reference=None,
        gross_amount=Money(Decimal(amount), "NGN"),
        provider_status="succeeded",
        merchant_scope=str(loan_id),
        timestamp=datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc),
        provider_metadata={},
        provider_event_type="charge.success",
    )


def _database():
    engine = create_engine(os.environ["TEST_POSTGRES_DATABASE_URL"])
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    loan_id = uuid.uuid4()
    db = sessions()
    db.add(Loan(
        id=loan_id,
        borrower_name="Concurrent Borrower",
        principal=Decimal("50000.00"),
        total_repayable=Decimal("56000.00"),
        total_paid=Decimal("0.00"),
        status=LoanStatus.active,
    ))
    db.commit()
    db.close()
    return engine, sessions, loan_id


def _run(sessions, event, barrier):
    barrier.wait()
    return ReconcilePaymentUseCase(
        SQLAlchemyUnitOfWork(sessions),
        SimpleProviderRegistry(),
        NoOpProviderLookup(),
    ).execute(event, f"race-{uuid.uuid4()}")


def test_same_reference_race_has_one_economic_application():
    engine, sessions, loan_id = _database()
    try:
        event = _event(loan_id, "RACE-SAME-001", "20000.00")
        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: _run(sessions, event, barrier), range(2)))

        db = sessions()
        try:
            loan = db.get(Loan, loan_id)
            repayments = db.query(Repayment).all()
            assert Decimal(str(loan.total_paid)) == Decimal("20000.00")
            assert len(repayments) == 1
            assert sum(result.idempotent_replay for result in results) == 1
        finally:
            db.close()
    finally:
        engine.dispose()


def test_distinct_payments_racing_same_loan_cannot_overdraw_balance():
    engine, sessions, loan_id = _database()
    try:
        events = [
            _event(loan_id, "RACE-LOAN-A", "40000.00"),
            _event(loan_id, "RACE-LOAN-B", "40000.00"),
        ]
        barrier = threading.Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda event: _run(sessions, event, barrier), events))

        db = sessions()
        try:
            loan = db.get(Loan, loan_id)
            overpayments = db.query(Overpayment).all()
            assert Decimal(str(loan.total_paid)) == Decimal("56000.00")
            assert Decimal(str(loan.outstanding)) == Decimal("0.00")
            assert loan.status == LoanStatus.paid_off
            assert len(overpayments) == 1
            assert Decimal(str(overpayments[0].remaining_amount)) == Decimal("24000.00")
            assert sorted(result.status.value for result in results) == ["applied", "partially_applied"]
        finally:
            db.close()
    finally:
        engine.dispose()
