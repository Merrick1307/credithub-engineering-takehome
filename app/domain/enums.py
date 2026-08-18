"""Domain enums for payment reconciliation."""

import enum


class LoanStatus(str, enum.Enum):
    """Loan lifecycle states."""
    active = "active"
    paid_off = "paid_off"
    cancelled = "cancelled"
    written_off = "written_off"


class EventKind(str, enum.Enum):
    """Canonical financial event types."""
    transaction_credit = "transaction.credit"
    transaction_reversal = "transaction.reversal"
    transaction_refund = "transaction.refund"


class ReconciliationStatus(str, enum.Enum):
    """Outcome of reconciling a payment event."""
    applied = "applied"  # Full amount applied to active loan
    partially_applied = "partially_applied"  # Amount split between loan and overpayment
    rejected = "rejected"  # Event not applied


class ReconciliationReason(str, enum.Enum):
    """Business reason for reconciliation outcome."""
    # Success reasons
    full_payment = "full_payment"
    partial_payment = "partial_payment"
    
    # Rejection reasons for payments
    active_loan_remainder = "active_loan_remainder"  # For partially_applied on active loan
    closed_loan_payment = "closed_loan_payment"  # Entire overpayment for closed loan
    unknown_loan = "unknown_loan"
    ambiguous_mapping = "ambiguous_mapping"
    identity_conflict = "identity_conflict"
    duplicate_payment = "duplicate_payment"
    invalid_amount = "invalid_amount"
    provider_status_not_final_success = "provider_status_not_final_success"
    provider_lookup_mismatch = "provider_lookup_mismatch"
    provider_lookup_not_found = "provider_lookup_not_found"
    
    # Reversal/refund reasons
    reversal_without_original = "reversal_without_original"
    reversal_already_applied = "reversal_already_applied"
    reversal_integrity = "reversal_integrity"
    refund_exceeds_balance = "refund_exceeds_balance"


class IssueType(str, enum.Enum):
    """Operational issue types."""
    identity_conflict = "identity_conflict"
    unknown_loan = "unknown_loan"
    ambiguous_mapping = "ambiguous_mapping"
    provider_lookup_failure = "provider_lookup_failure"
    reversal_integrity = "reversal_integrity"
    concurrent_payment = "concurrent_payment"


class IssueStatus(str, enum.Enum):
    """Issue lifecycle."""
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"


class OverpaymentStatus(str, enum.Enum):
    """Overpayment lifecycle."""
    active = "active"  # Has positive balance
    refunded = "refunded"  # Balance reached zero


class DeliveryStatus(str, enum.Enum):
    """Webhook delivery attempt outcome."""
    authenticated = "authenticated"
    unauthenticated = "unauthenticated"
    malformed = "malformed"
    invalid_content_type = "invalid_content_type"
    non_actionable = "non_actionable"  # Valid but provider status not final success
    lookup_retry = "lookup_retry"  # Transient lookup failure
    duplicate = "duplicate"  # Idempotent replay of prior event
    accepted = "accepted"  # Durably accepted, will be reconciled
