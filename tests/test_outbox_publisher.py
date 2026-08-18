from app.workers.outbox_publisher import HttpNotificationPublisher


class _Response:
    def raise_for_status(self):
        return None


def test_exact_event_type_route_overrides_the_default_url(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return _Response()

    monkeypatch.setattr("app.workers.outbox_publisher.httpx.post", post)
    publisher = HttpNotificationPublisher(
        "https://events.example.test/generic",
        {"overpayment.refund.requested": "https://refunds.example.test/commands"},
    )

    publisher.publish({"type": "payment.reconciled.v1"})
    publisher.publish({"type": "overpayment.refund.requested"})

    assert [url for url, _ in calls] == [
        "https://events.example.test/generic",
        "https://refunds.example.test/commands",
    ]
