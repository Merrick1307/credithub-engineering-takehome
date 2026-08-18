"""Optional PostgreSQL race coverage; enable with TEST_POSTGRES_DATABASE_URL."""

import os
import json
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import pytest


@pytest.mark.skipif(not os.getenv("TEST_POSTGRES_DATABASE_URL"), reason="requires an isolated PostgreSQL database")
def test_postgres_skip_locked_allows_only_one_refund_worker_to_claim_a_command():
    """Exercise the actual PostgreSQL lease query under a concurrent claim."""
    from app.adapters.persistence.db import Base
    from app.adapters.persistence.sqlalchemy_backend.models import OutboxEvent
    from app.workers.work_queue import claim_outbox

    engine = create_engine(os.environ["TEST_POSTGRES_DATABASE_URL"])
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    session = sessions()
    command = OutboxEvent(
        event_type="overpayment.refund.requested", payload=json.dumps({"provider": "core_banking"}),
        correlation_id="concurrency", idempotency_key="postgres-concurrency-command",
        status="pending",
    )
    session.add(command); session.commit(); session.close()

    start = threading.Barrier(2)
    def claim(name):
        db = sessions()
        start.wait()
        item = claim_outbox(db, name, event_types={"overpayment.refund.requested"})
        db.commit(); db.close()
        return item

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("worker-a", "worker-b")))
    assert sum(item is not None for item in results) == 1
    engine.dispose()
