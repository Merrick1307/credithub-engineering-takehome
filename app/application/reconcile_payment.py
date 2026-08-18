"""Application service for payment reconciliation.

This service orchestrates the business logic for accepting a canonical
financial event and producing a reconciliation result. It is framework-agnostic
and does not import FastAPI, SQLAlchemy ORM, or HTTP concepts.

The service is transaction-scoped: it either commits all changes or none.
"""

from decimal import Decimal
from typing import Optional
from datetime import datetime
import hashlib
import json

from ..domain.enums import (
    EventKind,
    ReconciliationStatus,
    ReconciliationReason,
    LoanStatus,
)
from ..domain.models import (
    Money,
    LoanBalance,
    CanonicalFinancialEvent,
    ReconciliationResult,
)
from ..ports.repositories import UnitOfWork
from ..ports.providers import ProviderRegistry, ProviderLookup
from ..models import PaymentStatus


class ReconcilePaymentUseCase:
    """Use case: receive a canonical financial event and reconcile it atomically.
    
    This is the core financial decision logic. All paths through this use case
    must either:
    1. Commit a complete reconciliation with loan updates and ledger rows, or
    2. Record a non-actionable delivery/issue without touching loan state.
    
    Concurrency: Lock the loan row before making financial decisions.
    """
    
    def __init__(
        self,
        unit_of_work: UnitOfWork,
        provider_registry: ProviderRegistry,
        provider_lookup: ProviderLookup,
    ):
        self.uow = unit_of_work
        self.provider_registry = provider_registry
        self.provider_lookup = provider_lookup
    
    def execute(
        self,
        canonical_event: CanonicalFinancialEvent,
        correlation_id: str,
    ) -> ReconciliationResult:
        """Execute reconciliation for a single financial event.
        
        Args:
            canonical_event: Provider-agnostic financial event after authentication.
            correlation_id: Unique request ID for audit trail.
        
        Returns:
            ReconciliationResult with outcome, amounts, and optional loan state.
        
        Raises:
            ValueError: Configuration or logical error (not a transient failure).
        """
        
        with self.uow:
            # Step 1: Check for idempotent replay
            idempotency_fingerprint = self._make_fingerprint(canonical_event)
            
            existing_event = self.uow.payment_events.get_event_by_identity(
                provider=canonical_event.provider,
                merchant_scope=canonical_event.merchant_scope,
                event_kind=canonical_event.event_kind,
                event_reference=canonical_event.event_reference,
            )
            
            if existing_event:
                # Identity exists; check fingerprint
                if existing_event.get("fingerprint") == idempotency_fingerprint:
                    # Exact replay: return stored result
                    return self._build_result_from_stored(existing_event, idempotent_replay=True)
                else:
                    # Different fingerprint: conflict
                    return ReconciliationResult(
                        event_id=existing_event.get("id"),
                        status=ReconciliationStatus.rejected,
                        reason=ReconciliationReason.identity_conflict,
                        gross_amount=canonical_event.gross_amount,
                        applied_amount=Money(Decimal(0), canonical_event.gross_amount.currency),
                        overpaid_amount=Money(Decimal(0), canonical_event.gross_amount.currency),
                        loan_id=None,
                        loan_status=None,
                        loan_outstanding=None,
                    )

            # Economic actions are positive amounts; reversals/refunds are
            # identified by their immutable event kind, never by a negative
            # credit amount.
            if not canonical_event.gross_amount.is_positive():
                return ReconciliationResult(
                    event_id=None,
                    status=ReconciliationStatus.rejected,
                    reason=ReconciliationReason.invalid_amount,
                    gross_amount=canonical_event.gross_amount,
                    applied_amount=Money(Decimal(0), canonical_event.gross_amount.currency),
                    overpaid_amount=Money(Decimal(0), canonical_event.gross_amount.currency),
                    loan_id=None,
                    loan_status=None,
                    loan_outstanding=None,
                )
            
            # Step 2: Perform provider lookup if configured
            provider_config = self.provider_registry.get_provider_config(canonical_event.provider)
            if provider_config.get("lookup_enabled"):
                lookup_result = self.provider_lookup.lookup_payment(
                    canonical_event.provider,
                    canonical_event,
                    provider_config,
                )
                if lookup_result["status"] == "mismatch":
                    return self._reject_lookup_mismatch(canonical_event, correlation_id, lookup_result)
                elif lookup_result["status"] == "not_found":
                    return self._reject_not_found(canonical_event, correlation_id)
                # else: "confirmed" or "transient_error" handled below
            
            # Step 3: Check if event is final-success
            if canonical_event.provider_status != "succeeded":
                # Non-actionable delivery; don't apply
                self.uow.outbox.record_outbox_event(
                    "payment.non_actionable",
                    {
                        "event_reference": canonical_event.event_reference,
                        "provider_status": canonical_event.provider_status,
                        "reason": "provider_status_not_final_success",
                    },
                    correlation_id,
                )
                return ReconciliationResult(
                    event_id=None,
                    status=ReconciliationStatus.rejected,
                    reason=ReconciliationReason.unknown_loan,  # Placeholder
                    gross_amount=canonical_event.gross_amount,
                    applied_amount=Money(Decimal(0), canonical_event.gross_amount.currency),
                    overpaid_amount=Money(Decimal(0), canonical_event.gross_amount.currency),
                    loan_id=None,
                    loan_status=None,
                    loan_outstanding=None,
                )
            
            # Step 4: Route by event kind
            if canonical_event.event_kind == EventKind.transaction_credit:
                return self._reconcile_payment(canonical_event, correlation_id)
            elif canonical_event.event_kind == EventKind.transaction_reversal:
                return self._reconcile_reversal(canonical_event, correlation_id)
            elif canonical_event.event_kind == EventKind.transaction_refund:
                return self._reconcile_refund(canonical_event, correlation_id)
            else:
                raise ValueError(f"Unknown event kind: {canonical_event.event_kind}")
    
    def _reconcile_payment(
        self,
        event: CanonicalFinancialEvent,
        correlation_id: str,
    ) -> ReconciliationResult:
        """Reconcile a transaction.credit event against a loan."""
        
        # Step 1: Find loan by merchant_scope
        loan_ids = self.uow.loans.get_loans_by_external_account(
            event.provider,
            event.merchant_scope,
        )
        
        if not loan_ids:
            return ReconciliationResult(
                event_id=None,
                status=ReconciliationStatus.rejected,
                reason=ReconciliationReason.unknown_loan,
                gross_amount=event.gross_amount,
                applied_amount=Money(Decimal(0), event.gross_amount.currency),
                overpaid_amount=Money(Decimal(0), event.gross_amount.currency),
                loan_id=None,
                loan_status=None,
                loan_outstanding=None,
            )
        
        if len(loan_ids) > 1:
            return ReconciliationResult(
                event_id=None,
                status=ReconciliationStatus.rejected,
                reason=ReconciliationReason.ambiguous_mapping,
                gross_amount=event.gross_amount,
                applied_amount=Money(Decimal(0), event.gross_amount.currency),
                overpaid_amount=Money(Decimal(0), event.gross_amount.currency),
                loan_id=None,
                loan_status=None,
                loan_outstanding=None,
            )
        
        loan_id = loan_ids[0]
        loan = self.uow.loans.get_loan_by_id(loan_id)
        
        if not loan:
            return ReconciliationResult(
                event_id=None,
                status=ReconciliationStatus.rejected,
                reason=ReconciliationReason.unknown_loan,
                gross_amount=event.gross_amount,
                applied_amount=Money(Decimal(0), event.gross_amount.currency),
                overpaid_amount=Money(Decimal(0), event.gross_amount.currency),
                loan_id=None,
                loan_status=None,
                loan_outstanding=None,
            )
        
        # Step 2: Check loan status
        if loan.status != LoanStatus.active:
            event_id = self.uow.payment_events.record_event(
                provider=event.provider,
                merchant_scope=event.merchant_scope,
                event_kind=event.event_kind,
                event_reference=event.event_reference,
                original_payment_reference=event.original_payment_reference,
                gross_amount=event.gross_amount.amount,
                provider_status=event.provider_status,
                provider_event_type=event.provider_event_type,
                provider_metadata=event.provider_metadata,
                timestamp=event.timestamp,
                idempotency_fingerprint=self._make_fingerprint(event),
            )
            overpayment = self.uow.overpayments.create(loan_id, event_id, event.gross_amount.amount)
            self.uow.loans.record_repayment_ledger(
                loan_id, event_id, event.gross_amount.amount,
                entry_type="overpayment",
                loan_balance_delta=Decimal(0),
                overpayment_balance_delta=event.gross_amount.amount,
                overpayment_id=overpayment["id"],
            )
            self.uow.payment_events.update_event_reconciliation(
                event_id, loan_id, ReconciliationStatus.rejected,
                ReconciliationReason.closed_loan_payment.value,
                Decimal(0), event.gross_amount.amount,
            )
            return ReconciliationResult(
                event_id=event_id,
                status=ReconciliationStatus.rejected,
                reason=ReconciliationReason.closed_loan_payment,
                gross_amount=event.gross_amount,
                applied_amount=Money(Decimal(0), event.gross_amount.currency),
                overpaid_amount=event.gross_amount,  # Entire amount is overpaid
                loan_id=loan_id,
                loan_status=LoanStatus(loan.status.value),
                loan_outstanding=Money(Decimal(str(loan.outstanding)), "NGN"),
            )
        
        # Step 3: Allocate payment
        outstanding = Money(Decimal(str(loan.outstanding)), "NGN")
        
        # Record event first
        event_id = self.uow.payment_events.record_event(
            provider=event.provider,
            merchant_scope=event.merchant_scope,
            event_kind=event.event_kind,
            event_reference=event.event_reference,
            original_payment_reference=event.original_payment_reference,
            gross_amount=event.gross_amount.amount,
            provider_status=event.provider_status,
            provider_event_type=event.provider_event_type,
            provider_metadata=event.provider_metadata,
            timestamp=event.timestamp,
            idempotency_fingerprint=self._make_fingerprint(event),
        )
        
        if event.gross_amount.amount > outstanding.amount:
            # Overpayment
            applied_amount = outstanding
            overpaid_amount = event.gross_amount - outstanding
            new_total_paid = Decimal(str(loan.total_paid)) + applied_amount.amount
            
            # Record repayment ledger
            self.uow.loans.record_repayment_ledger(
                loan_id, event_id, applied_amount.amount,
                loan_balance_delta=-applied_amount.amount,
            )
            overpayment = self.uow.overpayments.create(loan_id, event_id, overpaid_amount.amount)
            self.uow.loans.record_repayment_ledger(
                loan_id, event_id, overpaid_amount.amount,
                entry_type="overpayment",
                loan_balance_delta=Decimal(0),
                overpayment_balance_delta=overpaid_amount.amount,
                overpayment_id=overpayment["id"],
            )
            
            # Update loan
            self.uow.loans.update_loan_balance(
                loan_id,
                new_total_paid,
                LoanStatus.paid_off,  # Loan is now paid off
            )
            
            # Update event with reconciliation outcome
            self.uow.payment_events.update_event_reconciliation(
                event_id,
                loan_id,
                ReconciliationStatus.partially_applied,
                ReconciliationReason.active_loan_remainder.value,
                applied_amount.amount,
                overpaid_amount.amount,
            )
            
            return ReconciliationResult(
                event_id=event_id,
                status=ReconciliationStatus.partially_applied,
                reason=ReconciliationReason.active_loan_remainder,
                gross_amount=event.gross_amount,
                applied_amount=applied_amount,
                overpaid_amount=overpaid_amount,
                loan_id=loan_id,
                loan_status=LoanStatus.paid_off,
                loan_outstanding=Money(Decimal(0), "NGN"),
            )
        
        elif event.gross_amount.amount == outstanding.amount:
            # Exact payoff
            new_total_paid = Decimal(str(loan.total_paid)) + event.gross_amount.amount
            
            # Record repayment ledger
            self.uow.loans.record_repayment_ledger(
                loan_id, event_id, event.gross_amount.amount,
                loan_balance_delta=-event.gross_amount.amount,
            )
            
            # Update loan
            self.uow.loans.update_loan_balance(
                loan_id,
                new_total_paid,
                LoanStatus.paid_off,
            )
            
            # Update event
            self.uow.payment_events.update_event_reconciliation(
                event_id,
                loan_id,
                ReconciliationStatus.applied,
                ReconciliationReason.full_payment.value,
                event.gross_amount.amount,
                Decimal(0),
            )
            
            return ReconciliationResult(
                event_id=event_id,
                status=ReconciliationStatus.applied,
                reason=ReconciliationReason.full_payment,
                gross_amount=event.gross_amount,
                applied_amount=event.gross_amount,
                overpaid_amount=Money(Decimal(0), "NGN"),
                loan_id=loan_id,
                loan_status=LoanStatus.paid_off,
                loan_outstanding=Money(Decimal(0), "NGN"),
            )
        
        else:
            # Partial payment
            new_total_paid = Decimal(str(loan.total_paid)) + event.gross_amount.amount
            
            # Record repayment ledger
            self.uow.loans.record_repayment_ledger(
                loan_id, event_id, event.gross_amount.amount,
                loan_balance_delta=-event.gross_amount.amount,
            )
            
            # Update loan (stays active)
            self.uow.loans.update_loan_balance(
                loan_id,
                new_total_paid,
            )
            
            # Update event
            self.uow.payment_events.update_event_reconciliation(
                event_id,
                loan_id,
                ReconciliationStatus.applied,
                ReconciliationReason.full_payment.value,
                event.gross_amount.amount,
                Decimal(0),
            )
            
            new_outstanding = outstanding - event.gross_amount
            
            return ReconciliationResult(
                event_id=event_id,
                status=ReconciliationStatus.applied,
                reason=ReconciliationReason.full_payment,
                gross_amount=event.gross_amount,
                applied_amount=event.gross_amount,
                overpaid_amount=Money(Decimal(0), "NGN"),
                loan_id=loan_id,
                loan_status=LoanStatus.active,
                loan_outstanding=new_outstanding,
            )
    
    def _reconcile_reversal(
        self,
        event: CanonicalFinancialEvent,
        correlation_id: str,
    ) -> ReconciliationResult:
        """Reconcile a transaction.reversal event.

        A full reversal compensates every repayment/overpayment component of
        the original credit. The original event and its components are never
        modified.
        """

        if not event.original_payment_reference:
            return self._reject_reversal(event, ReconciliationReason.reversal_without_original)

        original_events = self.uow.payment_events.get_events_by_reference(
            event.original_payment_reference
        )
        original_event = next(
            (
                candidate
                for candidate in original_events
                if candidate.get("provider") == event.provider
                and candidate.get("merchant_scope") == event.merchant_scope
                and candidate.get("event_kind") == EventKind.transaction_credit.value
                and candidate.get("provider_status") == "succeeded"
            ),
            None,
        )
        if not original_event:
            return self._reject_reversal(event, ReconciliationReason.reversal_without_original)

        original_amount = Money(Decimal(str(original_event["amount"])), event.gross_amount.currency)
        components = self.uow.payment_events.get_ledger_components_for_event(original_event["id"])
        if not components or event.gross_amount != original_amount:
            return self._reject_reversal(event, ReconciliationReason.reversal_integrity)

        if self.uow.payment_events.get_successful_reversals_for_original_reference(
            event.provider, event.merchant_scope, event.original_payment_reference
        ):
            return self._reject_reversal(event, ReconciliationReason.reversal_already_applied)

        loan_id = original_event["loan_id"]
        loan = self.uow.loans.get_loan_by_id(loan_id)
        if not loan:
            return self._reject_reversal(event, ReconciliationReason.unknown_loan)

        for component in components:
            if component["entry_type"] == "overpayment":
                overpayment = self.uow.overpayments.get_by_payment_event(original_event["id"])
                if not overpayment or overpayment["refunded_amount"] > 0:
                    return self._reject_reversal(event, ReconciliationReason.reversal_integrity)

        event_id = self.uow.payment_events.record_event(
            provider=event.provider,
            merchant_scope=event.merchant_scope,
            event_kind=event.event_kind,
            event_reference=event.event_reference,
            original_payment_reference=event.original_payment_reference,
            gross_amount=event.gross_amount.amount,
            provider_status=event.provider_status,
            provider_event_type=event.provider_event_type,
            provider_metadata=event.provider_metadata,
            timestamp=event.timestamp,
            idempotency_fingerprint=self._make_fingerprint(event),
        )

        repayment_amount = Decimal(0)
        for component in components:
            amount = component["amount"]
            if component["entry_type"] == "repayment":
                repayment_amount += amount
                self.uow.loans.record_repayment_ledger(
                    loan_id, event_id, -amount,
                    entry_type="repayment_reversal",
                    loan_balance_delta=amount,
                    adjusts_repayment_id=component["id"],
                )
            elif component["entry_type"] == "overpayment":
                self.uow.overpayments.apply_reversal(component["overpayment_id"], amount)
                self.uow.loans.record_repayment_ledger(
                    loan_id, event_id, -amount,
                    entry_type="overpayment_reversal",
                    loan_balance_delta=Decimal(0),
                    overpayment_balance_delta=-amount,
                    overpayment_id=component["overpayment_id"],
                    adjusts_repayment_id=component["id"],
                )

        new_total_paid = max(Decimal(str(loan.total_paid)) - repayment_amount, Decimal(0))
        new_status = loan.status
        outstanding = Money(Decimal(str(loan.total_repayable)) - new_total_paid, "NGN")
        if loan.status == LoanStatus.paid_off and outstanding.amount > 0:
            new_status = LoanStatus.active

        self.uow.loans.update_loan_balance(loan_id, new_total_paid, new_status)
        self.uow.payment_events.update_event_reconciliation(
            event_id,
            loan_id,
            ReconciliationStatus.applied,
            ReconciliationReason.full_payment.value,
            repayment_amount,
            Decimal(0),
        )

        return ReconciliationResult(
            event_id=event_id,
            status=ReconciliationStatus.applied,
            reason=ReconciliationReason.full_payment,
            gross_amount=event.gross_amount,
            applied_amount=Money(repayment_amount, event.gross_amount.currency),
            overpaid_amount=Money(Decimal(0), "NGN"),
            loan_id=loan_id,
            loan_status=LoanStatus(new_status.value) if isinstance(new_status, LoanStatus) else new_status,
            loan_outstanding=outstanding,
        )

    @staticmethod
    def _reject_reversal(
        event: CanonicalFinancialEvent,
        reason: ReconciliationReason,
    ) -> ReconciliationResult:
        """Return a safe, non-mutating reversal rejection."""
        return ReconciliationResult(
            event_id=None,
            status=ReconciliationStatus.rejected,
            reason=reason,
            gross_amount=event.gross_amount,
            applied_amount=Money(Decimal(0), event.gross_amount.currency),
            overpaid_amount=Money(Decimal(0), event.gross_amount.currency),
            loan_id=None,
            loan_status=None,
            loan_outstanding=None,
        )
    
    def _reconcile_refund(
        self,
        event: CanonicalFinancialEvent,
        correlation_id: str,
    ) -> ReconciliationResult:
        """Consume an unapplied overpayment without changing a loan balance."""
        if not event.original_payment_reference:
            return self._reject_reversal(event, ReconciliationReason.refund_exceeds_balance)

        original_event = next(
            (
                candidate
                for candidate in self.uow.payment_events.get_events_by_reference(
                    event.original_payment_reference
                )
                if candidate.get("provider") == event.provider
                and candidate.get("merchant_scope") == event.merchant_scope
                and candidate.get("event_kind") == EventKind.transaction_credit.value
                and candidate.get("provider_status") == "succeeded"
            ),
            None,
        )
        if not original_event:
            return self._reject_reversal(event, ReconciliationReason.refund_exceeds_balance)

        loan_id = original_event["loan_id"]
        loan = self.uow.loans.get_loan_by_id(loan_id)
        overpayment = self.uow.overpayments.get_by_payment_event(original_event["id"])
        if not loan or not overpayment or event.gross_amount.amount > overpayment["remaining_amount"]:
            return self._reject_reversal(event, ReconciliationReason.refund_exceeds_balance)

        event_id = self.uow.payment_events.record_event(
            provider=event.provider,
            merchant_scope=event.merchant_scope,
            event_kind=event.event_kind,
            event_reference=event.event_reference,
            original_payment_reference=event.original_payment_reference,
            gross_amount=event.gross_amount.amount,
            provider_status=event.provider_status,
            provider_event_type=event.provider_event_type,
            provider_metadata=event.provider_metadata,
            timestamp=event.timestamp,
            idempotency_fingerprint=self._make_fingerprint(event),
        )
        self.uow.overpayments.apply_refund(overpayment["id"], event.gross_amount.amount)
        self.uow.loans.record_repayment_ledger(
            loan_id, event_id, -event.gross_amount.amount,
            entry_type="overpayment_refund",
            loan_balance_delta=Decimal(0),
            overpayment_balance_delta=-event.gross_amount.amount,
            overpayment_id=overpayment["id"],
        )
        self.uow.payment_events.update_event_reconciliation(
            event_id, loan_id, ReconciliationStatus.applied,
            ReconciliationReason.full_payment.value,
            Decimal(0), event.gross_amount.amount,
        )
        return ReconciliationResult(
            event_id=event_id,
            status=ReconciliationStatus.applied,
            reason=ReconciliationReason.full_payment,
            gross_amount=event.gross_amount,
            applied_amount=Money(Decimal(0), event.gross_amount.currency),
            overpaid_amount=event.gross_amount,
            loan_id=loan_id,
            loan_status=LoanStatus(loan.status.value),
            loan_outstanding=Money(Decimal(str(loan.outstanding)), event.gross_amount.currency),
        )
    
    def _reject_identity_conflict(
        self,
        event: CanonicalFinancialEvent,
        correlation_id: str,
        existing: dict,
    ) -> ReconciliationResult:
        """Handle identity conflict: same reference, different fingerprint."""
        # Record issue for operator review
        # Return stable rejected response
        raise NotImplementedError()
    
    def _reject_lookup_mismatch(
        self,
        event: CanonicalFinancialEvent,
        correlation_id: str,
        lookup_result: dict,
    ) -> ReconciliationResult:
        """Handle provider lookup mismatch."""
        raise NotImplementedError()
    
    def _reject_not_found(
        self,
        event: CanonicalFinancialEvent,
        correlation_id: str,
    ) -> ReconciliationResult:
        """Handle provider lookup terminal not-found."""
        raise NotImplementedError()
    
    def _build_result_from_stored(
        self,
        stored_event: dict,
        idempotent_replay: bool = False,
    ) -> ReconciliationResult:
        """Reconstruct result from a previously stored event."""
        status_str = stored_event.get("status")
        status = PaymentStatus(status_str) if status_str else PaymentStatus.pending
        loan_id = stored_event.get("loan_id")
        loan = self.uow.loans.get_loan_by_id(loan_id) if loan_id else None
        loan_status = LoanStatus(loan.status.value) if loan else None
        loan_outstanding = (
            Money(Decimal(str(loan.outstanding)), "NGN") if loan else None
        )
        
        # Reconstruct the result based on what's stored
        if status == PaymentStatus.applied:
            overpaid_amount = Money(Decimal(str(stored_event.get("overpaid_amount", 0))), "NGN")
            reconciliation_status = (
                ReconciliationStatus.partially_applied
                if overpaid_amount.amount > 0
                else ReconciliationStatus.applied
            )
            reason = (
                ReconciliationReason.active_loan_remainder
                if reconciliation_status == ReconciliationStatus.partially_applied
                else ReconciliationReason.full_payment
            )
            return ReconciliationResult(
                event_id=stored_event.get("id"),
                status=reconciliation_status,
                reason=reason,
                gross_amount=Money(Decimal(str(stored_event.get("amount", 0))), "NGN"),
                applied_amount=Money(Decimal(str(stored_event.get("applied_amount", 0))), "NGN"),
                overpaid_amount=overpaid_amount,
                loan_id=loan_id,
                loan_status=loan_status,
                loan_outstanding=loan_outstanding,
                idempotent_replay=idempotent_replay,
            )
        else:
            # Rejected
            try:
                reason = ReconciliationReason(stored_event.get("reason"))
            except ValueError:
                reason = ReconciliationReason.unknown_loan
            return ReconciliationResult(
                event_id=stored_event.get("id"),
                status=ReconciliationStatus.rejected,
                reason=reason,
                gross_amount=Money(Decimal(str(stored_event.get("amount", 0))), "NGN"),
                applied_amount=Money(Decimal(0), "NGN"),
                overpaid_amount=Money(Decimal(0), "NGN"),
                loan_id=loan_id,
                loan_status=loan_status,
                loan_outstanding=loan_outstanding,
                idempotent_replay=idempotent_replay,
            )
    
    @staticmethod
    def _make_idempotency_key(event: CanonicalFinancialEvent) -> str:
        """Create the unique identity key for an event."""
        return f"{event.provider}#{event.merchant_scope}#{event.event_kind.value}#{event.event_reference}"
    
    @staticmethod
    def _make_fingerprint(event: CanonicalFinancialEvent) -> str:
        """Create a stable fingerprint for idempotency conflict detection."""
        # Hash immutable fields: amount, original_payment_ref, timestamp
        data = {
            "gross_amount": str(event.gross_amount.amount),
            "currency": event.gross_amount.currency,
            "original_payment_reference": event.original_payment_reference,
            "timestamp": event.timestamp.isoformat(),
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
