"""Staff-only reconciliation query and manual provider-lookup retry APIs."""

from datetime import datetime, timezone
from decimal import Decimal
import hmac
import json
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import asc, desc

from ..audit import record_audit
from ..adapters.persistence.sqlalchemy_repositories import SQLAlchemyUnitOfWork
from ..application.reconcile_payment import ReconcilePaymentUseCase
from ..dependencies import get_db
from ..domain.enums import EventKind
from ..domain.models import CanonicalFinancialEvent, Money
from ..models import (
    AuditLog, OutboxEvent, Overpayment, PaymentEvent, ProviderLookupRetry,
    ReconciliationIssue, Repayment, WebhookDelivery,
)
from .pagination import DEFAULT_PAGE_SIZE, chronological_page

router = APIRouter(prefix="/admin", tags=["admin"])
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "dev-admin-secret")


def require_admin(request: Request) -> str:
    token = request.headers.get("x-admin-token", "")
    if not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="Staff authentication required")
    return "admin"


def money(value) -> str:
    return format(Decimal(str(value or 0)).quantize(Decimal("0.01")), "f")


def event_out(event: PaymentEvent) -> dict:
    return {
        "id": event.id,
        "reference": event.external_ref,
        "provider": event.provider,
        "merchant_scope": event.merchant_scope,
        "kind": event.event_kind,
        "original_payment_reference": event.original_payment_reference,
        "provider_status": event.provider_status,
        "status": event.status.value,
        "reason": event.reason,
        "loan_id": event.loan_id,
        "gross_amount": money(event.amount),
        "applied_amount": money(event.applied_amount),
        "overpaid_amount": money(event.overpaid_amount),
        "received_at": event.received_at.isoformat() if event.received_at else None,
        "processed_at": event.processed_at.isoformat() if event.processed_at else None,
    }


@router.get("/reconciliation/summary")
def summary(
    provider: Optional[str] = None,
    status: Optional[str] = None,
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(PaymentEvent)
    if provider:
        query = query.filter(PaymentEvent.provider == provider)
    if status:
        query = query.filter(PaymentEvent.status == status)
    events = query.all()
    total = len(events)
    applied = [event for event in events if event.status.value == "applied"]
    rejected = [event for event in events if event.status.value == "rejected"]
    active_overpayments = db.query(Overpayment).filter(Overpayment.status == "active").all()
    return {
        "counts": {"total": total, "applied": len(applied), "rejected": len(rejected), "open_issues": db.query(ReconciliationIssue).filter(ReconciliationIssue.status == "open").count()},
        "amounts": {
            "gross_received": money(sum((event.amount for event in events), Decimal(0))),
            "applied": money(sum((event.applied_amount for event in events), Decimal(0))),
            "overpaid": money(sum((event.overpaid_amount for event in events), Decimal(0))),
            "active_overpayments": money(sum((item.remaining_amount for item in active_overpayments), Decimal(0))),
        },
        "rejection_rate": money(Decimal(len(rejected) * 100) / Decimal(total)) if total else "0.00",
    }


@router.get("/reconciliation/events")
def list_events(
    provider: Optional[str] = None,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    loan_id: Optional[str] = None,
    reference: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = DEFAULT_PAGE_SIZE,
    sort: str = "received_at",
    direction: str = "desc",
    _: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    query = db.query(PaymentEvent)
    if provider: query = query.filter(PaymentEvent.provider == provider)
    if status: query = query.filter(PaymentEvent.status == status)
    if kind: query = query.filter(PaymentEvent.event_kind == kind)
    if loan_id: query = query.filter(PaymentEvent.loan_id == loan_id)
    if reference: query = query.filter(PaymentEvent.external_ref.contains(reference))
    sortable = {"received_at": PaymentEvent.received_at, "amount": PaymentEvent.amount, "status": PaymentEvent.status, "provider": PaymentEvent.provider}
    if sort not in sortable or direction not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid sort or direction")
    query = query.order_by(asc(sortable[sort]) if direction == "asc" else desc(sortable[sort]))
    rows, next_cursor = chronological_page(query, PaymentEvent, PaymentEvent.received_at, cursor, limit)
    return {"items": [event_out(row) for row in rows], "next_cursor": next_cursor}


@router.get("/reconciliation/events/{event_id}")
def event_detail(event_id: str, _: str = Depends(require_admin), db: Session = Depends(get_db)):
    event = db.get(PaymentEvent, event_id)
    if not event: raise HTTPException(status_code=404, detail="Event not found")
    overpayment = db.query(Overpayment).filter(Overpayment.payment_event_id == event.id).first()
    return {
        "event": event_out(event),
        "ledger": [{"id": row.id, "type": row.entry_type, "amount": money(row.amount), "loan_balance_delta": money(row.loan_balance_delta), "overpayment_balance_delta": money(row.overpayment_balance_delta), "created_at": row.created_at.isoformat() if row.created_at else None} for row in db.query(Repayment).filter(Repayment.payment_event_id == event.id).order_by(Repayment.id).all()],
        "overpayment": None if not overpayment else {"id": overpayment.id, "status": overpayment.status, "amount": money(overpayment.amount), "remaining_amount": money(overpayment.remaining_amount), "refunded_amount": money(overpayment.refunded_amount), "reversed_amount": money(overpayment.reversed_amount)},
        "deliveries": [{"id": item.id, "status": item.delivery_status, "received_at": item.received_at.isoformat() if item.received_at else None} for item in db.query(WebhookDelivery).filter(WebhookDelivery.payment_event_id == event.id).all()],
        "issues": [{"id": item.id, "status": item.status, "reason": item.reason} for item in db.query(ReconciliationIssue).filter(ReconciliationIssue.payment_event_id == event.id).all()],
        "audit": [{"id": item.id, "action": item.action, "actor": item.actor, "detail": item.detail, "created_at": item.created_at.isoformat()} for item in db.query(AuditLog).filter(AuditLog.entity_id == str(event.id)).all()],
    }


@router.get("/reconciliation/issues")
def issues(status: str = "open", cursor: Optional[str] = None, limit: int = DEFAULT_PAGE_SIZE, _: str = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(ReconciliationIssue).filter(ReconciliationIssue.status == status)
    rows, next_cursor = chronological_page(query, ReconciliationIssue, ReconciliationIssue.created_at, cursor, limit)
    return {"items": [{"id": item.id, "type": item.issue_type, "reason": item.reason, "status": item.status, "loan_id": item.loan_id, "payment_event_id": item.payment_event_id, "created_at": item.created_at.isoformat()} for item in rows], "next_cursor": next_cursor}


@router.get("/reconciliation/overpayments")
def overpayments(status: Optional[str] = None, cursor: Optional[str] = None, limit: int = DEFAULT_PAGE_SIZE, _: str = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(Overpayment)
    if status: query = query.filter(Overpayment.status == status)
    rows, next_cursor = chronological_page(query, Overpayment, Overpayment.created_at, cursor, limit)
    return {"items": [{"id": item.id, "loan_id": item.loan_id, "payment_event_id": item.payment_event_id, "status": item.status, "amount": money(item.amount), "remaining_amount": money(item.remaining_amount), "refunded_amount": money(item.refunded_amount), "reversed_amount": money(item.reversed_amount)} for item in rows], "next_cursor": next_cursor}


@router.get("/audit-log")
def audit_log(cursor: Optional[str] = None, limit: int = DEFAULT_PAGE_SIZE, _: str = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(AuditLog)
    rows, next_cursor = chronological_page(query, AuditLog, AuditLog.created_at, cursor, limit)
    return {"items": [{"id": row.id, "action": row.action, "entity": row.entity, "entity_id": row.entity_id, "actor": row.actor, "detail": row.detail, "created_at": row.created_at.isoformat()} for row in rows], "next_cursor": next_cursor}


@router.get("/reconciliation/provider-lookups")
def lookup_retries(status: str = "pending", cursor: Optional[str] = None, limit: int = DEFAULT_PAGE_SIZE, _: str = Depends(require_admin), db: Session = Depends(get_db)):
    query = db.query(ProviderLookupRetry).filter(ProviderLookupRetry.status == status)
    rows, next_cursor = chronological_page(query, ProviderLookupRetry, ProviderLookupRetry.created_at, cursor, limit)
    return {"items": [{"id": row.id, "provider": row.provider, "status": row.status, "attempts": row.attempts, "last_error": row.last_error, "created_at": row.created_at.isoformat()} for row in rows], "next_cursor": next_cursor}


@router.post("/reconciliation/provider-lookups/{retry_id}/retry")
def retry_lookup(retry_id: UUID, request: Request, actor: str = Depends(require_admin), db: Session = Depends(get_db)):
    retry = db.get(ProviderLookupRetry, retry_id)
    if not retry: raise HTTPException(status_code=404, detail="Lookup retry not found")
    if retry.status == "completed": raise HTTPException(status_code=409, detail="Lookup retry already completed")
    retry.attempts += 1
    retry.updated_at = datetime.now(timezone.utc)
    registry = request.app.state.provider_registry
    lookup = request.app.state.provider_lookup
    try:
        payload = json.loads(retry.canonical_payload)
        event = CanonicalFinancialEvent(provider=retry.provider, event_kind=EventKind(payload["event_kind"]), event_reference=payload["event_reference"], original_payment_reference=payload.get("original_payment_reference"), gross_amount=Money(Decimal(payload["gross_amount"]), payload.get("currency", "NGN")), provider_status=payload["provider_status"], merchant_scope=payload["merchant_scope"], timestamp=datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00")), provider_metadata=payload.get("provider_metadata", {}), provider_event_type=payload["provider_event_type"])
        outcome = lookup.lookup_payment(retry.provider, event, registry.get_provider_config(retry.provider))
        if outcome.get("status") != "confirmed":
            raise ValueError(outcome.get("reason", outcome.get("status", "lookup failed")))
        result = ReconcilePaymentUseCase(
            SQLAlchemyUnitOfWork(request.app.state.session_factory), registry, lookup
        ).execute(event, f"admin-retry-{retry.id}-{retry.attempts}")
        retry.status = "completed"
        retry.payment_event_id = result.event_id
        retry.last_error = None
        if retry.issue_id:
            issue = db.get(ReconciliationIssue, retry.issue_id)
            if issue: issue.status, issue.resolved_at = "resolved", datetime.now(timezone.utc)
        record_audit(db, action="provider_lookup.retry", entity="provider_lookup_retry", entity_id=retry.id, actor=actor, detail="confirmed by manual retry")
        db.commit()
        return {"id": retry.id, "status": retry.status, "attempts": retry.attempts, "payment_event_id": retry.payment_event_id}
    except Exception as exc:
        retry.status, retry.last_error = "pending", str(exc)
        db.commit()
        raise HTTPException(status_code=422, detail="Provider lookup retry failed")
