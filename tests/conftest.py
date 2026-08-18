import pytest
from uuid import UUID
from fastapi.testclient import TestClient

from app.adapters.persistence.db import Base, SessionLocal, engine
from app.api.dependencies import set_session_factory
from app.main import app
from app.adapters.persistence.sqlalchemy_backend.models import Loan, LoanStatus

ACTIVE_LOAN_UUID = UUID("00000000-0000-0000-0000-000000000001")
CLOSED_LOAN_UUID = UUID("00000000-0000-0000-0000-000000000002")
ACTIVE_LOAN_ID = str(ACTIVE_LOAN_UUID)
CLOSED_LOAN_ID = str(CLOSED_LOAN_UUID)
MISSING_LOAN_ID = "00000000-0000-0000-0000-000000000999"


@pytest.fixture()
def client():
    """Fresh DB per test.

    Loans: one active (outstanding 56000), one cancelled.
    No payment events — the webhook spec posts them in.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add_all([
        Loan(id=ACTIVE_LOAN_UUID, borrower_name="Test One", principal=50000, total_repayable=56000, total_paid=0, status=LoanStatus.active),
        Loan(id=CLOSED_LOAN_UUID, borrower_name="Closed", principal=10000, total_repayable=11000, total_paid=0, status=LoanStatus.cancelled),
    ])
    db.commit()
    db.close()
    
    # Initialize session factory for dependency injection
    set_session_factory(SessionLocal)
    
    return TestClient(app)
