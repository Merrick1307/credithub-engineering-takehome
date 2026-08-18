import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.dependencies import set_session_factory
from app.main import app
from app.models import Loan, LoanStatus


@pytest.fixture()
def client():
    """Fresh DB per test.

    Loans: #1 active (outstanding 56000), #2 cancelled.
    No payment events — the webhook spec posts them in.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add_all([
        Loan(id=1, borrower_name="Test One", principal=50000, total_repayable=56000, total_paid=0, status=LoanStatus.active),
        Loan(id=2, borrower_name="Closed", principal=10000, total_repayable=11000, total_paid=0, status=LoanStatus.cancelled),
    ])
    db.commit()
    db.close()
    
    # Initialize session factory for dependency injection
    set_session_factory(SessionLocal)
    
    return TestClient(app)
