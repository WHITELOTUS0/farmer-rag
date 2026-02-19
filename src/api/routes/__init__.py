"""API route handlers."""

from src.api.routes.health import router as health_router
from src.api.routes.chat import router as chat_router
from src.api.routes.auth import router as auth_router
from src.api.routes.admin import router as admin_router
from src.api.routes.users import router as users_router
from src.api.routes.farmers import router as farmers_router
from src.api.routes.conversations import router as conversations_router
from src.api.routes.documents import router as documents_router
from src.api.routes.search import router as search_router
from src.api.routes.farms import router as farms_router
from src.api.routes.crops import router as crops_router
from src.api.routes.metrics import router as metrics_router

__all__ = [
    "health_router",
    "chat_router",
    "auth_router",
    "admin_router",
    "users_router",
    "farmers_router",
    "conversations_router",
    "documents_router",
    "search_router",
    "farms_router",
    "crops_router",
    "metrics_router",
]
