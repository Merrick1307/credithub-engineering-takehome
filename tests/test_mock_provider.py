"""Tests for the mock provider adapter and architecture validation."""

import json
import hmac
import hashlib
from decimal import Decimal


def test_mock_provider_adapter_integration():
    """Demonstrate the complete mock provider path works end-to-end."""
    from app.adapters.providers.mock import (
        MockProviderAuthenticator,
        MockProviderDecoder,
        MockProviderNormalizer,
    )
    from app.infrastructure.provider_registry import SimpleProviderRegistry
    
    # Set up provider
    authenticator = MockProviderAuthenticator()
    decoder = MockProviderDecoder()
    normalizer = MockProviderNormalizer()
    registry = SimpleProviderRegistry()
    
    provider = "mock"
    config = registry.get_provider_config(provider)
    
    # Create a mock provider payload
    payload = {
        "transaction_id": "TXN-2026-0001",
        "amount": 5600000,  # 56,000.00 in kobo
        "customer_id": "1",
        "status": "success",
        "timestamp": "2026-08-17T10:31:00Z",
        "metadata": {"reference": "loan-payment-001"},
        "event_type": "payment",
    }
    
    raw_body = json.dumps(payload).encode("utf-8")
    
    # Sign the payload
    signature = hmac.new(
        config["secret_key"].encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    
    headers = {"x-mock-signature": signature}
    
    # Step 1: Authenticate
    assert authenticator.verify_signature(provider, raw_body, headers, config)
    
    # Step 2: Decode
    content_type = "application/json"
    provider_dto = decoder.decode_payload(provider, content_type, raw_body)
    assert provider_dto["transaction_id"] == "TXN-2026-0001"
    
    # Step 3: Normalize
    canonical = normalizer.normalize(provider, provider_dto, config)
    assert canonical.provider == "mock"
    assert canonical.event_reference == "TXN-2026-0001"
    assert canonical.gross_amount.amount == Decimal("56000.00")
    assert canonical.merchant_scope == "1"
    assert canonical.provider_status == "succeeded"


if __name__ == "__main__":
    test_mock_provider_adapter_integration()
