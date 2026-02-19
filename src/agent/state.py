"""
Agent state definition for LangGraph.

Defines the typed state that flows through the agent graph,
tracking conversation history, tool calls, and verification results.
"""

from typing import List, Dict, Any, Optional, Annotated
from typing_extensions import TypedDict
import operator


class ToolCall(TypedDict):
    """Record of a tool invocation."""
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: Any
    success: bool


class VerificationResult(TypedDict):
    """Result of response verification."""
    groundedness_score: float
    claims: List[Dict[str, Any]]
    is_reliable: bool
    suggestion: Optional[str]


class AgentState(TypedDict):
    """
    State that flows through the LangGraph agent.

    Attributes:
        messages: Conversation history (accumulates with each turn)
        farmer_context: Information about the farmer (crops, location, etc.)
        current_query: The current user query being processed
        tool_calls: History of tool invocations in this turn
        retrieved_sources: Documents retrieved from knowledge base
        draft_response: The agent's draft response before verification
        final_response: The verified final response
        verification: Verification results including groundedness score
        iteration_count: Number of reasoning iterations
        should_continue: Whether to continue the reasoning loop
        error: Any error that occurred
    """
    # Conversation
    messages: Annotated[List[Dict[str, Any]], operator.add]
    current_query: str

    # Context
    farmer_context: Optional[Dict[str, Any]]

    # Tool execution
    tool_calls: List[ToolCall]
    retrieved_sources: List[Dict[str, Any]]

    # Response generation
    draft_response: Optional[str]
    final_response: Optional[str]

    # Verification
    verification: Optional[VerificationResult]

    # Control flow
    iteration_count: int
    should_continue: bool
    error: Optional[str]

    # Pending tool to execute (must be in schema so LangGraph persists it)
    _pending_tool: Optional[Dict[str, Any]]


def create_initial_state(
    query: str,
    farmer_context: Optional[Dict[str, Any]] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
) -> AgentState:
    """
    Create initial state for a new agent invocation.

    Args:
        query: The user's query
        farmer_context: Optional farmer context
        messages: Optional conversation history

    Returns:
        Initialized AgentState
    """
    return AgentState(
        messages=messages or [],
        current_query=query,
        farmer_context=farmer_context,
        tool_calls=[],
        retrieved_sources=[],
        draft_response=None,
        final_response=None,
        verification=None,
        iteration_count=0,
        should_continue=True,
        error=None,
        _pending_tool=None,
    )
