"""
Chat interface component for farmer interactions.
"""

import gradio as gr
from typing import List, Tuple, Optional, Dict, Any, Generator
import logging
import time

logger = logging.getLogger(__name__)

# Store for conversation history and agent
_agent = None
_current_farmer_context = None


def get_agent():
    """Get or create the agent instance."""
    global _agent
    if _agent is None:
        from src.agent import create_agent
        _agent = create_agent()
    return _agent


def stream_chat_response(
    message: str,
    history: Optional[List[Dict[str, str]]],
    farmer_name: str,
    farmer_region: str,
    farmer_lat: float,
    farmer_lon: float,
    crop_types: List[str],
) -> Generator[Tuple[str, List[Dict[str, str]], Dict[str, Any]], None, None]:
    """
    Process a chat message and return response.

    Args:
        message: User's message
        history: Conversation history
        farmer_name: Selected farmer name
        farmer_region: Farmer's region
        farmer_lat: Latitude
        farmer_lon: Longitude
        crop_types: List of crops being grown

    Returns:
        Generator yielding (cleared_input, updated_history, stats)
    """
    if history is None:
        history = []

    if not message.strip():
        yield "", history, {
            "groundedness_score": "N/A",
            "sources_used": 0,
            "tools_called": [],
        }
        return

    # Build farmer context
    farmer_context = {
        "farmer": {
            "name": farmer_name or "Demo Farmer",
            "region": farmer_region or "Kigali",
            "location": {
                "lat": farmer_lat or -1.9403,
                "lon": farmer_lon or 29.8739,
            },
        },
        "farms": [
            {
                "name": "Main Farm",
                "crops": [
                    {"type": crop, "growth_stage": "vegetative"}
                    for crop in (crop_types or ["maize"])
                ],
            }
        ],
    }

    try:
        agent = get_agent()

        # Convert history to messages format
        conversation_history = []
        for msg in history:
            role = msg.get("role")
            content = msg.get("content")
            if role in {"user", "assistant"} and content:
                conversation_history.append({"role": role, "content": content})

        # Run agent
        result = agent.run(
            query=message,
            farmer_context=farmer_context,
            conversation_history=conversation_history,
        )

        response = result["response"]
        tools_called = result.get("tools_called") or []
        groundedness_score = result.get("groundedness_score", "N/A")
        sources_used = result.get("sources_used", 0)

    except Exception as e:
        logger.error(f"Chat error: {e}")
        response = f"I apologize, but I encountered an error: {str(e)}"
        tools_called = []
        groundedness_score = "N/A"
        sources_used = 0

    # Stream the assistant response in chunks
    history = history + [{"role": "user", "content": message}]
    chunk_size = 40
    for i in range(0, len(response), chunk_size):
        assistant_message = response[: i + chunk_size]
        interim_history = history + [{"role": "assistant", "content": assistant_message}]
        yield "", interim_history, {
            "groundedness_score": groundedness_score,
            "sources_used": sources_used,
            "tools_called": tools_called,
        }
        time.sleep(0.02)


def create_chat_interface() -> gr.Blocks:
    """
    Create the chat interface component.

    Returns:
        Gradio Blocks component
    """
    with gr.Blocks() as chat_interface:
        gr.Markdown("## 💬 Chat with Agricultural Advisor")
        gr.Markdown(
            "Ask questions about farming practices, weather, market prices, "
            "pest control, fertilizers, and more."
        )

        with gr.Row():
            with gr.Column(scale=3):
                # Chat area
                chatbot = gr.Chatbot(
                    label="Conversation",
                    height=500,
                )

                with gr.Row():
                    msg_input = gr.Textbox(
                        label="Your Question",
                        placeholder="e.g., When should I apply fertilizer to my maize?",
                        lines=2,
                        scale=4,
                    )
                    send_btn = gr.Button("Send", variant="primary", scale=1)

                with gr.Row():
                    clear_btn = gr.Button("Clear Chat")
                    example_btn = gr.Button("Load Example")

            with gr.Column(scale=1):
                # Farmer context panel
                gr.Markdown("### 👤 Farmer Profile")

                farmer_name = gr.Textbox(
                    label="Name",
                    value="Demo Farmer",
                    interactive=True,
                )

                farmer_region = gr.Dropdown(
                    label="Region",
                    choices=["Kigali", "Butare", "Nairobi", "Kampala", "Mwanza"],
                    value="Kigali",
                    interactive=True,
                )

                with gr.Row():
                    farmer_lat = gr.Number(
                        label="Latitude",
                        value=-1.9403,
                        precision=4,
                    )
                    farmer_lon = gr.Number(
                        label="Longitude",
                        value=29.8739,
                        precision=4,
                    )

                crop_types = gr.CheckboxGroup(
                    label="Crops",
                    choices=["maize", "beans", "tomatoes"],
                    value=["maize"],
                    interactive=True,
                )

                gr.Markdown("### 📊 Last Response Stats")
                stats_display = gr.JSON(
                    label="",
                    value={
                        "groundedness_score": "N/A",
                        "sources_used": 0,
                        "tools_called": [],
                    },
                )

        # Example questions
        gr.Markdown("### 💡 Example Questions")
        with gr.Row():
            gr.Examples(
                examples=[
                    ["When should I apply fertilizer to my maize?"],
                    ["What are the signs of tomato blight and how do I treat it?"],
                    ["What's the weather forecast for planting?"],
                    ["What are the current prices for beans?"],
                    ["How do I control aphids on my beans?"],
                    ["When is the best time to harvest my tomatoes?"],
                ],
                inputs=msg_input,
            )

        # Event handlers
        def submit_message(message, history, name, region, lat, lon, crops):
            yield from stream_chat_response(message, history, name, region, lat, lon, crops)

        send_btn.click(
            submit_message,
            inputs=[msg_input, chatbot, farmer_name, farmer_region, farmer_lat, farmer_lon, crop_types],
            outputs=[msg_input, chatbot, stats_display],
        )

        msg_input.submit(
            submit_message,
            inputs=[msg_input, chatbot, farmer_name, farmer_region, farmer_lat, farmer_lon, crop_types],
            outputs=[msg_input, chatbot, stats_display],
        )

        clear_btn.click(
            lambda: ([], {"groundedness_score": "N/A", "sources_used": 0, "tools_called": []}),
            outputs=[chatbot, stats_display],
        )

        def load_example():
            return "When should I apply fertilizer to my maize crop that is in the vegetative stage?"

        example_btn.click(load_example, outputs=[msg_input])

    return chat_interface
