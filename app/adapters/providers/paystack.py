"""Paystack provider adapter."""

from typing import Optional
from decimal import Decimal
import json
import hmac
import hashlib

from ...domain.models import CanonicalFinancialEvent, Money
from ...domain.enums import EventKind
from ...ports.providers import ProviderAuthenticator, ProviderDecoder, ProviderNormalizer


class PaystackAuthenticator(ProviderAuthenticator):
    """Verify Paystack HMAC-SHA512 signatures."""
    
    def verify_signature(
        self,
        provider: str,
        raw_body: bytes,
        headers: dict,
        config: dict,
    ) -> bool:
        """Verify Paystack signature using raw body and secret key."""
        signature = headers.get("x-paystack-signature")
        if not signature:
            return False
        
        secret = config.get("secret_key")
        if not secret:
            raise ValueError("Paystack secret_key not configured")
        
        expected = hmac.new(
            secret.encode(),
            raw_body,
            hashlib.sha512,
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected)


class PaystackDecoder(ProviderDecoder):
    """Decode and validate Paystack JSON payloads."""
    
    def get_supported_media_types(self, provider: str) -> list[str]:
        return ["application/json"]
    
    def decode_payload(
        self,
        provider: str,
        content_type: str,
        raw_body: bytes,
    ) -> dict:
        """Decode JSON strictly, parsing money as Decimal."""
        if content_type != "application/json":
            raise ValueError(f"Unsupported content type: {content_type}")
        
        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid JSON: {e}")
        
        # Validate Paystack event structure
        if "event" not in data or "data" not in data:
            raise ValueError("Missing 'event' or 'data' in Paystack payload")
        
        return data


class PaystackNormalizer(ProviderNormalizer):
    """Normalize Paystack DTO to canonical financial event."""
    
    # Paystack event type to canonical EventKind mapping
    EVENT_TYPE_MAP = {
        "charge.success": EventKind.transaction_credit,
        "transfer.reversed": EventKind.transaction_reversal,
        "refund": EventKind.transaction_refund,
    }
    
    def normalize(
        self,
        provider: str,
        provider_dto: dict,
        provider_config: dict,
    ) -> CanonicalFinancialEvent:
        """Convert Paystack DTO to canonical form."""
        
        event_type = provider_dto.get("event")
        data = provider_dto.get("data", {})
        
        if event_type not in self.EVENT_TYPE_MAP:
            raise ValueError(f"Unknown Paystack event type: {event_type}")
        
        canonical_kind = self.EVENT_TYPE_MAP[event_type]
        
        # Extract amount as Decimal
        try:
            amount_kobo = int(data.get("amount", 0))
            gross_amount = Money(Decimal(amount_kobo) / Decimal(100), "NGN")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid amount: {e}")
        
        # Extract reference
        reference = data.get("reference")
        if not reference:
            raise ValueError("Missing 'reference' in Paystack data")
        
        # For reversals/refunds, track the original reference
        original_reference = data.get("original_reference")
        
        return CanonicalFinancialEvent(
            provider="paystack",
            event_kind=canonical_kind,
            event_reference=reference,
            original_payment_reference=original_reference,
            gross_amount=gross_amount,
            provider_status=data.get("status", "unknown"),
            merchant_scope=str(data.get("customer", {}).get("id", "unknown")),
            timestamp=provider_dto.get("created_at", None),
            provider_metadata={
                "customer": data.get("customer"),
                "authorization": data.get("authorization"),
            },
            provider_event_type=event_type,
        )
