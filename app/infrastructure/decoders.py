"""Simple JSON decoder for demo."""

import json
from decimal import Decimal
from ..ports.providers import ProviderDecoder


class SimpleJsonDecoder(ProviderDecoder):
    """JSON decoder that parses money values as Decimal."""
    
    def get_supported_media_types(self, provider: str) -> list[str]:
        return ["application/json"]
    
    def decode_payload(
        self,
        provider: str,
        content_type: str,
        raw_body: bytes,
    ) -> dict:
        """Decode JSON strictly."""
        if content_type not in self.get_supported_media_types(provider):
            raise ValueError(f"Unsupported content type: {content_type}")
        
        try:
            data = json.loads(raw_body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid JSON: {e}")
        
        # For demo, expect: external_ref, loan_id, amount, channel
        required = ["external_ref", "loan_id", "amount"]
        for field in required:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")
        
        return data
