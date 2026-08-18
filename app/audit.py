"""Audit helper.

Every mutation on the platform must leave an audit record. This helper adds
the row to the CURRENT session so it commits in the SAME transaction as the
business change — a rollback discards both, a success persists both. Do not
commit here; the caller owns the transaction boundary.
"""

from sqlalchemy.orm import Session

from .models import AuditLog


def record_audit(
    db: Session,
    *,
    action: str,
    entity: str,
    entity_id,
    actor: str,
    detail: str | None = None,
    correlation_id: str | None = None,
) -> None:
    db.add(
        AuditLog(
            action=action,
            entity=entity,
            entity_id=str(entity_id),
            actor=actor,
            detail=detail,
            correlation_id=correlation_id,
        )
    )
