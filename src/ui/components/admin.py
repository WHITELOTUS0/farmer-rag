"""
Admin panel component for system configuration.
"""

import gradio as gr
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def get_current_settings() -> Dict[str, Any]:
    """Get current system settings."""
    from src.config.settings import get_settings
    settings = get_settings()

    return {
        "primary_model": settings.primary_model,
        "verification_model": settings.verification_model,
        "temperature": settings.model_temperature,
        "confidence_threshold": settings.confidence_threshold,
        "max_tool_calls": settings.max_tool_calls_per_turn,
        "retrieval_top_k": settings.retrieval_top_k,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
    }


def get_vector_store_stats() -> Dict[str, Any]:
    """Get vector store statistics."""
    try:
        from src.retrieval.vector_store import VectorStore
        vs = VectorStore()
        return vs.get_collection_stats()
    except Exception as e:
        logger.error(f"Error getting vector store stats: {e}")
        return {"error": str(e), "total_documents": 0}


def test_weather_tool(lat: float, lon: float) -> str:
    """Test the weather tool."""
    try:
        from src.tools.weather import WeatherTool
        tool = WeatherTool()
        result = tool.run(latitude=lat, longitude=lon, days=3)

        if result.success:
            data = result.data
            current = data.get("current_conditions", {})
            summary = data.get("agricultural_summary", {})

            output = f"**Current Conditions:**\n"
            output += f"- Temperature: {current.get('temperature_c', 'N/A')}°C\n"
            output += f"- Humidity: {current.get('humidity_percent', 'N/A')}%\n"
            output += f"- Conditions: {current.get('conditions', 'N/A')}\n\n"

            output += f"**7-Day Summary:**\n"
            output += f"- Total Precipitation: {summary.get('total_precipitation_mm', 0):.1f}mm\n"
            output += f"- Rainy Days: {summary.get('rainy_days_count', 0)}\n\n"

            if summary.get("recommendations"):
                output += f"**Recommendations:**\n"
                for rec in summary["recommendations"]:
                    output += f"- {rec}\n"

            return output
        else:
            return f"Error: {result.error}"
    except Exception as e:
        return f"Error: {str(e)}"


def test_market_tool(crop: str, region: str) -> str:
    """Test the market price tool."""
    try:
        from src.tools.market import MarketPriceTool
        tool = MarketPriceTool()
        result = tool.run(crop_type=crop, region=region if region else None)

        if result.success:
            data = result.data
            output = f"**Market Prices for {crop.title()}**\n\n"

            if data.get("best_market"):
                best = data["best_market"]
                output += f"Best Market: {best['region']} at ${best['price_usd_per_kg']}/kg\n\n"

            output += "**Prices by Region:**\n"
            for price in data.get("prices_by_region", [])[:5]:
                local = price.get("price_local_estimate", {})
                output += f"- {price['region']}: ${price['price_usd_per_kg']}/kg "
                output += f"({local.get('amount', 0):.0f} {local.get('currency', '')})\n"

            if data.get("recommendations"):
                output += f"\n**Recommendations:**\n"
                for rec in data["recommendations"]:
                    output += f"- {rec}\n"

            return output
        else:
            return f"Error: {result.error}"
    except Exception as e:
        return f"Error: {str(e)}"


def test_knowledge_tool(query: str, crop: str) -> str:
    """Test the knowledge base tool."""
    try:
        from src.tools.knowledge import KnowledgeBaseTool
        tool = KnowledgeBaseTool()
        result = tool.run(query=query, crop_type=crop if crop else None, top_k=3)

        if result.success:
            data = result.data
            results = data.get("results", [])

            if not results:
                return "No results found in the knowledge base."

            output = f"**Found {len(results)} relevant documents:**\n\n"

            for r in results:
                output += f"**[{r['rank']}] {r['source']}** (confidence: {r['confidence']:.2f})\n"
                output += f"{r['text'][:300]}...\n\n"

            return output
        else:
            return f"Error: {result.error}"
    except Exception as e:
        return f"Error: {str(e)}"


def create_admin_panel() -> gr.Blocks:
    """
    Create the admin panel component.

    Returns:
        Gradio Blocks component
    """
    with gr.Blocks() as admin_panel:
        gr.Markdown("## ⚙️ Admin Panel")

        with gr.Tabs():
            # System Settings Tab
            with gr.TabItem("📋 Settings"):
                gr.Markdown("### Model Configuration")
                gr.Markdown("*Note: Changes here are for display only. Edit `.env` file to change settings.*")

                with gr.Row():
                    with gr.Column():
                        settings_display = gr.JSON(
                            label="Current Settings",
                            value=get_current_settings(),
                        )
                        refresh_settings_btn = gr.Button("Refresh Settings")

                    with gr.Column():
                        gr.Markdown("### Configuration Options")
                        gr.Markdown("""
                        **Model Settings:**
                        - `PRIMARY_MODEL`: Main reasoning model (gpt-4o)
                        - `VERIFICATION_MODEL`: Verification model (gpt-4o-mini)
                        - `MODEL_TEMPERATURE`: Response randomness (0-2)

                        **Retrieval Settings:**
                        - `CONFIDENCE_THRESHOLD`: Min groundedness score
                        - `RETRIEVAL_TOP_K`: Documents to retrieve
                        - `CHUNK_SIZE`: Document chunk size
                        """)

                refresh_settings_btn.click(
                    get_current_settings,
                    outputs=[settings_display],
                )

            # Vector Store Tab
            with gr.TabItem("🗃️ Vector Store"):
                gr.Markdown("### Knowledge Base Statistics")

                stats_display = gr.JSON(
                    label="Vector Store Stats",
                    value=get_vector_store_stats(),
                )

                refresh_stats_btn = gr.Button("Refresh Stats")
                refresh_stats_btn.click(
                    get_vector_store_stats,
                    outputs=[stats_display],
                )

                gr.Markdown("### Reset Vector Store")
                gr.Markdown("⚠️ **Warning:** This will delete all indexed documents!")

                with gr.Row():
                    confirm_reset = gr.Checkbox(label="I understand this will delete all data")
                    reset_btn = gr.Button("Reset Vector Store", variant="stop")

                reset_status = gr.Textbox(label="Status", interactive=False)

                def reset_vector_store(confirmed):
                    if not confirmed:
                        return "Please confirm by checking the box."
                    try:
                        from src.retrieval.vector_store import VectorStore
                        vs = VectorStore()
                        vs.reset()
                        return "Vector store reset successfully."
                    except Exception as e:
                        return f"Error: {str(e)}"

                reset_btn.click(
                    reset_vector_store,
                    inputs=[confirm_reset],
                    outputs=[reset_status],
                )

            # Tool Testing Tab
            with gr.TabItem("🔧 Test Tools"):
                gr.Markdown("### Test Individual Tools")

                with gr.Accordion("🌤️ Weather Tool", open=True):
                    with gr.Row():
                        weather_lat = gr.Number(label="Latitude", value=-1.9403)
                        weather_lon = gr.Number(label="Longitude", value=29.8739)
                    weather_btn = gr.Button("Test Weather")
                    weather_output = gr.Markdown(label="Result")

                    weather_btn.click(
                        test_weather_tool,
                        inputs=[weather_lat, weather_lon],
                        outputs=[weather_output],
                    )

                with gr.Accordion("💰 Market Price Tool", open=False):
                    with gr.Row():
                        market_crop = gr.Dropdown(
                            label="Crop",
                            choices=["maize", "beans", "tomatoes"],
                            value="maize",
                        )
                        market_region = gr.Dropdown(
                            label="Region (optional)",
                            choices=["", "Kigali", "Nairobi", "Kampala"],
                            value="",
                        )
                    market_btn = gr.Button("Test Market Prices")
                    market_output = gr.Markdown(label="Result")

                    market_btn.click(
                        test_market_tool,
                        inputs=[market_crop, market_region],
                        outputs=[market_output],
                    )

                with gr.Accordion("📚 Knowledge Base Tool", open=False):
                    kb_query = gr.Textbox(
                        label="Query",
                        value="How to apply fertilizer to maize?",
                    )
                    kb_crop = gr.Dropdown(
                        label="Crop Filter (optional)",
                        choices=["", "maize", "beans", "tomatoes"],
                        value="",
                    )
                    kb_btn = gr.Button("Test Knowledge Base")
                    kb_output = gr.Markdown(label="Result")

                    kb_btn.click(
                        test_knowledge_tool,
                        inputs=[kb_query, kb_crop],
                        outputs=[kb_output],
                    )

            # Logs Tab
            with gr.TabItem("📜 Logs"):
                gr.Markdown("### System Logs")
                gr.Markdown("*Coming soon: View recent system logs and agent traces.*")

                logs_display = gr.Textbox(
                    label="Recent Logs",
                    value="Log viewing not yet implemented.\n\nCheck console output for logs.",
                    lines=20,
                    interactive=False,
                )

    return admin_panel
