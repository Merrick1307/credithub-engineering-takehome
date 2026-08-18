"""Provider registry and configuration management."""

from typing import Optional, Dict
from ..ports.providers import ProviderRegistry


class SimpleProviderRegistry(ProviderRegistry):
    """Simple in-memory provider registry for this exercise."""
    
    PROVIDERS = {
        "paystack": {
            "enabled": True,
            "secret_key": "dev-webhook-secret",  # Used for demo token auth
            "lookup_enabled": False,
        },
        "mock": {
            "enabled": True,
            "secret_key": "mock-secret-key-for-testing",
            "lookup_enabled": False,
            "auth_scheme": "hmac_sha256",
            "amount_format": "minor_units",
        },
        "mock_token": {
            "enabled": True,
            "secret_key": "mock-token-for-testing",
            "lookup_enabled": False,
            "auth_scheme": "token",
            "amount_format": "minor_units",
        },
        "mock_major": {
            "enabled": True,
            "secret_key": "mock-major-secret-for-testing",
            "lookup_enabled": False,
            "auth_scheme": "hmac_sha256",
            "amount_format": "major_units",
        },
        "core_banking": {
            "enabled": True,
            "secret_key": "core-banking-token-for-testing",
            "lookup_enabled": False,
            "auth_scheme": "hmac_sha256",
            "legacy_token_compatible": True,
            "amount_format": "major_units",
        },
    }
    
    def get_provider_config(self, provider: str) -> dict:
        """Load provider configuration."""
        if provider not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {provider}")
        if not self.PROVIDERS[provider]["enabled"]:
            raise ValueError(f"Provider disabled: {provider}")
        return self.PROVIDERS[provider].copy()
    
    def list_enabled_providers(self) -> list[str]:
        """List enabled providers."""
        return [p for p, cfg in self.PROVIDERS.items() if cfg.get("enabled")]
    
    def is_provider_enabled(self, provider: str) -> bool:
        """Check if provider is enabled."""
        return provider in self.PROVIDERS and self.PROVIDERS[provider].get("enabled", False)


class NoOpProviderLookup:
    """Deterministic demo verification adapter used by manual retries."""
    
    def lookup_payment(self, provider: str, canonical_event, config: dict):
        """Always return 'not supported' for now."""
        # The two local adapters emulate a successful provider verification;
        # this lets seeded admin retries exercise the full reconciliation path.
        if provider in {"mock", "core_banking"}:
            return {"status": "confirmed", "source": "demo_provider"}
        return {"status": "not_supported", "reason": "No demo lookup for provider"}
