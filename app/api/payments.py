"""Payment ingestion + reconciliation.

Provided (working): the payments feed (``GET /payment-events``).

The webhook is now implemented in main.py using the new architecture.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..dependencies import get_db
from ..models import PaymentEvent
from .pagination import DEFAULT_PAGE_SIZE, chronological_page

router = APIRouter()


class PaymentIn(BaseModel):
    external_ref: str
    loan_id: int
    amount: float
    channel: str = "paystack"


def _event_out(e: PaymentEvent) -> dict:
    return {
        "id": e.id,
        "external_ref": e.external_ref,
        "loan_id": e.loan_id,
        "amount": float(e.amount),
        "channel": e.channel,
        "status": e.status.value,
        "reason": e.reason,
        "received_at": e.received_at.isoformat() if e.received_at else None,
        "processed_at": e.processed_at.isoformat() if e.processed_at else None,
    }


@router.get("/payment-events")
def list_payment_events(cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE, db=Depends(get_db)):
    """The payments feed (newest first) — provided."""
    rows, next_cursor = chronological_page(db.query(PaymentEvent), PaymentEvent, PaymentEvent.received_at, cursor, limit)
    return {"items": [_event_out(event) for event in rows], "next_cursor": next_cursor}