"""API layer package: FastAPI controllers and request/response models."""
from fastapi import APIRouter

from .dev import router as dev_router
from .loans import router as loans_router
from .admin import router as admin_router
from .payments import router as payments_router

router = APIRouter()
router.include_router(dev_router)
router.include_router(loans_router)
router.include_router(admin_router)
router.include_router(payments_router)