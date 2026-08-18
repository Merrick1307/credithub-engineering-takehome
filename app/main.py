"""FastAPI app entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
import hashlib
import uuid

from app.adapters.persistence.db import engine, SessionLocal
from .api import router as api_router
from app.api.dependencies import set_session_factory

# Import new architecture
from .application.reconcile_payment import ReconcilePaymentUseCase
from app.adapters.persistence.sqlalchemy_backend.sqlalchemy_repositories import SQLAlchemyUnitOfWork
from .infrastructure.provider_registry import SimpleProviderRegistry, NoOpProviderLookup
from .infrastructure.authenticators import TokenAuthenticator
from .infrastructure.decoders import SimpleJsonDecoder
from .infrastructure.normalizers import LegacyPaystackNormalizer
from .adapters.providers.mock import (
    MockMajorUnitNormalizer,
    MockProviderAuthenticator,
    MockProviderDecoder,
    MockProviderNormalizer,
    MockTokenAuthenticator,
)
from .adapters.providers.core_banking import (
    CoreBankingAuthenticator,
    CoreBankingDecoder,
    CoreBankingNormalizer,
)
from app.adapters.persistence.sqlalchemy_backend.models import WebhookDelivery

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for FastAPI.
    
    Startup: Initialize database connection pool and inject session factory.
    Shutdown: Clean up connection pool.
    """
    # Startup: Initialize the session factory dependency
    set_session_factory(SessionLocal)
    print("✓ Database connection pool initialized")
    
    yield
    
    # Shutdown: Dispose the engine and close pool
    engine.dispose()
    print("✓ Database connection pool closed")


app = FastAPI(
    title="CreditHub take-home — loan servicing slice",
    lifespan=lifespan
)
app.include_router(api_router)

# Initialize new architecture components
provider_registry = SimpleProviderRegistry()
provider_lookup = NoOpProviderLookup()
authenticator = TokenAuthenticator()
decoder = SimpleJsonDecoder()
normalizer = LegacyPaystackNormalizer()

provider_adapters = {
    "mock": (MockProviderAuthenticator(), MockProviderDecoder(), MockProviderNormalizer()),
    "mock_token": (MockTokenAuthenticator(), MockProviderDecoder(), MockProviderNormalizer()),
    "mock_major": (MockProviderAuthenticator(), MockProviderDecoder(), MockMajorUnitNormalizer()),
    "core_banking": (CoreBankingAuthenticator(), CoreBankingDecoder(), CoreBankingNormalizer()),
}
app.state.provider_registry = provider_registry
app.state.provider_lookup = provider_lookup
app.state.session_factory = SessionLocal


def record_delivery(provider: str, raw_body: bytes, correlation_id: str, result) -> None:
    """Persist a sanitized callback fact after financial reconciliation commits."""
    db = SessionLocal()
    try:
        db.add(WebhookDelivery(
            provider=provider,
            delivery_status="accepted" if result.status.value != "rejected" else "non_actionable",
            payload_digest=hashlib.sha256(raw_body).hexdigest(),
            payment_event_id=result.event_id,
            correlation_id=correlation_id,
            detail=result.reason.value,
        ))
        db.commit()
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/webhooks/payments", status_code=200)
async def receive_payment_webhook(request: Request):
    """Webhook endpoint for payment ingestion.
    
    Legacy endpoint that accepts:
    {
        "external_ref": "...",
        "loan_id": ...,
        "amount": ...,
        "channel": "paystack"
    }
    
    Authenticated via X-Webhook-Token header.
    """
    
    correlation_id = str(uuid.uuid4())
    
    try:
        # Get provider config
        provider = "paystack"
        if not provider_registry.is_provider_enabled(provider):
            raise HTTPException(status_code=404, detail="Provider not found")
        
        provider_config = provider_registry.get_provider_config(provider)
        
        # Read raw body
        raw_body = await request.body()
        
        # Authenticate
        if not authenticator.verify_signature(
            provider,
            raw_body,
            dict(request.headers),
            provider_config,
        ):
            raise HTTPException(status_code=401, detail="Invalid or missing X-Webhook-Token header")
        
        # Decode
        content_type = "application/json"
        try:
            provider_dto = decoder.decode_payload(provider, content_type, raw_body)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        
        # Normalize
        try:
            canonical_event = normalizer.normalize(provider, provider_dto, provider_config)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        
        # Execute reconciliation
        uow = SQLAlchemyUnitOfWork(SessionLocal)
        use_case = ReconcilePaymentUseCase(uow, provider_registry, provider_lookup)
        result = use_case.execute(canonical_event, correlation_id)
        record_delivery(provider, raw_body, correlation_id, result)
        return result.to_dict()
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in webhook: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")


@app.post("/webhooks/payments/{provider}", status_code=200)
async def receive_provider_payment_webhook(provider: str, request: Request):
    """Receive a provider-native callback through the adapter boundary."""
    adapter = provider_adapters.get(provider)
    if adapter is None:
        raise HTTPException(status_code=404, detail="Provider not found or disabled")

    authenticator, decoder, normalizer = adapter
    # The transport-level controller is intentionally inline here: webhooks
    # are the sole exception to the API package's read/admin route grouping.
    from .api.webhooks import PaymentWebhookController
    controller = PaymentWebhookController(SQLAlchemyUnitOfWork(SessionLocal), provider_registry, authenticator, decoder, normalizer, provider_lookup)
    return await controller.receive_payment_webhook(provider, request)
