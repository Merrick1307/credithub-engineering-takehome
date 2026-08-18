"""Simple normalizers for demo/legacy formats."""

from decimal import Decimal
from datetime import datetime, timezone
from ..domain.models import CanonicalFinancialEvent, Money
from ..domain.enums import EventKind
from ..ports.providers import ProviderNormalizer


class LegacyPaystackNormalizer(ProviderNormalizer):
    """Normalize legacy demo format to canonical financial event."""
    
    def normalize(
        self,
        provider: str,
        provider_dto: dict,
        provider_config: dict,
    ) -> CanonicalFinancialEvent:
        """Convert legacy DTO to canonical form.
        
        Expected format:
        {
            "external_ref": "R-1",
            "loan_id": 1,
            "amount": 20000,
            "channel": "paystack"
        }
        """
        
        try:
            amount_float = float(provider_dto.get("amount", 0))
            gross_amount = Money(Decimal(str(amount_float)), "NGN")
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid amount: {e}")
        
        external_ref = provider_dto.get("external_ref")
        if not external_ref:
            raise ValueError("Missing external_ref")
        
        loan_id = provider_dto.get("loan_id")
        if not loan_id:
            raise ValueError("Missing loan_id")
        
        return CanonicalFinancialEvent(
            provider="paystack",
            event_kind=EventKind.transaction_credit,
            event_reference=external_ref,
            original_payment_reference=None,
            gross_amount=gross_amount,
            provider_status="succeeded",
            merchant_scope=str(loan_id),  # Use loan_id as merchant scope for demo
            timestamp=datetime.now(timezone.utc),
            provider_metadata={},
            provider_event_type="charge.success",
        )
