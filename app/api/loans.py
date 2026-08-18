"""Read endpoints for loans (provided — working)."""

from fastapi import APIRouter, Depends, HTTPException
from decimal import Decimal
from uuid import UUID

from app.api.dependencies import get_db
from app.adapters.persistence.sqlalchemy_backend.models import Loan
from .pagination import DEFAULT_PAGE_SIZE, chronological_page

router = APIRouter()


def _loan_out(loan: Loan) -> dict:
    return {
        "id": loan.id,
        "borrower_name": loan.borrower_name,
        "principal": float(loan.principal),
        "total_repayable": float(loan.total_repayable),
        "total_paid": float(loan.total_paid),
        "outstanding": float(loan.outstanding),
        "status": loan.status.value,
    }


@router.get("/loans")
def list_loans(cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE, db=Depends(get_db)):
    rows, next_cursor = chronological_page(db.query(Loan), Loan, Loan.disbursed_at, cursor, limit)
    return {"items": [_loan_out(loan) for loan in rows], "next_cursor": next_cursor}


@router.get("/loans/{loan_id}")
def get_loan(loan_id: str, db=Depends(get_db)):
    try:
        loan = db.get(Loan, UUID(loan_id))
    except ValueError:
        loan = None
    if loan is None:
        raise HTTPException(status_code=404, detail="loan not found")
    return _loan_out(loan)
