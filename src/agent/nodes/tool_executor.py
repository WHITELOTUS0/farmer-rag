"""
Tool executor node for the agent graph.

Executes tools based on the reasoning node's decisions.
"""

import logging
from typing import Dict, Any

from src.agent.state import AgentState, ToolCall
from src.tools import (
    get_weather_forecast,
    get_market_prices,
    query_agricultural_knowledge,
)

logger = logging.getLogger(__name__)

# Tool mapping for @tool decorated functions
_TOOL_MAP = {
    "get_weather_forecast": get_weather_forecast,
    "get_market_prices": get_market_prices,
    "query_agricultural_knowledge": query_agricultural_knowledge,
}


def tool_executor_node(state: AgentState) -> Dict[str, Any]:
    """
    Execute a tool based on the pending tool call.

    This node:
    1. Gets the pending tool call from state
    2. Executes the tool with provided arguments
    3. Records the result in tool_calls history
    4. Updates retrieved_sources if knowledge base was queried

    Args:
        state: Current agent state

    Returns:
        Updated state with tool execution results
    """
    # Get the pending tool call from the last message
    pending_tool = None
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, dict) and "_pending_tool" in msg:
            pending_tool = msg["_pending_tool"]
            break

    # Also check state directly (set by reasoning node)
    if not pending_tool and "_pending_tool" in state:
        pending_tool = state["_pending_tool"]

    if not pending_tool:
        logger.warning("Tool executor called but no pending tool found")
        return {
            "should_continue": True,  # Continue to reasoning
        }

    pending_tool = pending_tool or {}
    tool_name = pending_tool.get("name") or ""
    tool_args = pending_tool.get("args") or {}
    retry_count = pending_tool.get("retry_count", 0)

    logger.info(f"🔧 ACT: Executing tool: {tool_name} with args: {tool_args} (retry: {retry_count})")

    # Get tool function
    tool_func = _TOOL_MAP.get(tool_name)
    if not tool_func:
        logger.error(f"Unknown tool: {tool_name}")
        tool_call_record: ToolCall = {
            "tool_name": tool_name,
            "tool_input": tool_args,
            "tool_output": f"Unknown tool: {tool_name}",
            "success": False,
            "retry_count": retry_count,
        }
        return {
            "tool_calls": state.get("tool_calls", []) + [tool_call_record],
            "should_continue": False,
            "error": f"Unknown tool: {tool_name}",
        }

    # Execute tool
    try:
        result = tool_func.invoke(tool_args)
        success = True
        output = result
        error = None
    except Exception as e:
        logger.error(f"Tool {tool_name} execution failed: {e}")
        success = False
        output = None
        error = str(e)

    # Create tool call record
    tool_call_record: ToolCall = {
        "tool_name": tool_name,
        "tool_input": tool_args,
        "tool_output": output if success else error,
        "success": success,
        "retry_count": retry_count,
    }

    # Build update
    updates: Dict[str, Any] = {
        "tool_calls": state.get("tool_calls", []) + [tool_call_record],
        "should_continue": True,  # Continue reasoning after tool execution
        "_pending_tool": None,    # Clear pending tool so routing doesn't re-execute it
    }

    # If this was a knowledge base query, update retrieved sources
    if tool_name == "query_agricultural_knowledge" and success:
        if isinstance(output, dict) and "results" in output:
            sources = [
                {
                    "text": (r or {}).get("text", ""),
                    "source": (r or {}).get("source", "Unknown"),
                    "source_id": (r or {}).get("source_id", ""),
                    "confidence": (r or {}).get("confidence", 0.0),
                }
                for r in (output.get("results") or [])
                if r is not None
            ]
            updates["retrieved_sources"] = (state.get("retrieved_sources") or []) + sources

    # Add tool result to messages for context
    import json
    tool_result_msg = {
        "role": "tool",
        "tool_name": tool_name,
        "content": json.dumps(output, default=str)[:3000] if success else f"Error: {error}",
    }
    updates["messages"] = state.get("messages", []) + [tool_result_msg]

    logger.info(f"✅ Tool {tool_name} completed: success={success}")

    return updates


def execute_tool_directly(
    tool_name: str,
    **kwargs,
) -> Dict[str, Any]:
    """
    Execute a tool directly without going through the graph.

    Useful for testing or standalone tool usage.

    Args:
        tool_name: Name of the tool to execute
        **kwargs: Tool arguments

    Returns:
        Tool result as dictionary
    """
    registry = get_tool_registry()
    result = registry.execute(tool_name, **kwargs)
    return result.to_dict()
