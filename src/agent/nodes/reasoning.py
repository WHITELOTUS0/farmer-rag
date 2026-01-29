"""
Reasoning node for the agent graph.

Implements ReAct-style reasoning to decide whether to use tools
or generate a final response.
"""

import json
import logging
from typing import Dict, Any, Literal

from openai import OpenAI

from src.config.settings import get_settings
from src.agent.state import AgentState
from src.agent.prompts.system import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def reasoning_node(state: AgentState) -> Dict[str, Any]:
    """
    ReAct reasoning node that decides next action.

    This node:
    1. Analyzes the farmer's query and context
    2. Reviews any previous tool results
    3. Decides whether to call a tool or generate a response

    Args:
        state: Current agent state

    Returns:
        Updated state with reasoning results
    """
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    # Build context from previous tool calls
    tool_context = ""
    if state["tool_calls"]:
        tool_context = "\n\n## Previous Tool Results:\n"
        for tc in state["tool_calls"]:
            tool_context += f"\n### {tc['tool_name']}\n"
            tool_context += f"Input: {json.dumps(tc['tool_input'], indent=2)}\n"
            if tc['success']:
                # Truncate long outputs
                output_str = json.dumps(tc['tool_output'], indent=2, default=str)
                if len(output_str) > 2000:
                    output_str = output_str[:2000] + "\n... [truncated]"
                tool_context += f"Output: {output_str}\n"
            else:
                tool_context += f"Error: {tc['tool_output']}\n"

    # Build farmer context string
    farmer_context_str = "No farmer context available."
    if state["farmer_context"]:
        ctx = state["farmer_context"]
        farmer_context_str = f"""
Farmer: {ctx.get('farmer', {}).get('name', 'Unknown')}
Region: {ctx.get('farmer', {}).get('region', 'Unknown')}
Location: {ctx.get('farmer', {}).get('location', 'Unknown')}
"""
        # Add crop information
        for farm in ctx.get("farms", []):
            farmer_context_str += f"\nFarm: {farm.get('name', 'Unknown')}"
            for crop in farm.get("crops", []):
                farmer_context_str += f"\n  - {crop.get('type', 'Unknown')} at {crop.get('growth_stage', 'unknown')} stage"
                if crop.get("planting_date"):
                    farmer_context_str += f" (planted: {crop['planting_date']})"

    # Build the prompt
    user_message = f"""## Farmer's Question
{state["current_query"]}

## Farmer's Context
{farmer_context_str}
{tool_context}

## Instructions
Based on the above information, decide your next action:

1. If you need weather information for the farmer's location, call get_weather_forecast
2. If you need agricultural knowledge (farming practices, pest control, etc.), call query_agricultural_knowledge
3. If you need market prices, call get_market_prices
4. If you have enough information to provide a complete, accurate response, generate your response

Think step by step about what information you need.

Respond in JSON format:
{{
    "thought": "Your reasoning about what to do next",
    "action": "call_tool" or "final_response",
    "tool_name": "tool name if action is call_tool",
    "tool_args": {{}}, // tool arguments if action is call_tool
    "response": "your response if action is final_response"
}}"""

    # Define tools for the LLM
    tools = [
        {
            "type": "function",
            "function": {
                "name": "query_agricultural_knowledge",
                "description": "Search the agricultural knowledge base for farming practices, pest control, disease management, fertilizer recommendations, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query"
                        },
                        "crop_type": {
                            "type": "string",
                            "enum": ["maize", "beans", "tomatoes"],
                            "description": "Optional crop filter"
                        },
                        "topic": {
                            "type": "string",
                            "enum": ["fertilizer", "pest_control", "disease", "irrigation", "planting", "harvesting", "weeding", "soil"],
                            "description": "Optional topic filter"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_weather_forecast",
                "description": "Get weather forecast for a location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number",
                            "description": "Latitude of location"
                        },
                        "longitude": {
                            "type": "number",
                            "description": "Longitude of location"
                        },
                        "days": {
                            "type": "integer",
                            "description": "Number of forecast days (1-16)",
                            "default": 7
                        }
                    },
                    "required": ["latitude", "longitude"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_market_prices",
                "description": "Get market prices for crops",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "crop_type": {
                            "type": "string",
                            "enum": ["maize", "beans", "tomatoes"],
                            "description": "Type of crop"
                        },
                        "region": {
                            "type": "string",
                            "description": "Optional region filter"
                        }
                    },
                    "required": ["crop_type"]
                }
            }
        }
    ]

    try:
        response = client.chat.completions.create(
            model=settings.primary_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            tools=tools,
            tool_choice="auto",
            temperature=settings.model_temperature,
        )

        message = response.choices[0].message

        # Check if the model wants to call a tool
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            logger.info(f"Reasoning decided to call tool: {tool_name}")

            return {
                "messages": [{"role": "assistant", "content": f"Calling {tool_name}...", "tool_call": tool_call}],
                "should_continue": True,
                "iteration_count": state["iteration_count"] + 1,
                "_pending_tool": {"name": tool_name, "args": tool_args},
            }

        # Model wants to respond directly
        response_content = message.content

        # Try to parse as JSON for structured response
        try:
            parsed = json.loads(response_content)
            if "response" in parsed:
                response_content = parsed["response"]
        except json.JSONDecodeError:
            pass  # Use raw content

        logger.info("Reasoning decided to generate final response")

        return {
            "messages": [{"role": "assistant", "content": response_content}],
            "draft_response": response_content,
            "should_continue": False,
            "iteration_count": state["iteration_count"] + 1,
        }

    except Exception as e:
        logger.error(f"Reasoning node error: {e}")
        return {
            "error": f"Reasoning error: {str(e)}",
            "should_continue": False,
        }
