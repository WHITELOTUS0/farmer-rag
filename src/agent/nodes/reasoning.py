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
    for tc in (state.get("tool_calls") or []):
        if tc is None:
            continue
        tc = tc or {}
        if not tool_context:
            tool_context = "\n\n## Previous Tool Results:\n"
        tool_context += f"\n### {tc.get('tool_name', 'unknown')}\n"
        tool_context += f"Input: {json.dumps(tc.get('tool_input', {}), indent=2)}\n"
        if tc.get('success'):
            # Truncate long outputs
            output_str = json.dumps(tc.get('tool_output', ''), indent=2, default=str)
            if len(output_str) > 2000:
                output_str = output_str[:2000] + "\n... [truncated]"
            tool_context += f"Output: {output_str}\n"
        else:
            tool_context += f"Error: {tc.get('tool_output', '')}\n"

    # Build farmer context string (defensive: handle None for farmer/farms/crops)
    # Use explicit "registered profile" framing so the LLM treats this as
    # confirmed knowledge, not speculation.
    farmer_context_str = "No registered profile found for this farmer."
    if state["farmer_context"]:
        ctx = state["farmer_context"] or {}
        farmer = ctx.get("farmer") or {}
        lines = ["This farmer's registered profile:"]
        lines.append(f"  Name: {farmer.get('name', 'Unknown')}")
        region = farmer.get('region')
        if region and region != 'Unknown':
            lines.append(f"  Region: {region}")
        loc = farmer.get('location')
        if loc and loc != 'Unknown':
            if isinstance(loc, dict):
                lines.append(f"  Location: lat={loc.get('lat')}, lon={loc.get('lon')}")
            else:
                lines.append(f"  Location: {loc}")

        farms = ctx.get("farms") or []
        if farms:
            lines.append("  Registered farms and active crops:")
            for farm in farms:
                if farm is None:
                    continue
                farm_name = (farm or {}).get('name', 'Unknown')
                lines.append(f"    Farm: {farm_name}")
                for crop in ((farm or {}).get("crops") or []):
                    if crop is None:
                        continue
                    crop = crop or {}
                    crop_line = f"      - {crop.get('type', 'Unknown')} at {crop.get('growth_stage', 'unknown')} stage"
                    if crop.get("planting_date"):
                        crop_line += f" (planted: {crop['planting_date']})"
                    lines.append(crop_line)
        else:
            lines.append("  No farms registered yet.")

        farmer_context_str = "\n".join(lines)

    # Build the prompt
    user_message = f"""## Farmer's Question
{state["current_query"]}

## What You Already Know About This Farmer (confirmed from their profile)
{farmer_context_str}
{tool_context}

## Instructions
Decide your next action. **Only call tools when the question actually requires specific data.**

**Respond directly (action: final_response) for:**
- Greetings, introductions, "who are you", "how can you help"
- Questions about what you know about the farmer — answer using the profile above
- Simple clarifications or follow-up questions
- General conversational replies
- Questions you can answer from context alone

**Call tools only when the question needs:**
- Weather forecasts → get_weather_forecast (use the farmer's registered lat/lon from the profile above; if not available, ask for their location)
- Market/crop prices → get_market_prices (use the farmer's registered region if available)
- Specific farming practices, pest control, fertilizer dosages, disease management → query_agricultural_knowledge

If in doubt, prefer responding directly. Call ONE tool at a time (do not use multi_tool_use.parallel).

Respond with valid JSON only (no markdown, no code blocks):
{{
    "thought": "Your reasoning",
    "action": "call_tool" or "final_response",
    "tool_name": "get_weather_forecast | get_market_prices | query_agricultural_knowledge",
    "tool_args": {{}},
    "response": "only if action is final_response"
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

        # Check if the model wants to call a tool (native function calling)
        if message.tool_calls:
            tool_call = message.tool_calls[0]
            tool_name = tool_call.function.name
            raw_args = tool_call.function.arguments or "{}"
            try:
                tool_args = json.loads(raw_args) or {}
            except json.JSONDecodeError:
                tool_args = {}

            # multi_tool_use.parallel via native function calling: pick first uncalled tool
            if tool_name == "multi_tool_use.parallel":
                already_called = {
                    (tc or {}).get("tool_name")
                    for tc in (state.get("tool_calls") or [])
                    if tc and (tc or {}).get("success")
                }
                for tu in (tool_args.get("tool_uses") or []):
                    if tu is None:
                        continue
                    candidate = (tu or {}).get("recipient_name", "").replace("functions.", "")
                    if candidate and candidate not in already_called:
                        tool_name = candidate
                        tool_args = (tu or {}).get("parameters", {}) or {}
                        break
                else:
                    # All parallel tools done — fall through to JSON / text parsing
                    tool_name = None

            if tool_name and tool_name in ["get_weather_forecast", "get_market_prices", "query_agricultural_knowledge"]:
                logger.info(f"Reasoning decided to call tool: {tool_name}")
                return {
                    "messages": [{"role": "assistant", "content": f"Calling {tool_name}...", "tool_call": tool_call}],
                    "should_continue": True,
                    "iteration_count": state["iteration_count"] + 1,
                    "_pending_tool": {"name": tool_name, "args": tool_args},
                }

        # Model wants to respond directly - check if it's JSON with tool calls
        response_content = message.content or ""

        # Strip markdown code blocks (LLM often wraps JSON in ```json ... ```)
        _raw = response_content.strip()
        if _raw.startswith("```"):
            parts = _raw.split("```", 2)
            if len(parts) > 1:
                _raw = parts[1]
                if _raw.lower().startswith("json"):
                    _raw = _raw[4:].lstrip()
                response_content = _raw

        # Try to parse as JSON for structured response
        try:
            parsed = json.loads(response_content)
            
            # Check if LLM wants to call a tool (even though it didn't use function calling)
            if parsed.get("action") == "call_tool":
                tool_name = (parsed.get("tool_name", "") or "").replace("functions.", "").strip()
                
                # Handle multi_tool_use.parallel by picking the first uncalled tool
                if tool_name == "multi_tool_use.parallel":
                    tool_uses = (parsed.get("tool_args") or {}).get("tool_uses") or []
                    if tool_uses:
                        # Skip tools that have already been successfully called
                        already_called = {
                            (tc or {}).get("tool_name")
                            for tc in (state.get("tool_calls") or [])
                            if tc and (tc or {}).get("success")
                        }
                        next_tool_use = None
                        for tu in tool_uses:
                            if tu is None:
                                continue
                            candidate = (tu or {}).get("recipient_name", "").replace("functions.", "")
                            if candidate and candidate not in already_called:
                                next_tool_use = (candidate, (tu or {}).get("parameters", {}) or {})
                                break

                        if next_tool_use:
                            tool_name, tool_args = next_tool_use
                            logger.info(f"Reasoning decided to call tool (from parallel): {tool_name}")
                            return {
                                "messages": [{"role": "assistant", "content": f"Calling {tool_name}...", "tool_call": {"function": {"name": tool_name, "arguments": json.dumps(tool_args)}}}],
                                "should_continue": True,
                                "iteration_count": state["iteration_count"] + 1,
                                "_pending_tool": {"name": tool_name, "args": tool_args},
                            }
                        # All tools in the parallel set have been called — fall through to generate response
                elif tool_name in ["get_weather_forecast", "get_market_prices", "query_agricultural_knowledge"]:
                    # Direct tool call from JSON
                    tool_args = (parsed.get("tool_args") or {}) or {}
                    logger.info(f"Reasoning decided to call tool (from JSON): {tool_name}")
                    
                    return {
                        "messages": [{"role": "assistant", "content": f"Calling {tool_name}...", "tool_call": {"function": {"name": tool_name, "arguments": json.dumps(tool_args)}}}],
                        "should_continue": True,
                        "iteration_count": state["iteration_count"] + 1,
                        "_pending_tool": {"name": tool_name, "args": tool_args},
                    }
            
            # If it's a final response
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
            "_pending_tool": None,  # Clear any stale pending tool
        }

    except Exception as e:
        logger.error(f"Reasoning node error: {e}")
        return {
            "error": f"Reasoning error: {str(e)}",
            "should_continue": False,
        }
