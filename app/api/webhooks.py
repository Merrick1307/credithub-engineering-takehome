"""FastAPI webhook controller for payment reconciliation.

This controller:
1. Receives raw webhook requests
2. Authenticates them with provider adapters
3. Decodes and normalizes the payload
4. Invokes the reconciliation use case
5. Maps results back to HTTP responses

It remains thin and framework-specific, delegating domain logic to the use case.
"""

from fastapi import HTTPException, Request
import hashlib
from datetime import datetime
import uuid

from ..application.reconcile_payment import ReconcilePaymentUseCase
from ..ports.providers import ProviderRegistry, ProviderDecoder, ProviderAuthenticator, ProviderNormalizer
from ..ports.repositories import UnitOfWork
from app.adapters.persistence.sqlalchemy_backend.models import WebhookDelivery

class PaymentWebhookController:
    """Controller for payment webhook ingestion."""
    
    def __init__(
        self,
        uow: UnitOfWork,
        provider_registry: ProviderRegistry,
        authenticator: ProviderAuthenticator,
        decoder: ProviderDecoder,
        normalizer: ProviderNormalizer,
        lookup_service,
    ):
        self.uow = uow
        self.provider_registry = provider_registry
        self.authenticator = authenticator
        self.decoder = decoder
        self.normalizer = normalizer
        self.lookup_service = lookup_service
        self.use_case = ReconcilePaymentUseCase(uow, provider_registry, lookup_service)
    
    async def receive_payment_webhook(
        self,
        provider: str,
        request: Request,
    ) -> dict:
        """Handle POST /webhooks/payments/{provider}.
        
        Args:
            provider: Provider name (e.g., "paystack", "fincra")
            request: FastAPI Request with raw body and headers
        
        Returns:
            JSON response with reconciliation result or error.
        
        HTTP Status Codes:
            200: Successful reconciliation (applied, partially applied, or non-actionable)
            401: Invalid signature
            404: Unknown provider
            415: Unsupported content type
            422: Malformed content
            503: Transient failure (unrecoverable)
        """
        
        correlation_id = str(uuid.uuid4())
        
        try:
            # Step 1: Check provider exists and is enabled
            if not self.provider_registry.is_provider_enabled(provider):
                raise HTTPException(status_code=404, detail="Provider not found or disabled")
            
            provider_config = self.provider_registry.get_provider_config(provider)
            
            # Step 2: Read raw body
            raw_body = await request.body()
            
            # Step 3: Authenticate signature
            try:
                if not self.authenticator.verify_signature(
                    provider,
                    raw_body,
                    dict(request.headers),
                    provider_config,
                ):
                    raise HTTPException(status_code=401, detail="Invalid signature")
            except ValueError as e:
                # Config error
                raise HTTPException(status_code=500, detail=f"Configuration error: {e}")
            
            # Step 4: Check content type
            content_type = request.headers.get("content-type", "").split(";")[0].strip()
            supported_types = self.decoder.get_supported_media_types(provider)
            if content_type not in supported_types:
                raise HTTPException(status_code=415, detail=f"Unsupported content type: {content_type}")
            
            # Step 5: Decode payload
            try:
                provider_dto = self.decoder.decode_payload(provider, content_type, raw_body)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Malformed content: {e}")
            
            # Step 6: Normalize to canonical form
            try:
                canonical_event = self.normalizer.normalize(provider, provider_dto, provider_config)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"Invalid event: {e}")
            
            # Step 7: Execute reconciliation use case
            result = self.use_case.execute(canonical_event, correlation_id)
            self._record_delivery(provider, raw_body, correlation_id, result)
            
            # Step 8: Return result
            return result.to_dict()
        
        except HTTPException:
            raise
        except Exception as e:
            # Unhandled error; log and return 503
            print(f"Unhandled error in webhook: {e}")
            raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    def _record_delivery(self, provider: str, raw_body: bytes, correlation_id: str, result) -> None:
        """Write a sanitized delivery fact after its financial transaction commits."""
        session = self.uow.session_factory()
        try:
            delivery_status = (
                "duplicate" if result.idempotent_replay
                else "accepted" if result.status.value != "rejected"
                else "non_actionable"
            )
            session.add(WebhookDelivery(
                provider=provider,
                delivery_status=delivery_status,
                payload_digest=hashlib.sha256(raw_body).hexdigest(),
                payment_event_id=result.event_id,
                correlation_id=correlation_id,
                detail=result.reason.value,
            ))
            session.commit()
        finally:
            session.close()
