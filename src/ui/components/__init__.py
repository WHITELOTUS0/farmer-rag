"""UI components for the Gradio interface."""

from src.ui.components.chat import create_chat_interface
from src.ui.components.admin import create_admin_panel
from src.ui.components.documents import create_document_manager

__all__ = [
    "create_chat_interface",
    "create_admin_panel",
    "create_document_manager",
]
