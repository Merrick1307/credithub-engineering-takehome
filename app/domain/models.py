"""Domain value objects and data classes."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from datetime import datetime

from .enums import EventKind, ReconciliationStatus, ReconciliationReason, LoanStatus


@dataclass(frozen=True)
class Money:
    """Immutable monetary value."""
    amount: Decimal
    currency: str = "NGN"
    
    def __post_init__(self):
        if self.amount.as_tuple().exponent < -2:
            raise ValueError(f"Money amount {self.amount} has more than 2 decimal places")
    
    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"Cannot add {self.currency} and {other.currency}")
        return Money(self.amount + other.amount, self.currency)
    
    def __sub__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"Cannot subtract {self.currency} and {other.currency}")
        return Money(self.amount - other.amount, self.currency)
    
    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)
    
    def is_positive(self) -> bool:
        return self.amount > 0
    
    def is_zero(self) -> bool:
        return self.amount == 0
    
    def is_negative(self) -> bool:
        return self.amount < 0


@dataclass(frozen=True)
class LoanBalance:
    """Loan's financial state."""
    total_repayable: Money
    total_paid: Money
    
    @property
    def outstanding(self) -> Money:
        return self.total_repayable - self.total_paid
    
    @property
    def is_paid_off(self) -> bool:
        return self.outstanding.is_zero() or self.outstanding.is_negative()


@dataclass(frozen=True)
class CanonicalFinancialEvent:
    """Provider-agnostic financial event after normalization.
    
    This is the single internal contract across adapters and the domain.
    """
    provider: str
    event_kind: EventKind
    event_reference: str  # Unique within provider + merchant scope + event kind
    original_payment_reference: Optional[str]  # For reversals/refunds
    
    gross_amount: Money
    provider_status: str  # "succeeded", "pending", "failed", etc. (provider-specific)
    
    merchant_scope: str  # Merchant/partner ID from provider context
    timestamp: datetime
    
    # Provider-specific metadata (unknown fields, extra context)
    provider_metadata: dict
    provider_event_type: str  # Original provider event label
    
    # Schema version for future evolution
    schema_version: int = 1


@dataclass(frozen=True)
class ReconciliationResult:
    """Outcome of reconciling a single financial event."""
    event_id: Optional[int]  # Database ID of the canonical event
    status: ReconciliationStatus
    reason: ReconciliationReason
    
    gross_amount: Money
    applied_amount: Money
    overpaid_amount: Money
    
    loan_id: Optional[int]
    loan_status: Optional[LoanStatus]
    loan_outstanding: Optional[Money]
    
    idempotent_replay: bool = False
    
    def to_dict(self) -> dict:
        """Export as provider-agnostic JSON-compatible response."""
        return {
            "event": {"id": self.event_id, "status": self.status.value},
            "reconciliation": {
                "gross_amount": str(self.gross_amount.amount),
                "applied_amount": str(self.applied_amount.amount),
                "overpaid_amount": str(self.overpaid_amount.amount),
                "reason": self.reason.value,
                "idempotent_replay": self.idempotent_replay,
            },
            "loan": {
                "id": self.loan_id,
                "outstanding": str(self.loan_outstanding.amount) if self.loan_outstanding else None,
                "status": self.loan_status.value if self.loan_status else None,
            } if self.loan_id else None,
        }
