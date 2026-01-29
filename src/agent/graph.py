"""
LangGraph-based agent orchestration.

Implements the ReAct-style reasoning loop with verification
for the agricultural advisory agent.
"""

import logging
from typing import Dict, Any, Optional, Literal

from langgraph.graph import StateGraph, END

from src.config.settings import get_settings
from src.agent.state import AgentState, create_initial_state
from src.agent.nodes.reasoning import reasoning_node
from src.agent.nodes.tool_executor import tool_executor_node
from src.agent.nodes.verifier import verification_node

logger = logging.getLogger(__name__)


def should_continue(state: AgentState) -> Literal["tools", "verify", "end"]:
    """
    Determine the next step in the agent graph.

    Args:
        state: Current agent state

    Returns:
        Next node to execute
    """
    settings = get_settings()

    # Check for errors
    if state.get("error"):
        return "end"

    # Check iteration limit
    if state.get("iteration_count", 0) >= settings.max_tool_calls_per_turn:
        logger.warning("Max iterations reached, forcing response")
        return "verify"

    # Check if we have a draft response ready for verification
    if state.get("draft_response") and not state.get("should_continue", True):
        return "verify"

    # Check if there's a pending tool call
    if state.get("_pending_tool"):
        return "tools"

    # Default: continue reasoning
    return "end"


def route_after_reasoning(state: AgentState) -> Literal["tools", "verify", "end"]:
    """
    Route after the reasoning node.

    Args:
        state: Current agent state

    Returns:
        Next node to execute
    """
    # If there's a pending tool, execute it
    if "_pending_tool" in state and state["_pending_tool"]:
        return "tools"

    # If there's a draft response, verify it
    if state.get("draft_response"):
        return "verify"

    # If should_continue is False, we're done
    if not state.get("should_continue", True):
        return "end"

    return "end"


def route_after_tools(state: AgentState) -> Literal["reasoning", "end"]:
    """
    Route after tool execution.

    Args:
        state: Current agent state

    Returns:
        Next node to execute
    """
    settings = get_settings()

    # Check iteration limit
    if state.get("iteration_count", 0) >= settings.max_tool_calls_per_turn:
        return "end"

    # Go back to reasoning to process tool results
    return "reasoning"


def build_agent_graph() -> StateGraph:
    """
    Build the LangGraph agent graph.

    Graph structure:
    START -> reasoning -> tools -> reasoning (loop)
                      -> verify -> END

    Returns:
        Compiled StateGraph
    """
    # Create the graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("reasoning", reasoning_node)
    workflow.add_node("tools", tool_executor_node)
    workflow.add_node("verify", verification_node)

    # Set entry point
    workflow.set_entry_point("reasoning")

    # Add conditional edges from reasoning
    workflow.add_conditional_edges(
        "reasoning",
        route_after_reasoning,
        {
            "tools": "tools",
            "verify": "verify",
            "end": END,
        }
    )

    # Add conditional edges from tools
    workflow.add_conditional_edges(
        "tools",
        route_after_tools,
        {
            "reasoning": "reasoning",
            "end": END,
        }
    )

    # Verify always goes to END
    workflow.add_edge("verify", END)

    return workflow.compile()


class FarmerAdvisoryAgent:
    """
    High-level interface for the farmer advisory agent.

    Provides a simple API for running queries through the agent
    with proper state management.
    """

    def __init__(self):
        """Initialize the agent with the compiled graph."""
        self.graph = build_agent_graph()
        self.settings = get_settings()

    def run(
        self,
        query: str,
        farmer_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Run a query through the agent.

        Args:
            query: The farmer's question
            farmer_context: Optional context about the farmer
            conversation_history: Optional previous messages

        Returns:
            Dictionary with response and metadata
        """
        # Create initial state
        initial_state = create_initial_state(
            query=query,
            farmer_context=farmer_context,
            messages=conversation_history,
        )

        # Add user message
        initial_state["messages"] = initial_state.get("messages", []) + [
            {"role": "user", "content": query}
        ]

        logger.info(f"Running agent for query: {query[:50]}...")

        try:
            # Run the graph
            final_state = self.graph.invoke(initial_state)

            # Extract results
            response = final_state.get("final_response") or final_state.get("draft_response", "")
            verification = final_state.get("verification", {})

            return {
                "success": True,
                "response": response,
                "groundedness_score": verification.get("groundedness_score", 0.0),
                "is_reliable": verification.get("is_reliable", False),
                "sources_used": len(final_state.get("retrieved_sources", [])),
                "tools_called": [tc["tool_name"] for tc in final_state.get("tool_calls", [])],
                "verification_details": verification,
                "messages": final_state.get("messages", []),
            }

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return {
                "success": False,
                "response": f"I apologize, but I encountered an error: {str(e)}",
                "groundedness_score": 0.0,
                "is_reliable": False,
                "sources_used": 0,
                "tools_called": [],
                "error": str(e),
            }

    async def arun(
        self,
        query: str,
        farmer_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Async version of run.

        Args:
            query: The farmer's question
            farmer_context: Optional context about the farmer
            conversation_history: Optional previous messages

        Returns:
            Dictionary with response and metadata
        """
        # For now, just wrap sync version
        # TODO: Implement true async execution
        return self.run(query, farmer_context, conversation_history)


def create_agent() -> FarmerAdvisoryAgent:
    """
    Factory function to create a configured agent.

    Returns:
        Configured FarmerAdvisoryAgent instance
    """
    return FarmerAdvisoryAgent()


# Convenience function for quick testing
def quick_query(query: str, farmer_context: Optional[Dict[str, Any]] = None) -> str:
    """
    Quick function to run a single query.

    Args:
        query: The question to ask
        farmer_context: Optional farmer context

    Returns:
        The agent's response
    """
    agent = create_agent()
    result = agent.run(query, farmer_context)
    return result["response"]
