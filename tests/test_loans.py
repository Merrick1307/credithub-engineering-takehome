"""Provided, passing tests for the read endpoints. Leave these green."""

from conftest import ACTIVE_LOAN_ID, MISSING_LOAN_ID


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_list_and_get_loan(client):
    loans = client.get("/loans").json()
    assert len(loans) == 2

    loan = client.get(f"/loans/{ACTIVE_LOAN_ID}").json()
    assert loan["outstanding"] == 56000
    assert loan["status"] == "active"


def test_get_missing_loan_returns_404(client):
    assert client.get(f"/loans/{MISSING_LOAN_ID}").status_code == 404
