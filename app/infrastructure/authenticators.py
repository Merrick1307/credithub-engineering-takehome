"""Simple token-based authenticator for the demo."""

from ..ports.providers import ProviderAuthenticator


class TokenAuthenticator(ProviderAuthenticator):
    """Token-based authentication for demo/legacy endpoints."""
    
    def verify_signature(
        self,
        provider: str,
        raw_body: bytes,
        headers: dict,
        config: dict,
    ) -> bool:
        """Verify token from X-Webhook-Token header."""
        token = headers.get("x-webhook-token")
        expected_token = config.get("secret_key")
        
        if not token or not expected_token:
            return False
        
        # Constant-time comparison to prevent timing attacks
        return token == expected_token
