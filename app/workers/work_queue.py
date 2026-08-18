"""Small lease-based queue primitives shared by all worker processes."""

from datetime import datetime, timedelta, timezone
import os
import socket
import uuid

from sqlalchemy import and_, or_

from app.adapters.persistence.sqlalchemy_backend.models import OutboxEvent, ProviderLookupRetry, ReconciliationIssue


REFUND_COMMAND = "overpayment.refund.requested"


def utcnow():
    return datetime.now(timezone.utc)


def worker_id(name: str) -> str:
    return f"{name}:{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def retry_delay(attempts: int) -> timedelta:
    """Bounded exponential backoff, with no hidden in-memory retry state."""
    return timedelta(seconds=min(300, 2 ** min(attempts, 8)))


def claim_outbox(
    session,
    claimant: str,
    *,
    event_types: set[str] | None = None,
    lease_seconds: int = 60,
):
    """Claim one due outbox event, optionally restricted to exact event types."""
    now = utcnow()
    eligible = or_(
        and_(OutboxEvent.status == "pending", OutboxEvent.available_at <= now),
        and_(OutboxEvent.status == "processing", OutboxEvent.lease_expires_at < now),
    )
    query = session.query(OutboxEvent).filter(eligible)
    if event_types is not None:
        query = query.filter(OutboxEvent.event_type.in_(event_types))
    row = query.order_by(
        OutboxEvent.available_at, OutboxEvent.created_at
    ).with_for_update(skip_locked=True).first()
    if not row:
        return None
    row.status = "processing"
    row.leased_by = claimant
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    row.attempts += 1
    row.updated_at = now
    session.flush()
    return {
        "id": row.id, "event_type": row.event_type, "payload": row.payload,
        "correlation_id": row.correlation_id, "attempts": row.attempts,
    }


def finish_outbox(session, outbox_id, claimant: str) -> bool:
    row = session.get(OutboxEvent, outbox_id)
    if not row or row.status != "processing" or row.leased_by != claimant:
        return False
    row.status = "published"
    row.published_at = utcnow()
    row.lease_expires_at = None
    row.leased_by = None
    row.last_error = None
    row.updated_at = utcnow()
    return True


def fail_outbox(session, outbox_id, claimant: str, error: Exception, max_attempts: int) -> bool:
    row = session.get(OutboxEvent, outbox_id)
    if not row or row.status != "processing" or row.leased_by != claimant:
        return False
    now = utcnow()
    row.last_error = str(error)[:4000]
    row.lease_expires_at = None
    row.leased_by = None
    row.updated_at = now
    if row.attempts >= max_attempts:
        row.status = "failed"
        session.add(ReconciliationIssue(
            issue_type="worker_delivery_failure",
            reason=f"{row.event_type} exhausted retries: {row.last_error}"[:4000],
        ))
    else:
        row.status = "pending"
        row.available_at = now + retry_delay(row.attempts)
    return True


def claim_lookup_retry(session, claimant: str, lease_seconds: int = 60):
    now = utcnow()
    eligible = or_(
        and_(ProviderLookupRetry.status == "pending", or_(ProviderLookupRetry.next_attempt_at.is_(None), ProviderLookupRetry.next_attempt_at <= now)),
        and_(ProviderLookupRetry.status == "processing", ProviderLookupRetry.lease_expires_at < now),
    )
    row = session.query(ProviderLookupRetry).filter(eligible).order_by(
        ProviderLookupRetry.next_attempt_at, ProviderLookupRetry.created_at
    ).with_for_update(skip_locked=True).first()
    if not row:
        return None
    row.status = "processing"
    row.leased_by = claimant
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    row.attempts += 1
    row.updated_at = now
    session.flush()
    return {"id": row.id, "provider": row.provider, "canonical_payload": row.canonical_payload, "attempts": row.attempts}


def finish_lookup_retry(session, retry_id, claimant: str, payment_event_id) -> bool:
    row = session.get(ProviderLookupRetry, retry_id)
    if not row or row.status != "processing" or row.leased_by != claimant:
        return False
    row.status, row.payment_event_id = "completed", payment_event_id
    row.last_error, row.lease_expires_at, row.leased_by = None, None, None
    row.updated_at = utcnow()
    if row.issue_id:
        issue = session.get(ReconciliationIssue, row.issue_id)
        if issue:
            issue.status, issue.resolved_at = "resolved", utcnow()
    return True


def fail_lookup_retry(session, retry_id, claimant: str, error: Exception, max_attempts: int) -> bool:
    row = session.get(ProviderLookupRetry, retry_id)
    if not row or row.status != "processing" or row.leased_by != claimant:
        return False
    now = utcnow()
    row.last_error = str(error)[:4000]
    row.lease_expires_at, row.leased_by, row.updated_at = None, None, now
    if row.attempts >= max_attempts:
        row.status = "failed"
        if row.issue_id:
            issue = session.get(ReconciliationIssue, row.issue_id)
            if issue:
                issue.status = "open"
        else:
            session.add(ReconciliationIssue(issue_type="provider_lookup_failure", reason=row.last_error))
    else:
        row.status = "pending"
        row.next_attempt_at = now + retry_delay(row.attempts)
    return True
