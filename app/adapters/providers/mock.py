"""Mock provider adapter for testing and demonstration.

This adapter accepts the legacy demo format and demonstrates the full
provider authentication, decoding, and normalization pipeline.
"""

from typing import Dict, Any
from decimal import Decimal
from datetime import datetime, timezone
import json
import hmac
import hashlib

from ...domain.models import CanonicalFinancialEvent, Money
from ...domain.enums import EventKind
from ...ports.providers import (
    ProviderAuthenticator,
    ProviderDecoder,
    ProviderNormalizer,
)


class MockProviderAuthenticator(ProviderAuthenticator):
    """Mock authenticator using HMAC-SHA256 over raw body."""
    
    def verify_signature(
        self,
        provider: str,
        raw_body: bytes,
        headers: dict,
        config: dict,
    ) -> bool:
        """Verify mock provider signature (HMAC-SHA256 over raw body).
        
        For mock provider, we use a test secret key.
        Header: X-Mock-Signature
        """
        signature = headers.get("x-mock-signature")
        if not signature:
            return False
        
        secret = config.get("secret_key", "mock-secret-key-for-testing")
        
        expected = hmac.new(
            secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        
        # Constant-time comparison
        return hmac.compare_digest(signature, expected)


class MockTokenAuthenticator(ProviderAuthenticator):
    """Mock variant using a constant-time token comparison instead of HMAC."""

    def verify_signature(self, provider: str, raw_body: bytes, headers: dict, config: dict) -> bool:
        supplied = headers.get("x-mock-token", "")
        expected = config.get("secret_key", "")
        return bool(expected) and hmac.compare_digest(supplied, expected)


class MockProviderDecoder(ProviderDecoder):
    """Mock provider JSON decoder with Decimal money parsing."""
    
    def get_supported_media_types(self, provider: str) -> list[str]:
        return ["application/json"]
    
    def decode_payload(
        self,
        provider: str,
        content_type: str,
        raw_body: bytes,
    ) -> dict:
        """Decode JSON with Decimal precision for money values."""
        if content_type != "application/json":
            raise ValueError(f"Unsupported content type: {content_type}")
        
        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid JSON: {e}")
        
        # Validate required fields for mock provider
        required = ["transaction_id", "amount", "customer_id", "status"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        return data


class MockProviderNormalizer(ProviderNormalizer):
    """Normalize mock provider DTO to canonical form.
    
    The mock provider uses a simple JSON format:
    {
        "transaction_id": "TXN-001",
        "amount": 50000,  # In smallest currency unit (kobo/cents)
        "customer_id": "CUST-123",
        "status": "success",
        "timestamp": "2026-08-17T10:00:00Z",
        "metadata": {}
    }
    """
    
    # Mock event type to canonical mapping
    EVENT_TYPE_MAP = {
        "payment": EventKind.transaction_credit,
        "reversal": EventKind.transaction_reversal,
        "refund": EventKind.transaction_refund,
    }
    
    def normalize(
        self,
        provider: str,
        provider_dto: dict,
        provider_config: dict,
    ) -> CanonicalFinancialEvent:
        """Convert mock provider DTO to canonical financial event."""
        
        # Extract event type (default to payment)
        event_type = provider_dto.get("event_type", "payment")
        if event_type not in self.EVENT_TYPE_MAP:
            raise ValueError(f"Unknown event type: {event_type}")
        
        canonical_kind = self.EVENT_TYPE_MAP[event_type]
        
        # Parse amount (mock provider uses smallest unit)
        try:
            amount_units = int(provider_dto.get("amount", 0))
            # Mock uses 2 decimal places (like NGN)
            gross_amount = Money(Decimal(amount_units) / Decimal(100), "NGN")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid amount: {e}")
        
        # Extract transaction ID
        transaction_id = provider_dto.get("transaction_id")
        if not transaction_id:
            raise ValueError("Missing transaction_id")
        
        # Parse timestamp
        try:
            timestamp_str = provider_dto.get("timestamp")
            if timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            else:
                timestamp = datetime.now(timezone.utc)
        except (ValueError, AttributeError):
            timestamp = datetime.now(timezone.utc)
        
        # For reversals/refunds, track original reference
        original_reference = provider_dto.get("original_transaction_id")
        
        return CanonicalFinancialEvent(
            provider=provider,
            event_kind=canonical_kind,
            event_reference=transaction_id,
            original_payment_reference=original_reference,
            gross_amount=gross_amount,
            provider_status=(
                "succeeded"
                if provider_dto.get("status") == "success"
                else provider_dto.get("status", "unknown")
            ),
            merchant_scope=str(provider_dto.get("customer_id", "unknown")),
            timestamp=timestamp,
            provider_metadata=provider_dto.get("metadata", {}),
            provider_event_type=event_type,
        )


class MockMajorUnitNormalizer(MockProviderNormalizer):
    """Mock variant whose amount is a fixed-point NGN value rather than kobo."""

    def normalize(self, provider: str, provider_dto: dict, provider_config: dict) -> CanonicalFinancialEvent:
        try:
            amount = Decimal(str(provider_dto["amount"]))
            if amount.as_tuple().exponent < -2:
                raise ValueError("amount has more than two decimal places")
            amount_in_kobo = amount * Decimal(100)
            if amount_in_kobo != amount_in_kobo.to_integral_value():
                raise ValueError("amount cannot be represented in kobo")
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid major-unit amount: {exc}") from exc

        normalized_dto = provider_dto.copy()
        normalized_dto["amount"] = int(amount_in_kobo)
        return super().normalize(provider, normalized_dto, provider_config)
