"""SQLAlchemy persistence models."""
import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import relationship
from app.adapters.persistence.db import Base


def _utcnow(): return datetime.now(timezone.utc)

class LoanStatus(str, enum.Enum):
    active = "active"; paid_off = "paid_off"; cancelled = "cancelled"; written_off = "written_off"
class PaymentStatus(str, enum.Enum):
    pending = "pending"; applied = "applied"; rejected = "rejected"

class Loan(Base):
    __tablename__ = "loans"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    borrower_name = Column(String, nullable=False)
    principal = Column(Numeric(20, 2), nullable=False)
    total_repayable = Column(Numeric(20, 2), nullable=False)
    total_paid = Column(Numeric(20, 2), nullable=False, default=Decimal("0"))
    status = Column(Enum(LoanStatus), nullable=False, default=LoanStatus.active)
    disbursed_at = Column(DateTime, default=_utcnow)
    @property
    def outstanding(self): return self.total_repayable - self.total_paid

class PaymentEvent(Base):
    __tablename__ = "payment_events"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    external_ref = Column(String, nullable=False)
    loan_id = Column(Uuid, ForeignKey("loans.id"), nullable=False)
    amount = Column(Numeric(20, 2), nullable=False)
    channel = Column(String, nullable=False, default="paystack")
    provider = Column(String, nullable=False, default="paystack")
    merchant_scope = Column(String, nullable=False, default="")
    event_kind = Column(String, nullable=False, default="transaction.credit")
    original_payment_reference = Column(String)
    provider_status = Column(String, nullable=False, default="succeeded")
    fingerprint = Column(String)
    applied_amount = Column(Numeric(20, 2), nullable=False, default=Decimal("0"))
    overpaid_amount = Column(Numeric(20, 2), nullable=False, default=Decimal("0"))
    status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.pending)
    reason = Column(String)
    received_at = Column(DateTime, default=_utcnow)
    processed_at = Column(DateTime)
    repayments = relationship("Repayment", back_populates="payment_event")

class Repayment(Base):
    __tablename__ = "repayments"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    loan_id = Column(Uuid, ForeignKey("loans.id"), nullable=False)
    payment_event_id = Column(Uuid, ForeignKey("payment_events.id"))
    amount = Column(Numeric(20, 2), nullable=False)
    entry_type = Column(String, nullable=False, default="repayment")
    loan_balance_delta = Column(Numeric(20, 2), nullable=False, default=Decimal("0"))
    overpayment_balance_delta = Column(Numeric(20, 2), nullable=False, default=Decimal("0"))
    overpayment_id = Column(Uuid, ForeignKey("overpayments.id"))
    adjusts_repayment_id = Column(Uuid, ForeignKey("repayments.id"))
    created_at = Column(DateTime, default=_utcnow)
    loan = relationship("Loan"); payment_event = relationship("PaymentEvent", back_populates="repayments")

class Overpayment(Base):
    __tablename__ = "overpayments"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    loan_id = Column(Uuid, ForeignKey("loans.id"), nullable=False)
    payment_event_id = Column(Uuid, ForeignKey("payment_events.id"), nullable=False, unique=True)
    amount = Column(Numeric(20, 2), nullable=False); refunded_amount = Column(Numeric(20, 2), nullable=False, default=Decimal("0")); reversed_amount = Column(Numeric(20, 2), nullable=False, default=Decimal("0")); status = Column(String, nullable=False, default="active"); created_at = Column(DateTime, default=_utcnow)
    @property
    def remaining_amount(self): return self.amount - self.refunded_amount - self.reversed_amount

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4); action = Column(String, nullable=False); entity = Column(String, nullable=False); entity_id = Column(String, nullable=False); actor = Column(String, nullable=False); detail = Column(String); correlation_id = Column(String); created_at = Column(DateTime, default=_utcnow)
class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4); provider = Column(String, nullable=False); delivery_status = Column(String, nullable=False); payload_digest = Column(String, nullable=False); payment_event_id = Column(Uuid, ForeignKey("payment_events.id")); correlation_id = Column(String, nullable=False); detail = Column(Text); received_at = Column(DateTime, default=_utcnow, nullable=False)
class ReconciliationIssue(Base):
    __tablename__ = "reconciliation_issues"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4); issue_type = Column(String, nullable=False); status = Column(String, nullable=False, default="open"); reason = Column(String, nullable=False); payment_event_id = Column(Uuid, ForeignKey("payment_events.id")); loan_id = Column(Uuid, ForeignKey("loans.id")); overpayment_id = Column(Uuid, ForeignKey("overpayments.id")); assigned_to = Column(String); resolution_note = Column(Text); created_at = Column(DateTime, default=_utcnow, nullable=False); resolved_at = Column(DateTime)
class ProviderLookupRetry(Base):
    __tablename__ = "provider_lookup_retries"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4); provider = Column(String, nullable=False); canonical_payload = Column(Text, nullable=False); status = Column(String, nullable=False, default="pending"); attempts = Column(Integer, nullable=False, default=0); last_error = Column(Text); next_attempt_at = Column(DateTime); lease_expires_at = Column(DateTime); leased_by = Column(String); payment_event_id = Column(Uuid, ForeignKey("payment_events.id")); issue_id = Column(Uuid, ForeignKey("reconciliation_issues.id")); created_at = Column(DateTime, default=_utcnow, nullable=False); updated_at = Column(DateTime, default=_utcnow, nullable=False)
class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id = Column(Uuid, primary_key=True, default=uuid.uuid4); event_type = Column(String, nullable=False); payload = Column(Text, nullable=False); correlation_id = Column(String, nullable=False); idempotency_key = Column(String, nullable=True, unique=True); status = Column(String, nullable=False, default="pending"); available_at = Column(DateTime, nullable=False, default=_utcnow); lease_expires_at = Column(DateTime); leased_by = Column(String); published_at = Column(DateTime); attempts = Column(Integer, nullable=False, default=0); last_error = Column(Text); created_at = Column(DateTime, default=_utcnow, nullable=False); updated_at = Column(DateTime, default=_utcnow, nullable=False)
