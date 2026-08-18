"""SQLAlchemy repository implementations."""

from typing import Optional, List
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from ...domain.enums import LoanStatus, EventKind, ReconciliationStatus
from ...ports.repositories import (
    LoanRepository,
    PaymentEventRepository,
    IdempotencyRepository,
    OutboxRepository,
    UnitOfWork,
)
from ...models import AuditLog, Loan, PaymentEvent, Repayment, PaymentStatus, Overpayment, ReconciliationIssue
from ...ports.repositories import OverpaymentRepository


class SQLAlchemyLoanRepository(LoanRepository):
    """SQLAlchemy implementation of LoanRepository."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_loan_by_id(self, loan_id: int):
        """Load a loan by ID."""
        return self.session.query(Loan).filter(Loan.id == loan_id).with_for_update().first()
    
    def get_loans_by_external_account(self, provider: str, account_id: str) -> List[int]:
        """Find loans by provider-scoped account.
        
        For this demo, account_id is the loan_id itself (via merchant_scope).
        """
        try:
            loan_id = uuid.UUID(account_id)
            loan = self.get_loan_by_id(loan_id)
            return [loan_id] if loan else []
        except (ValueError, TypeError):
            return []
    
    def update_loan_balance(
        self,
        loan_id: int,
        total_paid: Decimal,
        status: Optional[LoanStatus] = None,
    ) -> None:
        """Update loan balance and optionally status."""
        loan = self.session.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            raise ValueError(f"Loan {loan_id} not found")
        
        loan.total_paid = total_paid
        if status:
            loan.status = status
        
        self.session.add(loan)
    
    def record_repayment_ledger(
        self,
        loan_id: int,
        payment_event_id: int,
        amount: Decimal,
        entry_type: str = "repayment",
        loan_balance_delta: Optional[Decimal] = None,
        overpayment_balance_delta: Optional[Decimal] = None,
        overpayment_id: Optional[int] = None,
        adjusts_repayment_id: Optional[int] = None,
    ) -> int:
        """Record a repayment ledger entry."""
        repayment = Repayment(
            loan_id=loan_id,
            payment_event_id=payment_event_id,
            amount=amount,
            entry_type=entry_type,
            loan_balance_delta=loan_balance_delta if loan_balance_delta is not None else amount,
            overpayment_balance_delta=overpayment_balance_delta or Decimal(0),
            overpayment_id=overpayment_id,
            adjusts_repayment_id=adjusts_repayment_id,
        )
        self.session.add(repayment)
        self.session.flush()
        return repayment.id
    
    def get_total_paid_by_loan(self, loan_id: int) -> Decimal:
        """Get the sum of all repayment ledger entries for a loan."""
        total = self.session.query(Repayment).filter(
            Repayment.loan_id == loan_id
        ).all()
        
        if not total:
            return Decimal(0)
        
        return Decimal(str(sum(r.amount for r in total)))


class SQLAlchemyPaymentEventRepository(PaymentEventRepository):
    """SQLAlchemy implementation of PaymentEventRepository."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def get_event_by_identity(
        self,
        provider: str,
        merchant_scope: str,
        event_kind: EventKind,
        event_reference: str,
    ) -> Optional[dict]:
        """Load an event by its provider-scoped canonical identity."""
        event = self.session.query(PaymentEvent).filter(
            PaymentEvent.provider == provider,
            PaymentEvent.merchant_scope == merchant_scope,
            PaymentEvent.event_kind == event_kind.value,
            PaymentEvent.external_ref == event_reference,
        ).first()
        
        if event:
            return {
                "id": event.id,
                "external_ref": event.external_ref,
                "loan_id": event.loan_id,
                "amount": event.amount,
                "status": event.status.value,
                "reason": event.reason,
                "provider": event.provider,
                "merchant_scope": event.merchant_scope,
                "event_kind": event.event_kind,
                "original_payment_reference": event.original_payment_reference,
                "provider_status": event.provider_status,
                "fingerprint": event.fingerprint,
                "applied_amount": event.applied_amount,
                "overpaid_amount": event.overpaid_amount,
            }
        return None
    
    def get_events_by_reference(
        self,
        event_reference: str,
    ) -> List[dict]:
        """Load all events with a specific reference."""
        events = self.session.query(PaymentEvent).filter(
            PaymentEvent.external_ref == event_reference
        ).all()
        
        return [
            {
                "id": event.id,
                "external_ref": event.external_ref,
                "loan_id": event.loan_id,
                "amount": event.amount,
                "status": event.status.value,
                "reason": event.reason,
                "provider": event.provider,
                "merchant_scope": event.merchant_scope,
                "event_kind": event.event_kind,
                "original_payment_reference": event.original_payment_reference,
                "provider_status": event.provider_status,
                "fingerprint": event.fingerprint,
                "applied_amount": event.applied_amount,
                "overpaid_amount": event.overpaid_amount,
            }
            for event in events
        ]

    def get_successful_reversals_for_original_reference(
        self,
        provider: str,
        merchant_scope: str,
        original_payment_reference: str,
    ) -> List[dict]:
        """Return prior applied reversal actions for an original credit."""
        events = self.session.query(PaymentEvent).filter(
            PaymentEvent.provider == provider,
            PaymentEvent.merchant_scope == merchant_scope,
            PaymentEvent.event_kind == EventKind.transaction_reversal.value,
            PaymentEvent.original_payment_reference == original_payment_reference,
            PaymentEvent.status == PaymentStatus.applied,
        ).all()
        return [{"id": event.id, "external_ref": event.external_ref} for event in events]

    def get_ledger_components_for_event(self, payment_event_id: int) -> List[dict]:
        """Return all immutable ledger components for an event, newest last."""
        rows = self.session.query(Repayment).filter(
            Repayment.payment_event_id == payment_event_id
        ).order_by(Repayment.id).all()
        return [
            {
                "id": row.id,
                "loan_id": row.loan_id,
                "amount": Decimal(str(row.amount)),
                "entry_type": row.entry_type,
                "loan_balance_delta": Decimal(str(row.loan_balance_delta)),
                "overpayment_balance_delta": Decimal(str(row.overpayment_balance_delta)),
                "overpayment_id": row.overpayment_id,
                "adjusts_repayment_id": row.adjusts_repayment_id,
            }
            for row in rows
        ]
    
    def record_event(
        self,
        provider: str,
        merchant_scope: str,
        event_kind: EventKind,
        event_reference: str,
        original_payment_reference: Optional[str],
        gross_amount: Decimal,
        provider_status: str,
        provider_event_type: str,
        provider_metadata: dict,
        timestamp: datetime,
        idempotency_fingerprint: str,
    ) -> int:
        """Insert a new canonical event."""
        # The legacy schema stores the canonical fields alongside its original
        # feed columns, so both webhook contracts share one event journal.
        event = PaymentEvent(
            external_ref=event_reference,
            loan_id=uuid.UUID(merchant_scope),
            amount=gross_amount,
            channel=provider,
            provider=provider,
            merchant_scope=merchant_scope,
            event_kind=event_kind.value,
            original_payment_reference=original_payment_reference,
            provider_status=provider_status,
            fingerprint=idempotency_fingerprint,
            status=PaymentStatus.pending,
        )
        self.session.add(event)
        self.session.flush()
        return event.id
    
    def update_event_reconciliation(
        self,
        event_id: int,
        loan_id: Optional[int],
        status: ReconciliationStatus,
        reason: str,
        applied_amount: Decimal,
        overpaid_amount: Decimal,
    ) -> None:
        """Update event with reconciliation outcome."""
        event = self.session.query(PaymentEvent).filter(PaymentEvent.id == event_id).first()
        if not event:
            raise ValueError(f"Event {event_id} not found")
        
        # Map ReconciliationStatus to PaymentStatus
        if status == ReconciliationStatus.applied:
            event.status = PaymentStatus.applied
        elif status == ReconciliationStatus.partially_applied:
            event.status = PaymentStatus.applied  # Still applied for demo
        else:
            event.status = PaymentStatus.rejected
        
        event.reason = reason
        event.loan_id = loan_id
        event.applied_amount = applied_amount
        event.overpaid_amount = overpaid_amount
        event.processed_at = datetime.now(timezone.utc)
        self.session.add(event)
        self.session.add(AuditLog(
            action=f"payment_event.{status.value}",
            entity="payment_event",
            entity_id=str(event.id),
            actor="system",
            detail=reason,
        ))
        if status == ReconciliationStatus.rejected:
            self.session.add(ReconciliationIssue(
                issue_type="reconciliation_rejection",
                reason=reason,
                payment_event_id=event.id,
                loan_id=loan_id,
            ))


class SQLAlchemyIdempotencyRepository(IdempotencyRepository):
    """SQLAlchemy implementation of IdempotencyRepository."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def claim_idempotency_key(
        self,
        provider: str,
        merchant_scope: str,
        event_kind: EventKind,
        event_reference: str,
    ) -> tuple[bool, Optional[dict]]:
        """Atomically claim an idempotency key.
        
        For demo, we use external_ref as the key. If it already exists,
        return the prior result.
        """
        existing = self.session.query(PaymentEvent).filter(
            PaymentEvent.external_ref == event_reference
        ).first()
        
        if existing and existing.status == PaymentStatus.applied:
            # Return the prior result
            return (False, {
                "status": "applied",
                "reason": None,
            })
        elif existing and existing.status == PaymentStatus.rejected:
            # Return the prior rejection
            return (False, {
                "status": "rejected",
                "reason": existing.reason,
            })
        
        # New key; caller owns it
        return (True, None)
    
    def record_idempotency_result(
        self,
        provider: str,
        merchant_scope: str,
        event_kind: EventKind,
        event_reference: str,
        fingerprint: str,
        result: dict,
    ) -> None:
        """Store result for a processed event."""
        # For demo, store in the reason field
        pass


class SQLAlchemyOverpaymentRepository(OverpaymentRepository):
    """SQLAlchemy implementation of the overpayment projection."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _as_dict(overpayment: Overpayment) -> dict:
        return {
            "id": overpayment.id,
            "loan_id": overpayment.loan_id,
            "payment_event_id": overpayment.payment_event_id,
            "amount": Decimal(str(overpayment.amount)),
            "refunded_amount": Decimal(str(overpayment.refunded_amount)),
            "reversed_amount": Decimal(str(overpayment.reversed_amount)),
            "remaining_amount": Decimal(str(overpayment.remaining_amount)),
            "status": overpayment.status,
        }

    def create(self, loan_id: int, payment_event_id: int, amount: Decimal) -> dict:
        overpayment = Overpayment(
            loan_id=loan_id,
            payment_event_id=payment_event_id,
            amount=amount,
        )
        self.session.add(overpayment)
        self.session.flush()
        return self._as_dict(overpayment)

    def get_by_payment_event(self, payment_event_id: int) -> Optional[dict]:
        overpayment = self.session.query(Overpayment).filter(
            Overpayment.payment_event_id == payment_event_id
        ).with_for_update().first()
        return self._as_dict(overpayment) if overpayment else None

    def apply_refund(self, overpayment_id: int, amount: Decimal) -> None:
        overpayment = self.session.query(Overpayment).filter(Overpayment.id == overpayment_id).with_for_update().first()
        if not overpayment or Decimal(str(overpayment.remaining_amount)) < amount:
            raise ValueError("Refund exceeds remaining overpayment")
        overpayment.refunded_amount = Decimal(str(overpayment.refunded_amount)) + amount
        if Decimal(str(overpayment.remaining_amount)) == 0:
            overpayment.status = "refunded"

    def apply_reversal(self, overpayment_id: int, amount: Decimal) -> None:
        overpayment = self.session.query(Overpayment).filter(Overpayment.id == overpayment_id).with_for_update().first()
        if not overpayment or Decimal(str(overpayment.remaining_amount)) < amount:
            raise ValueError("Reversal exceeds remaining overpayment")
        overpayment.reversed_amount = Decimal(str(overpayment.reversed_amount)) + amount
        if Decimal(str(overpayment.remaining_amount)) == 0:
            overpayment.status = "refunded"


class SQLAlchemyOutboxRepository(OutboxRepository):
    """SQLAlchemy implementation of OutboxRepository."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def record_outbox_event(
        self,
        event_type: str,
        payload: dict,
        correlation_id: str,
    ) -> int:
        """Record an outgoing event."""
        # TODO: Implement with a real outbox table
        # For demo, just log it
        print(f"[OUTBOX] {event_type}: {payload}")
        return 0
    
    def list_unpublished_events(self, limit: int = 100) -> List[dict]:
        """Fetch unpublished outbox events."""
        # For demo, return empty
        return []
    
    def mark_event_published(self, outbox_id: int) -> None:
        """Mark an event as published."""
        pass


class SQLAlchemyUnitOfWork(UnitOfWork):
    """SQLAlchemy transaction boundary and repository container."""
    
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session = None
        self._loans = None
        self._payment_events = None
        self._idempotency = None
        self._overpayments = None
        self._outbox = None
    
    def __enter__(self):
        self.session = self.session_factory()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.session.rollback()
        else:
            self.session.commit()
        self.session.close()
    
    @property
    def loans(self) -> LoanRepository:
        if self._loans is None:
            self._loans = SQLAlchemyLoanRepository(self.session)
        return self._loans
    
    @property
    def payment_events(self) -> PaymentEventRepository:
        if self._payment_events is None:
            self._payment_events = SQLAlchemyPaymentEventRepository(self.session)
        return self._payment_events
    
    @property
    def idempotency(self) -> IdempotencyRepository:
        if self._idempotency is None:
            self._idempotency = SQLAlchemyIdempotencyRepository(self.session)
        return self._idempotency

    @property
    def overpayments(self) -> OverpaymentRepository:
        if self._overpayments is None:
            self._overpayments = SQLAlchemyOverpaymentRepository(self.session)
        return self._overpayments
    
    @property
    def outbox(self) -> OutboxRepository:
        if self._outbox is None:
            self._outbox = SQLAlchemyOutboxRepository(self.session)
        return self._outbox
