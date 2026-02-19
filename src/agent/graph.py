"""
LangGraph-based agent orchestration with explicit role-based nodes.

Implements a multi-node architecture:
- Reasoning Node: Plans next action (tool call or response)
- Tool Executor Node: Executes tools
- Verification Node: Verifies response groundedness
- Adaptive Control: Re-retrieves on low scores, retries on failures
"""

import asyncio
import json
import logging
import threading
import traceback
from typing import Any, Callable, Dict, Optional, List

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from src.config.settings import get_settings
from src.agent.state import AgentState, create_initial_state
from src.agent.nodes.reasoning import reasoning_node
from src.agent.nodes.tool_executor import tool_executor_node
from src.agent.nodes.verifier import verification_node
from src.retrieval.retriever import Retriever

logger = logging.getLogger(__name__)

# Patterns that indicate simple conversational queries (no tools needed)
_SIMPLE_QUERY_PATTERNS = (
    "hello", "hi ", "hey ", "good morning", "good afternoon", "good evening",
    "who are you", "what are you", "how can you help", "how do you help",
    "introduce yourself", "tell me about yourself", "what can you do",
    "thanks", "thank you", "bye", "goodbye",
)
# If query contains these, skip fast path (needs tools)
_AGRICULTURAL_KEYWORDS = (
    "fertilizer", "pest", "weather", "rain", "maize", "bean", "tomato",
    "crop", "plant", "harvest", "price", "market", "spray", "weed",
    "disease", "irrigation", "soil", "seed", "yield", "acre", "hectare",
)


def _is_simple_conversational_query(query: str) -> bool:
    """Detect greetings/introductions that don't need tools or verification."""
    if not query or not isinstance(query, str):
        return False
    q = query.lower().strip()
    if len(q) > 120:  # Long queries likely need tools
        return False
    if any(kw in q for kw in _AGRICULTURAL_KEYWORDS):
        return False  # Agricultural question - use full pipeline
    return any(p in q for p in _SIMPLE_QUERY_PATTERNS)


def _get_fast_conversational_response(
    query: str, farmer_context: Optional[Dict[str, Any]]
) -> str:
    """Return a quick, friendly response for simple conversational queries."""
    name = "there"
    if farmer_context:
        farmer = (farmer_context or {}).get("farmer") or {}
        if farmer.get("name"):
            name = str(farmer["name"]).split()[0]  # First name only
    return (
        f"Hello {name}! I'm your Agricultural Advisory Agent. "
        "I can help with farming advice—weather forecasts, crop management, pest control, "
        "fertilizer recommendations, and market prices for maize, beans, and tomatoes. "
        "What would you like to know?"
    )


def _should_continue(state: AgentState) -> str:
    """
    Router function to decide next step in the graph.
    
    Implements adaptive control:
    - If error occurred → END
    - If should_continue is False → go to verification
    - If iteration limit exceeded → END with escalation
    - If pending tool → execute tool
    - Otherwise → continue reasoning
    """
    settings = get_settings()
    max_iterations = getattr(settings, "max_agent_iterations", 10)
    
    # Check for errors
    if state.get("error"):
        logger.warning(f"Agent error detected: {state['error']}")
        return "end"
    
    # Check iteration limit (adaptive control: escalation)
    if state["iteration_count"] >= max_iterations:
        logger.warning(f"Max iterations ({max_iterations}) reached. Escalating.")
        return "end"
    
    # Check if we should continue
    if not state.get("should_continue", True):
        return "verify"
    
    # Check if there's a pending tool to execute
    if state.get("_pending_tool") is not None:
        return "execute_tool"

    # Otherwise, continue reasoning
    return "reason"


def _adaptive_retrieval_check(state: AgentState) -> Dict[str, Any]:
    """
    Adaptive control: Re-retrieve if groundedness is low.

    Returns only the changed keys (delta) to avoid the operator.add
    reducer on `messages` duplicating the full message list.
    """
    settings = get_settings()
    verification = state.get("verification")

    if not (verification and not verification.get("is_reliable", True)):
        return {}

    groundedness = verification.get("groundedness_score", 1.0)
    re_retrieval_count = state.get("_re_retrieval_count", 0)
    max_re_retrieval = getattr(settings, "max_verification_retries", 2)

    # Bug fix: check re-retrieval limit; previously there was no limit and
    # iteration_count was decremented here, completely cancelling the +1 from
    # reasoning_node and making max_iterations unreachable.
    if groundedness >= settings.confidence_threshold or re_retrieval_count >= max_re_retrieval:
        return {}

    logger.info(
        f"🔄 ADAPTIVE: Low groundedness ({groundedness:.2f}), "
        f"triggering re-retrieval (attempt {re_retrieval_count + 1}/{max_re_retrieval})"
    )

    retriever = Retriever()
    new_sources = retriever.retrieve(
        query=state["current_query"],
        top_k=settings.retrieval_top_k + 3,
        min_confidence=max(0.0, settings.confidence_threshold - 0.1),
    )

    if not new_sources:
        return {}

    logger.info(f"🔄 ADAPTIVE: Re-retrieved {len(new_sources)} additional sources")
    existing = state.get("retrieved_sources") or []
    return {
        "retrieved_sources": existing + [
            {
                "text": r.text,
                "source": r.source_name,
                "source_id": r.source_id,
                "confidence": r.similarity_score,
            }
            for r in new_sources
        ],
        "should_continue": True,
        "_re_retrieval_count": re_retrieval_count + 1,
        # Do NOT touch iteration_count — decrementing it here was what made
        # the max_iterations guard ineffective (the infinite loop root cause).
    }


def _tool_retry_handler(state: AgentState) -> Dict[str, Any]:
    """
    Adaptive control: Retry failed tools with alternative approaches.

    Returns only the changed keys (delta) to avoid the operator.add
    reducer on `messages` duplicating the full message list.
    """
    tool_calls = state.get("tool_calls") or []
    if not tool_calls:
        return {}

    last_call = tool_calls[-1] or {}
    if last_call.get("success", True):
        return {}

    tool_name = last_call.get("tool_name", "")
    retry_count = last_call.get("retry_count", 0)

    if retry_count < 2:
        logger.info(f"🔄 ADAPTIVE: Tool {tool_name} failed, retrying (attempt {retry_count + 1})")
        return {
            "_pending_tool": {
                "name": tool_name,
                "args": last_call.get("tool_input", {}),
                "retry_count": retry_count + 1,
            },
            "should_continue": True,
        }

    logger.warning(f"⚠️ ADAPTIVE: Tool {tool_name} failed after {retry_count} retries. Escalating.")
    if tool_name == "query_agricultural_knowledge":
        logger.info("🔄 ADAPTIVE: Trying knowledge base with broader query")
        return {
            "_pending_tool": {
                "name": "query_agricultural_knowledge",
                "args": {"query": state["current_query"]},
                # Bug fix: keep retry_count at 2 (not 0) so this broader attempt
                # can itself retry once more but won't loop back here indefinitely.
                "retry_count": 2,
            },
            "should_continue": True,
        }

    # All retries exhausted for other tools — let reasoning decide what to do.
    return {}


def _create_graph() -> StateGraph:
    """
    Create the agent graph with explicit role-based nodes.
    
    Graph structure:
    START → reasoning → [execute_tool | verify] → [reasoning | END]
    
    With adaptive control:
    - Re-retrieval on low groundedness
    - Tool retries on failure
    - Iteration limit escalation
    """
    # Create the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes (explicit role separation)
    workflow.add_node("reason", reasoning_node)  # Planning node
    workflow.add_node("execute_tool", tool_executor_node)  # Execution node
    workflow.add_node("verify", verification_node)  # Critique/Evaluation node
    
    # Add adaptive control nodes
    workflow.add_node("adaptive_retrieval", _adaptive_retrieval_check)
    workflow.add_node("tool_retry", _tool_retry_handler)
    
    # Set entry point
    workflow.set_entry_point("reason")
    
    # Add edges with routing logic
    workflow.add_conditional_edges(
        "reason",
        _should_continue,
        {
            "execute_tool": "execute_tool",
            "verify": "verify",
            "reason": "reason",   # self-loop when no pending tool yet
            "end": END,
        }
    )
    
    # After tool execution, check for retries, then continue reasoning
    workflow.add_edge("execute_tool", "tool_retry")
    workflow.add_edge("tool_retry", "reason")
    
    # After verification, check for adaptive re-retrieval
    workflow.add_edge("verify", "adaptive_retrieval")
    workflow.add_conditional_edges(
        "adaptive_retrieval",
        lambda s: "reason" if s.get("should_continue", False) else "end",
        {
            "reason": "reason",
            "end": END,
        }
    )
    
    return workflow.compile(checkpointer=MemorySaver())


class FarmerAdvisoryAgent:
    """
    High-level interface for the farmer advisory agent.
    
    Uses explicit role-based nodes:
    - Planning (reasoning_node)
    - Execution (tool_executor_node)
    - Critique (verification_node)
    
    Implements adaptive control:
    - Re-retrieval on low groundedness
    - Tool retries on failure
    - Iteration limit escalation
    """

    def __init__(self):
        """Initialize the agent with custom role-based graph."""
        self.settings = get_settings()
        self.graph = _create_graph()
        logger.info("✅ Agent initialized with role-based architecture (Planning → Execution → Critique)")

    def run(
        self,
        query: str,
        farmer_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[list] = None,
        callbacks: Optional[List[BaseCallbackHandler]] = None,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """
        Run a query through the agent with full Observe → Reason → Decide → Act → Evaluate → Update cycle.
        
        Args:
            query: The farmer's question
            farmer_context: Optional context about the farmer
            conversation_history: Optional previous messages
            
        Returns:
            Dictionary with response and metadata
        """
        logger.info("=" * 80)
        logger.info(f"🔍 OBSERVE: Processing query: {query[:50]}...")
        logger.info("=" * 80)

        # Fast path: simple conversational queries (greetings, introductions)
        if _is_simple_conversational_query(query):
            logger.info("⚡ FAST PATH: Simple conversational query, skipping tools")
            response = _get_fast_conversational_response(query, farmer_context)
            return {
                "success": True,
                "response": response,
                "groundedness_score": 1.0,
                "is_reliable": True,
                "sources_used": 0,
                "tools_called": [],
                "verification_details": {"groundedness_score": 1.0, "is_reliable": True},
                "iteration_count": 0,
                "adaptive_actions": [],
                "messages": [],
                "tool_call_details": [],
                "tool_call_records": [],
                "source_summaries": [],
            }

        try:
            # Create initial state
            initial_state = create_initial_state(
                query=query,
                farmer_context=farmer_context,
                messages=conversation_history or [],
            )

            # Run the graph with timeout protection
            config = {"thread_id": "default"}
            final_state = initial_state
            step_count = 0
            max_steps = 30  # Safety limit to prevent infinite loops (reduced from 50)
            seen_tool_calls = set()  # Track tool calls to detect loops
            
            # Execute graph with logging
            for step_output in self.graph.stream(initial_state, config=config):
                # LangGraph 0.0.x yields None for nodes that return {} (empty update).
                # Guard here to prevent AttributeError on .items().
                if not step_output:
                    continue

                step_count += 1

                # Safety check: prevent infinite loops
                if step_count > max_steps:
                    logger.error(f"⚠️ SAFETY: Max steps ({max_steps}) reached. Forcing end.")
                    final_state["error"] = f"Max steps ({max_steps}) exceeded"
                    final_state["should_continue"] = False
                    if not final_state.get("final_response"):
                        final_state["final_response"] = "Agent execution exceeded maximum steps. Please try a simpler query."
                    break

                # step_output is a dict like {"node_name": state_update}
                for node_name, state_update in step_output.items():
                    logger.info(f"📊 STEP {step_count}: Node '{node_name}' executed")

                    # state_update can be None when a node returns {} in LangGraph 0.0.x
                    if state_update is None:
                        continue

                    # Merge state updates
                    for key, value in state_update.items():
                        if key == "messages" and key in final_state:
                            # Append messages (guard: may be None)
                            lst = final_state[key]
                            if lst is not None:
                                lst.extend(value if isinstance(value, list) else [value])
                            else:
                                final_state[key] = value if isinstance(value, list) else [value]
                        elif key == "tool_calls" and key in final_state:
                            # Append tool calls (guard: may be None)
                            lst = final_state[key]
                            if lst is not None:
                                lst.extend(value if isinstance(value, list) else [value])
                            else:
                                final_state[key] = value if isinstance(value, list) else [value]
                        elif key == "retrieved_sources" and key in final_state:
                            # Append sources (guard: final_state[key] may be None)
                            lst = final_state[key]
                            if lst is None:
                                final_state[key] = value if isinstance(value, list) else [value]
                            else:
                                lst.extend(value if isinstance(value, list) else [value])
                        else:
                            # Replace value
                            final_state[key] = value
                    
                    logger.info(f"   └─ Iteration: {final_state.get('iteration_count', 0)}")
                    logger.info(f"   └─ Should continue: {final_state.get('should_continue', False)}")
                    
                    # Detect infinite loops: same tool call repeated many times
                    _pt = final_state.get("_pending_tool")
                    if _pt is not None:
                        _pt = _pt or {}
                        tool_key = f"{_pt.get('name', '')}:{str(_pt.get('args', {}))}"
                        if tool_key in seen_tool_calls:
                            logger.warning(f"⚠️ LOOP DETECTED: Same tool call repeated. Breaking loop.")
                            final_state["error"] = "Infinite loop detected: same tool call repeated"
                            final_state["should_continue"] = False
                            if not final_state.get("final_response") and not final_state.get("draft_response"):
                                final_state["final_response"] = (
                                    "I encountered a processing loop and couldn't complete a verified response. "
                                    "Please try rephrasing your question or asking something more specific."
                                )
                            break
                        seen_tool_calls.add(tool_key)
                        if len(seen_tool_calls) > 10:
                            seen_tool_calls.clear()  # Reset to prevent memory issues
                    
                    # Early exit if we have a final response and shouldn't continue
                    if final_state.get("final_response") and not final_state.get("should_continue", False):
                        logger.info("✅ Final response generated, ending execution")
                        break
                    
                    if "_pending_tool" in final_state:
                        tool = final_state.get("_pending_tool") or {}
                        tool_name = tool.get("name", "unknown")
                        logger.info(f"   └─ Pending tool: {tool_name}")
                        if progress_callback and tool_name:
                            try:
                                progress_callback("tool_start", {"tool": tool_name})
                            except Exception:
                                pass
                    
                    if "verification" in final_state and final_state["verification"]:
                        v = final_state["verification"]
                        logger.info(f"   └─ Groundedness: {v.get('groundedness_score', 0.0):.2f}")
                        logger.info(f"   └─ Reliable: {v.get('is_reliable', False)}")
                    
                    if "error" in final_state and final_state["error"]:
                        logger.error(f"   └─ Error: {final_state['error']}")
                        break

                # Exit outer loop when done — otherwise stream keeps running (reasoning/tools)
                if final_state.get("error") or (
                    final_state.get("final_response")
                    and not final_state.get("should_continue", True)
                ):
                    break

            # Extract results (guard: both can be None when loop/max-steps breaks before verify)
            response = (
                final_state.get("final_response")
                or final_state.get("draft_response")
                or "I apologize, but I couldn't generate a response. Please try again or rephrasing your question."
            )
            verification = final_state.get("verification") or {}
            tool_calls = final_state.get("tool_calls") or []
            retrieved_sources = final_state.get("retrieved_sources") or []
            
            # Log final state
            logger.info("=" * 80)
            logger.info("✅ FINAL STATE:")
            logger.info(f"   └─ Response generated: {len(response or '')} chars")
            logger.info(f"   └─ Groundedness: {verification.get('groundedness_score', 0.0):.2f}")
            logger.info(f"   └─ Tools called: {len(tool_calls)}")
            logger.info(f"   └─ Sources retrieved: {len(retrieved_sources)}")
            logger.info(f"   └─ Iterations: {final_state.get('iteration_count', 0)}")
            logger.info("=" * 80)
            
            # Build detailed result for trace
            result = {
                "success": True,
                "response": response,
                "groundedness_score": verification.get("groundedness_score", 0.0),
                "is_reliable": verification.get("is_reliable", False),
                "sources_used": len(retrieved_sources),
                "tools_called": [(tc or {}).get("tool_name", "unknown") for tc in (tool_calls or []) if tc],
                "verification_details": verification,
                "iteration_count": final_state.get("iteration_count", 0),
                "adaptive_actions": [
                    "re_retrieval" if len(retrieved_sources) > len([s for s in retrieved_sources if s.get("confidence", 0) > 0.8]) else None,
                    "tool_retry" if any(tc.get("retry_count", 0) > 0 for tc in tool_calls) else None,
                ],
                # Include messages for trace (sanitize for JSON)
                "messages": [
                    {
                        "role": (msg or {}).get("role", "unknown"),
                        "content": str((msg or {}).get("content", ""))[:2000],  # Truncate long content
                    }
                    for msg in (final_state.get("messages") or [])
                    if msg is not None
                ],
                # Include tool call details for trace
                "tool_call_details": [
                    {
                        "tool_name": (tc or {}).get("tool_name", "unknown"),
                        "success": (tc or {}).get("success", False),
                        "retry_count": (tc or {}).get("retry_count", 0),
                        "input_summary": str((tc or {}).get("tool_input", {}))[:500],
                        "output_summary": str((tc or {}).get("tool_output", ""))[:1000] if (tc or {}).get("success") else str((tc or {}).get("tool_output", ""))[:200],
                    }
                    for tc in tool_calls
                    if tc is not None
                ],
                # Full tool call records for persistence (chat route writes to tool_calls table)
                "tool_call_records": [
                    {
                        "tool_name": (tc or {}).get("tool_name", "unknown"),
                        "tool_input": (tc or {}).get("tool_input") or {},
                        "tool_output": (tc or {}).get("tool_output"),
                    }
                    for tc in tool_calls
                    if tc is not None
                ],
                # Include source summaries
                "source_summaries": [
                    {
                        "source": (s or {}).get("source", "Unknown"),
                        "confidence": (s or {}).get("confidence", 0.0),
                        "text_preview": str((s or {}).get("text", ""))[:300],
                    }
                    for s in (retrieved_sources or [])[:10]  # Limit to top 10
                    if s is not None
                ],
            }
            
            return result

        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"❌ Agent execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "response": f"I apologize, but I encountered an error: {str(e)}",
                "groundedness_score": 0.0,
                "is_reliable": False,
                "sources_used": 0,
                "error": str(e),
                "traceback": tb[:4000] if tb else None,  # Truncate for trace file
            }

    async def arun(
        self,
        query: str,
        farmer_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Async version of run."""
        return self.run(query, farmer_context, conversation_history)

    async def astream(
        self,
        query: str,
        farmer_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[list] = None,
    ):
        """
        Stream agent execution with token-by-token output.
        
        Yields:
            ("token", token_string) - Individual tokens
            ("final", result_dict) - Final result
            ("error", error_string) - Error message
        """
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _progress_cb(event_type: str, payload: Dict[str, Any]) -> None:
            asyncio.run_coroutine_threadsafe(queue.put((event_type, payload)), loop)

        class _TokenHandler(BaseCallbackHandler):
            def on_llm_new_token(self, token: str, **kwargs) -> None:
                asyncio.run_coroutine_threadsafe(queue.put(("token", token)), loop)

        def _run() -> None:
            try:
                result = self.run(
                    query=query,
                    farmer_context=farmer_context,
                    conversation_history=conversation_history,
                    callbacks=[_TokenHandler()],
                    progress_callback=_progress_cb,
                )
                asyncio.run_coroutine_threadsafe(queue.put(("final", result)), loop)
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(queue.put(("error", str(exc))), loop)

        threading.Thread(target=_run, daemon=True).start()

        while True:
            event_type, payload = await queue.get()
            yield event_type, payload
            if event_type in {"final", "error"}:
                break


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


def _extract_sources(messages: list) -> list:
    """Extract source documents from tool messages (legacy compatibility)."""
    sources = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and msg.name == "query_agricultural_knowledge":
            try:
                payload = json.loads(msg.content)
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                for item in payload.get("results", []):
                    if isinstance(item, dict) and "text" in item:
                        sources.append(item["text"])
    return sources


def _extract_tools_called(messages: list) -> list:
    """Extract tool names from messages (legacy compatibility)."""
    tools = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tools.append(msg.name)
    return tools
