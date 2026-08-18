"""Port interfaces for repository access.

Repositories are the abstraction over persistence. The domain and application
layers depend on these ports; the infrastructure layer implements them.
"""

from abc import ABC, abstractmethod
from typing import Optional, List
from decimal import Decimal
from datetime import datetime

from ..domain.enums import LoanStatus, EventKind, ReconciliationStatus


class LoanRepository(ABC):
    """Port for loading and updating loans."""
    
    @abstractmethod
    def get_loan_by_id(self, loan_id: int):
        """Load a loan by ID with lock if in transaction context."""
        pass
    
    @abstractmethod
    def get_loans_by_external_account(self, provider: str, account_id: str) -> List[int]:
        """Find loan IDs by provider-scoped account identifier."""
        pass
    
    @abstractmethod
    def update_loan_balance(
        self,
        loan_id: int,
        total_paid: Decimal,
        status: Optional[LoanStatus] = None,
    ) -> None:
        """Update loan's total_paid and optionally status."""
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def get_total_paid_by_loan(self, loan_id: int) -> Decimal:
        """Get the sum of all repayment ledger entries for a loan."""
        pass


class PaymentEventRepository(ABC):
    """Port for recording canonical financial events."""
    
    @abstractmethod
    def get_event_by_identity(
        self,
        provider: str,
        merchant_scope: str,
        event_kind: EventKind,
        event_reference: str,
    ) -> Optional[dict]:
        """Load an event by its canonical identity."""
        pass
    
    @abstractmethod
    def get_events_by_reference(
        self,
        event_reference: str,
    ) -> List[dict]:
        """Load all events with a specific reference (for reversal lookup)."""
        pass

    @abstractmethod
    def get_ledger_components_for_event(self, payment_event_id: int) -> List[dict]:
        """Load immutable ledger components written for one financial event."""
        pass

    @abstractmethod
    def get_successful_reversals_for_original_reference(
        self,
        provider: str,
        merchant_scope: str,
        original_payment_reference: str,
    ) -> List[dict]:
        """Load applied reversals that already compensate an original credit."""
        pass
    
    @abstractmethod
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
        """Insert a new canonical event and return its ID."""
        pass
    
    @abstractmethod
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
        pass


class IdempotencyRepository(ABC):
    """Port for idempotent event processing."""
    
    @abstractmethod
    def claim_idempotency_key(
        self,
        provider: str,
        merchant_scope: str,
        event_kind: EventKind,
        event_reference: str,
    ) -> tuple[bool, Optional[dict]]:
        """Atomically claim an idempotency key in a transaction.
        
        Returns (claimed, prior_result) where:
        - claimed=True, prior_result=None: Key is now owned by this caller
        - claimed=False, prior_result=dict: Key was previously processed with this result
        - claimed=False, prior_result=None: Key exists but fingerprint differs (conflict)
        """
        pass

    @abstractmethod
    def record_idempotency_result(
        self,
        provider: str,
        merchant_scope: str,
        event_kind: EventKind,
        event_reference: str,
        fingerprint: str,
        result: dict,
    ) -> None:
        """Store the result for a successfully processed event."""
        pass


class OverpaymentRepository(ABC):
    """Port for the mutable overpayment balance projection."""

    @abstractmethod
    def create(self, loan_id: int, payment_event_id: int, amount: Decimal) -> dict:
        pass

    @abstractmethod
    def get_by_payment_event(self, payment_event_id: int) -> Optional[dict]:
        pass

    @abstractmethod
    def apply_refund(self, overpayment_id: int, amount: Decimal) -> None:
        pass

    @abstractmethod
    def apply_reversal(self, overpayment_id: int, amount: Decimal) -> None:
        pass
    
class OutboxRepository(ABC):
    """Port for transactional outbox pattern."""
    
    @abstractmethod
    def record_outbox_event(
        self,
        event_type: str,
        payload: dict,
        correlation_id: str,
        idempotency_key: Optional[str] = None,
    ) -> int:
        """Record an outgoing event in the outbox (idempotent publish)."""
        pass
    
    @abstractmethod
    def list_unpublished_events(self, limit: int = 100) -> List[dict]:
        """Fetch outbox events not yet published."""
        pass
    
    @abstractmethod
    def mark_event_published(self, outbox_id: int) -> None:
        """Mark an outbox event as published."""
        pass


class UnitOfWork(ABC):
    """Port for transaction boundary and repository access."""
    
    @abstractmethod
    def __enter__(self):
        """Begin transaction."""
        pass
    
    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Commit or rollback."""
        pass
    
    @property
    @abstractmethod
    def loans(self) -> LoanRepository:
        """Access loan repository."""
        pass
    
    @property
    @abstractmethod
    def payment_events(self) -> PaymentEventRepository:
        """Access payment event repository."""
        pass
    
    @property
    @abstractmethod
    def idempotency(self) -> IdempotencyRepository:
        """Access idempotency repository."""
        pass

    @property
    @abstractmethod
    def overpayments(self) -> OverpaymentRepository:
        """Access overpayment projections."""
        pass
    
    @property
    @abstractmethod
    def outbox(self) -> OutboxRepository:
        """Access outbox repository."""
        pass
