"""Lease-safe provider lookup retries that reuse the reconciliation use case."""

import json
import logging
import os
import time
from datetime import datetime
from decimal import Decimal

from app.adapters.persistence.sqlalchemy_backend.sqlalchemy_repositories import SQLAlchemyUnitOfWork
from ..application.reconcile_payment import ReconcilePaymentUseCase
from app.adapters.persistence.db import SessionLocal
from ..domain.enums import EventKind
from ..domain.models import CanonicalFinancialEvent, Money
from ..infrastructure.provider_registry import NoOpProviderLookup, SimpleProviderRegistry
from .work_queue import claim_lookup_retry, fail_lookup_retry, finish_lookup_retry, worker_id

logger = logging.getLogger(__name__)


def event_from_payload(provider: str, raw_payload: str) -> CanonicalFinancialEvent:
    payload = json.loads(raw_payload)
    return CanonicalFinancialEvent(
        provider=provider, event_kind=EventKind(payload["event_kind"]),
        event_reference=payload["event_reference"], original_payment_reference=payload.get("original_payment_reference"),
        gross_amount=Money(Decimal(payload["gross_amount"]), payload.get("currency", "NGN")),
        provider_status=payload["provider_status"], merchant_scope=payload["merchant_scope"],
        timestamp=datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00")),
        provider_metadata=payload.get("provider_metadata", {}), provider_event_type=payload["provider_event_type"],
    )


class LookupRetryRunner:
    """Claims retry records and delegates all financial work to the use case."""

    def __init__(self, session_factory=SessionLocal, registry=None, lookup=None, *, name: str | None = None):
        self.session_factory = session_factory
        self.registry = registry or SimpleProviderRegistry()
        self.lookup = lookup or NoOpProviderLookup()
        self.name = name or worker_id("lookup-retry")
        self.max_attempts = int(os.getenv("LOOKUP_RETRY_MAX_ATTEMPTS", "8"))

    def run_once(self, limit: int = 20) -> int:
        completed = 0
        for _ in range(limit):
            session = self.session_factory()
            try:
                item = claim_lookup_retry(session, self.name, int(os.getenv("WORKER_LEASE_SECONDS", "60")))
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
            if not item:
                break
            try:
                event = event_from_payload(item["provider"], item["canonical_payload"])
                verification = self.lookup.lookup_payment(item["provider"], event, self.registry.get_provider_config(item["provider"]))
                if verification.get("status") != "confirmed":
                    raise ValueError(verification.get("reason", verification.get("status", "lookup failed")))
                result = ReconcilePaymentUseCase(
                    SQLAlchemyUnitOfWork(self.session_factory), self.registry, self.lookup
                ).execute(event, f"lookup-retry-{item['id']}-{item['attempts']}")
                session = self.session_factory()
                finish_lookup_retry(session, item["id"], self.name, result.event_id)
                session.commit(); session.close()
                completed += 1
            except Exception as exc:
                logger.exception("provider lookup retry failed", extra={"retry_id": str(item["id"])})
                session = self.session_factory()
                fail_lookup_retry(session, item["id"], self.name, exc, self.max_attempts)
                session.commit(); session.close()
        return completed


def main() -> None:
    logging.basicConfig(level=os.getenv("WORKER_LOG_LEVEL", "INFO"))
    worker = LookupRetryRunner()
    interval = float(os.getenv("LOOKUP_RETRY_INTERVAL_SECONDS", "30"))
    while True:
        worker.run_once()
        time.sleep(interval)


if __name__ == "__main__":
    main()
