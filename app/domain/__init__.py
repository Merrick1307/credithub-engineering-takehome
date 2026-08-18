"""Domain layer: core business logic and models.

The domain layer is framework-agnostic and contains:
- Value objects (Money, Identity, etc.)
- Domain events and aggregates
- Business rules and policies
- Domain enums and constants

It must not depend on SQLAlchemy, FastAPI, or any infrastructure.
"""

from . import enums  # noqa: F401
from .models import (  # noqa: F401
    Money,
    LoanBalance,
    CanonicalFinancialEvent,
    ReconciliationResult,
)
