"""
Main Gradio application for the Farmer RAG Advisory System.

Combines chat, document management, and admin panels into
a unified interface.
"""

import gradio as gr
import logging

from src.ui.components.chat import create_chat_interface
from src.ui.components.admin import create_admin_panel
from src.ui.components.documents import create_document_manager

logger = logging.getLogger(__name__)


def create_app() -> gr.Blocks:
    """
    Create the main Gradio application.

    Returns:
        Gradio Blocks application
    """
    # Custom CSS for better styling
    custom_css = """
    .gradio-container {
        max-width: 1400px !important;
    }
    .contain {
        max-width: 1400px !important;
    }
    #header {
        text-align: center;
        margin-bottom: 20px;
    }
    .footer {
        text-align: center;
        margin-top: 20px;
        padding: 10px;
        border-top: 1px solid #e0e0e0;
    }
    """

    with gr.Blocks(
        title="Farmer RAG Advisory System",
        theme=gr.themes.Soft(
            primary_hue="green",
            secondary_hue="emerald",
        ),
        css=custom_css,
    ) as app:
        # Header
        gr.Markdown(
            """
            # 🌾 Farmer RAG Advisory System

            An AI-powered agricultural advisory system for smallholder farmers in East Africa.
            Get personalized recommendations for maize, beans, and tomatoes based on your location,
            weather conditions, and market prices.
            """,
            elem_id="header",
        )

        # Main tabs
        with gr.Tabs():
            with gr.TabItem("💬 Chat", id="chat"):
                create_chat_interface()

            with gr.TabItem("📁 Documents", id="documents"):
                create_document_manager()

            with gr.TabItem("⚙️ Admin", id="admin"):
                create_admin_panel()

            with gr.TabItem("ℹ️ About", id="about"):
                gr.Markdown(
                    """
                    ## About This System

                    The Farmer RAG Advisory System is designed to help smallholder farmers in East Africa
                    make better agricultural decisions. It combines:

                    ### 🤖 AI-Powered Advice
                    - Uses GPT-4 for intelligent reasoning and response generation
                    - Implements ReAct-style reasoning for complex queries
                    - Provides grounded responses with source citations

                    ### 📚 Knowledge Base (RAG)
                    - Stores agricultural extension documents
                    - Semantic search for relevant information
                    - Metadata filtering by crop type, topic, and growth stage

                    ### 🛠️ External Tools
                    - **Weather Forecast**: Real-time weather data from Open-Meteo API
                    - **Market Prices**: Current crop prices across East African markets
                    - **Knowledge Base**: Agricultural best practices and recommendations

                    ### ✅ Verification
                    - Extracts factual claims from responses
                    - Verifies claims against retrieved sources
                    - Calculates groundedness score (0-1)

                    ---

                    ### How to Use

                    1. **Chat**: Ask questions about farming practices, pest control, weather, or prices
                    2. **Documents**: Upload agricultural guides to expand the knowledge base
                    3. **Admin**: Test tools and view system statistics

                    ---

                    ### Technical Stack
                    - **LLM**: OpenAI GPT-4o / GPT-4o-mini
                    - **Vector DB**: ChromaDB
                    - **Framework**: LangGraph for agent orchestration
                    - **UI**: Gradio

                    ---

                    *Developed for 04-801-W3 Agentic AI: Fundamentals and Applications*

                    *Carnegie Mellon University - Spring 2026*
                    """
                )

        # Footer
        gr.Markdown(
            """
            <div class="footer">
            <p>🌱 Farmer RAG Advisory System v0.1.0</p>
            <p>Built with LangGraph, ChromaDB, and Gradio</p>
            </div>
            """,
        )

    return app


def launch_app(
    share: bool = False,
    server_port: int = 7860,
    server_name: str = "0.0.0.0",
    debug: bool = False,
) -> None:
    """
    Launch the Gradio application.

    Args:
        share: Whether to create a public link
        server_port: Port to run the server on
        server_name: Server hostname
        debug: Enable debug mode
    """
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting Farmer RAG Advisory System...")

    app = create_app()

    app.launch(
        share=share,
        server_port=server_port,
        server_name=server_name,
        show_error=debug,
    )


if __name__ == "__main__":
    launch_app(debug=True)
