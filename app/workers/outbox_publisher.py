"""Publish durable outbox events to the HTTP endpoint configured for their type."""

import json
import logging
import os
import time

import httpx

from app.adapters.persistence.db import SessionLocal
from .work_queue import claim_outbox, fail_outbox, finish_outbox, worker_id

logger = logging.getLogger(__name__)


class HttpNotificationPublisher:
    """HTTP adapter with exact event-type routes and an optional default route.

    ``OUTBOX_EVENT_URLS`` is a JSON object of exact event type to URL mappings.
    ``DOWNSTREAM_NOTIFICATION_URL`` remains the fallback for every unmapped type.
    """

    def __init__(self, default_url: str, event_urls: dict[str, str] | None = None, timeout_seconds: float = 10):
        self.default_url = default_url
        self.event_urls = event_urls or {}
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "HttpNotificationPublisher":
        raw_routes = os.getenv("OUTBOX_EVENT_URLS", "{}")
        try:
            event_urls = json.loads(raw_routes)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OUTBOX_EVENT_URLS must be a JSON object") from exc
        if not isinstance(event_urls, dict) or not all(
            isinstance(kind, str) and isinstance(url, str) and url
            for kind, url in event_urls.items()
        ):
            raise RuntimeError("OUTBOX_EVENT_URLS must map non-empty event types to non-empty URLs")
        return cls(os.getenv("DOWNSTREAM_NOTIFICATION_URL", ""), event_urls)

    def url_for(self, event_type: str) -> str:
        return self.event_urls.get(event_type, self.default_url)

    def configured_event_types(self) -> set[str] | None:
        """Return a claim filter, or ``None`` when the default route handles all."""
        return None if self.default_url else set(self.event_urls)

    def publish(self, event: dict) -> None:
        url = self.url_for(event["type"])
        if not url:
            raise RuntimeError(f"No downstream URL is configured for {event['type']}")
        response = httpx.post(url, json=event, timeout=self.timeout_seconds)
        response.raise_for_status()


class OutboxPublisher:
    def __init__(self, session_factory=SessionLocal, publisher=None, *, name: str | None = None):
        self.session_factory = session_factory
        self.publisher = publisher or HttpNotificationPublisher.from_environment()
        self.name = name or worker_id("outbox-publisher")
        self.max_attempts = int(os.getenv("OUTBOX_MAX_ATTEMPTS", "8"))
        self._reported_missing_url = False

    def run_once(self, limit: int = 20) -> int:
        # A local deployment can run before any consumer is provisioned. Leave
        # events pending rather than burning retries on a known configuration omission.
        event_types = None
        if isinstance(self.publisher, HttpNotificationPublisher):
            event_types = self.publisher.configured_event_types()
            if event_types == set():
                if not self._reported_missing_url:
                    logger.warning("No downstream event URL is configured; outbox events remain pending")
                    self._reported_missing_url = True
                return 0
        completed = 0
        for _ in range(limit):
            session = self.session_factory()
            try:
                item = claim_outbox(
                    session, self.name, event_types=event_types,
                    lease_seconds=int(os.getenv("WORKER_LEASE_SECONDS", "60")),
                )
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
            if not item:
                break
            try:
                self.publisher.publish({
                    "id": str(item["id"]), "type": item["event_type"],
                    "payload": json.loads(item["payload"]), "correlation_id": item["correlation_id"],
                })
                session = self.session_factory()
                finish_outbox(session, item["id"], self.name)
                session.commit(); session.close()
                completed += 1
            except Exception as exc:
                logger.exception("outbox delivery failed", extra={"outbox_id": str(item["id"]), "event_type": item["event_type"]})
                session = self.session_factory()
                fail_outbox(session, item["id"], self.name, exc, self.max_attempts)
                session.commit(); session.close()
        return completed


def main() -> None:
    logging.basicConfig(level=os.getenv("WORKER_LOG_LEVEL", "INFO"))
    worker = OutboxPublisher()
    interval = float(os.getenv("OUTBOX_PUBLISH_INTERVAL_SECONDS", "5"))
    while True:
        worker.run_once()
        time.sleep(interval)


if __name__ == "__main__":
    main()
