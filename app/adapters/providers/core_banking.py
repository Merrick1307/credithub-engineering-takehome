"""Minimal internal core-banking webhook adapter.

The adapter intentionally follows the same authenticate/decode/normalize
contract as the mock provider so later lender rails need no reconciliation
branching.
"""

from datetime import datetime, timezone
from decimal import Decimal
import hmac
import json

from ...domain.enums import EventKind
from ...domain.models import CanonicalFinancialEvent, Money
from ...ports.providers import ProviderAuthenticator, ProviderDecoder, ProviderNormalizer


class CoreBankingAuthenticator(ProviderAuthenticator):
    """Authenticate an internal callback using a configured bearer token."""

    def verify_signature(self, provider: str, raw_body: bytes, headers: dict, config: dict) -> bool:
        supplied = headers.get("x-core-banking-token", "")
        expected = config.get("secret_key", "")
        return bool(expected) and hmac.compare_digest(supplied, expected)


class CoreBankingDecoder(ProviderDecoder):
    def get_supported_media_types(self, provider: str) -> list[str]:
        return ["application/json"]

    def decode_payload(self, provider: str, content_type: str, raw_body: bytes) -> dict:
        if content_type != "application/json":
            raise ValueError(f"Unsupported content type: {content_type}")
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid JSON: {exc}") from exc
        for field in ("notification_id", "account_id", "amount", "status", "event"):
            if field not in payload:
                raise ValueError(f"Missing required field: {field}")
        return payload


class CoreBankingNormalizer(ProviderNormalizer):
    EVENT_KIND = {
        "payment.posted": EventKind.transaction_credit,
        "payment.reversed": EventKind.transaction_reversal,
        "overpayment.refunded": EventKind.transaction_refund,
    }

    def normalize(self, provider: str, provider_dto: dict, provider_config: dict) -> CanonicalFinancialEvent:
        event_label = provider_dto["event"]
        if event_label not in self.EVENT_KIND:
            raise ValueError(f"Unsupported core-banking event: {event_label}")
        try:
            amount = Decimal(str(provider_dto["amount"]))
            if amount <= 0 or amount.as_tuple().exponent < -2:
                raise ValueError("amount must be a positive two-decimal value")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid amount: {exc}") from exc
        try:
            timestamp = datetime.fromisoformat(provider_dto.get("occurred_at", "").replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            timestamp = datetime.now(timezone.utc)
        return CanonicalFinancialEvent(
            provider=provider,
            event_kind=self.EVENT_KIND[event_label],
            event_reference=str(provider_dto["notification_id"]),
            original_payment_reference=provider_dto.get("original_notification_id"),
            gross_amount=Money(amount, provider_dto.get("currency", "NGN")),
            provider_status="succeeded" if provider_dto["status"] == "posted" else provider_dto["status"],
            merchant_scope=str(provider_dto["account_id"]),
            timestamp=timestamp,
            provider_metadata=provider_dto.get("metadata", {}),
            provider_event_type=event_label,
        )
