"""Database module for Farmer RAG Agent."""

from src.database.connection import (
    get_async_session,
    get_sync_session,
    init_db,
    AsyncSessionLocal,
)
from src.database.models import (
    Base,
    Farm,
    Crop,
    Advisory,
    SystemConfig,
    Document,
    User,
    UserProfile,
    Conversation,
    Message,
    ToolCall,
    DocumentChunk,
    BackgroundJob,
    EvaluationRun,
)

__all__ = [
    # Connection
    "get_async_session",
    "get_sync_session",
    "init_db",
    "AsyncSessionLocal",
    # Models
    "Base",
    "Farm",
    "Crop",
    "Advisory",
    "SystemConfig",
    "Document",
    "User",
    "UserProfile",
    "Conversation",
    "Message",
    "ToolCall",
    "DocumentChunk",
    "BackgroundJob",
    "EvaluationRun",
]
