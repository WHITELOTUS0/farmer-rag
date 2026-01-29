"""
Tool executor node for the agent graph.

Executes tools based on the reasoning node's decisions.
"""

import logging
from typing import Dict, Any

from src.agent.state import AgentState, ToolCall
from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Global tool registry (initialized on first use)
_tool_registry = None


def get_tool_registry() -> ToolRegistry:
    """Get or create the global tool registry."""
    global _tool_registry
    if _tool_registry is None:
        from src.tools.registry import create_default_registry
        _tool_registry = create_default_registry()
    return _tool_registry


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

    tool_name = pending_tool["name"]
    tool_args = pending_tool["args"]

    logger.info(f"Executing tool: {tool_name} with args: {tool_args}")

    registry = get_tool_registry()
    result = registry.execute(tool_name, **tool_args)

    # Create tool call record
    tool_call_record: ToolCall = {
        "tool_name": tool_name,
        "tool_input": tool_args,
        "tool_output": result.data if result.success else result.error,
        "success": result.success,
    }

    # Build update
    updates: Dict[str, Any] = {
        "tool_calls": state.get("tool_calls", []) + [tool_call_record],
        "should_continue": True,  # Continue reasoning after tool execution
    }

    # If this was a knowledge base query, update retrieved sources
    if tool_name == "query_agricultural_knowledge" and result.success:
        if result.data and "results" in result.data:
            sources = [
                {
                    "text": r["text"],
                    "source": r["source"],
                    "source_id": r["source_id"],
                    "confidence": r["confidence"],
                }
                for r in result.data["results"]
            ]
            updates["retrieved_sources"] = state.get("retrieved_sources", []) + sources

    # Add tool result to messages for context
    tool_result_msg = {
        "role": "tool",
        "tool_name": tool_name,
        "content": result.to_string()[:3000],  # Truncate long results
    }
    updates["messages"] = [tool_result_msg]

    logger.info(f"Tool {tool_name} completed: success={result.success}")

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
