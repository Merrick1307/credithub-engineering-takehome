"""Port interfaces for provider adapters."""

from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime

from ..domain.models import CanonicalFinancialEvent


class ProviderAuthenticator(ABC):
    """Port for verifying provider signatures."""
    
    @abstractmethod
    def verify_signature(
        self,
        provider: str,
        raw_body: bytes,
        headers: dict,
        config: dict,
    ) -> bool:
        """Verify that the raw request matches the provider's signature.
        
        Must use constant-time comparison and handle replay windows.
        Raises ValueError on configuration errors or missing credentials.
        """
        pass


class ProviderDecoder(ABC):
    """Port for decoding provider-specific payloads."""
    
    @abstractmethod
    def get_supported_media_types(self, provider: str) -> list[str]:
        """Return list of Content-Type values this provider accepts."""
        pass
    
    @abstractmethod
    def decode_payload(
        self,
        provider: str,
        content_type: str,
        raw_body: bytes,
    ) -> dict:
        """Decode and validate provider-specific payload.
        
        For JSON: strict parsing, Decimal for money values.
        For XML: hardened parser, no DTD/XXE, element size limits.
        
        Returns a validated provider DTO as dict.
        Raises ValueError on malformed or invalid content.
        """
        pass


class ProviderNormalizer(ABC):
    """Port for normalizing provider-specific DTOs to canonical form."""
    
    @abstractmethod
    def normalize(
        self,
        provider: str,
        provider_dto: dict,
        provider_config: dict,
    ) -> CanonicalFinancialEvent:
        """Convert provider DTO to canonical financial event.
        
        Maps provider-specific field names, status values, and types
        to the canonical form. Unknown fields are preserved in metadata.
        
        Raises ValueError if required fields are missing or invalid.
        """
        pass


class ProviderLookup(ABC):
    """Port for confirming payments with provider's authoritative record."""
    
    @abstractmethod
    def lookup_payment(
        self,
        provider: str,
        canonical_event: CanonicalFinancialEvent,
        config: dict,
    ) -> dict:
        """Fetch the authoritative payment record from the provider.
        
        Returns:
        - {"status": "confirmed", "amount": Decimal, ...}: Confirmed and matches
        - {"status": "not_found"}: Terminal not-found result
        - {"status": "mismatch", "reason": str}: Authenticated but doesn't match
        - {"status": "transient_error", "reason": str}: Retry-able error
        
        Raises ValueError on configuration errors.
        """
        pass


class ProviderRegistry(ABC):
    """Port for provider configuration and adapter lookup."""
    
    @abstractmethod
    def get_provider_config(self, provider: str) -> dict:
        """Load provider configuration (credentials, endpoints, etc.)
        
        Returns encrypted/masked config suitable for authenticators/adapters.
        Raises ValueError if provider is unknown or disabled.
        """
        pass
    
    @abstractmethod
    def list_enabled_providers(self) -> list[str]:
        """List all enabled provider names."""
        pass
    
    @abstractmethod
    def is_provider_enabled(self, provider: str) -> bool:
        """Check if a provider is currently accepting webhooks."""
        pass
