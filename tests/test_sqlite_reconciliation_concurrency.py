"""SQLite regression coverage for concurrent reconciliation of one loan."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.adapters.persistence.db import Base
from app.adapters.persistence.sqlalchemy_backend.models import Loan, LoanStatus, Overpayment, Repayment
from app.adapters.persistence.sqlalchemy_backend.sqlalchemy_repositories import SQLAlchemyUnitOfWork
from app.application.reconcile_payment import ReconcilePaymentUseCase
from app.domain.enums import EventKind
from app.domain.models import CanonicalFinancialEvent, Money
from app.infrastructure.provider_registry import NoOpProviderLookup, SimpleProviderRegistry


def test_sqlite_serializes_distinct_payments_for_the_same_loan(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'same-loan.db'}",
        connect_args={"check_same_thread": False, "timeout": 2},
        poolclass=NullPool,
    )
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

    # Widen the old race deterministically: without SQLite transaction
    # serialization, both workers finish their first loan read before either
    # writes. With serialization, the first worker times out of this test-only
    # rendezvous and commits before the second worker can read the loan.
    first_loan_reads = threading.Barrier(2)
    thread_state = threading.local()

    @event.listens_for(engine, "after_cursor_execute")
    def rendezvous_after_first_loan_read(conn, cursor, statement, parameters, context, executemany):
        if "FROM loans" not in statement or getattr(thread_state, "synchronized", False):
            return
        thread_state.synchronized = True
        try:
            first_loan_reads.wait(timeout=0.25)
        except threading.BrokenBarrierError:
            pass

    def payment(reference):
        return CanonicalFinancialEvent(
            provider="paystack",
            event_kind=EventKind.transaction_credit,
            event_reference=reference,
            original_payment_reference=None,
            gross_amount=Money(Decimal("40000.00"), "NGN"),
            provider_status="succeeded",
            merchant_scope=str(loan_id),
            timestamp=datetime(2026, 8, 20, tzinfo=timezone.utc),
            provider_metadata={},
            provider_event_type="charge.success",
        )

    start = threading.Barrier(2)

    def reconcile(event_to_apply):
        start.wait()
        return ReconcilePaymentUseCase(
            SQLAlchemyUnitOfWork(sessions),
            SimpleProviderRegistry(),
            NoOpProviderLookup(),
        ).execute(event_to_apply, f"sqlite-race-{uuid.uuid4()}")

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reconcile, [payment("SQLITE-RACE-A"), payment("SQLITE-RACE-B")]))

        db = sessions()
        try:
            loan = db.get(Loan, loan_id)
            overpayments = db.query(Overpayment).all()
            repayments = db.query(Repayment).all()
            assert Decimal(str(loan.total_paid)) == Decimal("56000.00")
            assert Decimal(str(loan.outstanding)) == Decimal("0.00")
            assert loan.status == LoanStatus.paid_off
            assert sorted(
                Decimal(str(row.amount))
                for row in repayments
                if row.entry_type == "repayment"
            ) == [Decimal("16000.00"), Decimal("40000.00")]
            assert len(overpayments) == 1
            assert Decimal(str(overpayments[0].remaining_amount)) == Decimal("24000.00")
            assert sorted(result.status.value for result in results) == ["applied", "partially_applied"]
        finally:
            db.close()
    finally:
        engine.dispose()
