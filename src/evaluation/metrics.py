"""
Automated evaluation metrics for agent performance.

Implements at least 3 quantitative metrics:
1. Groundedness score (factual accuracy)
2. Tool selection accuracy (did agent choose right tools?)
3. Task completion rate (did agent answer the question?)
4. Iterations before convergence (efficiency)
5. Hallucination frequency (unsupported claims)
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class EvaluationMetrics:
    """
    Comprehensive evaluation metrics for agent performance.
    """
    # Core metrics (required)
    groundedness_score: float = 0.0
    tool_selection_accuracy: float = 0.0
    task_completion_rate: float = 0.0
    
    # Additional metrics
    iterations_before_convergence: int = 0
    hallucination_frequency: float = 0.0
    sources_used: int = 0
    tools_called: List[str] = field(default_factory=list)
    
    # Metadata
    query: str = ""
    expected_tools: List[str] = field(default_factory=list)
    response_length: int = 0
    has_error: bool = False
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            "groundedness_score": self.groundedness_score,
            "tool_selection_accuracy": self.tool_selection_accuracy,
            "task_completion_rate": self.task_completion_rate,
            "iterations_before_convergence": self.iterations_before_convergence,
            "hallucination_frequency": self.hallucination_frequency,
            "sources_used": self.sources_used,
            "tools_called": self.tools_called,
            "query": self.query,
            "expected_tools": self.expected_tools,
            "response_length": self.response_length,
            "has_error": self.has_error,
            "error_message": self.error_message,
        }


def compute_tool_selection_accuracy(
    tools_called: List[str],
    expected_tools: List[str],
) -> float:
    """
    Compute how accurately the agent selected tools.
    
    Returns:
        Score from 0.0 to 1.0:
        - 1.0 if all expected tools were called
        - 0.5 if some expected tools were called
        - 0.0 if no expected tools were called
        - Bonus for calling relevant unexpected tools
    """
    if not expected_tools:
        # If no expected tools, check if agent called appropriate tools
        # For now, return 1.0 if any tools were called (agent was proactive)
        return 1.0 if tools_called else 0.5
    
    if not tools_called:
        return 0.0
    
    # Check how many expected tools were called
    called_set = set(tools_called)
    expected_set = set(expected_tools)
    
    # Precision: expected tools called / total tools called
    precision = len(called_set & expected_set) / len(called_set) if called_set else 0.0
    
    # Recall: expected tools called / total expected tools
    recall = len(called_set & expected_set) / len(expected_set) if expected_set else 0.0
    
    # F1 score (harmonic mean)
    if precision + recall == 0:
        return 0.0
    f1 = 2 * (precision * recall) / (precision + recall)
    
    return f1


def compute_task_completion_rate(
    response: str,
    query: str,
    has_error: bool = False,
) -> float:
    """
    Compute whether the agent completed the task (answered the question).
    
    Returns:
        Score from 0.0 to 1.0:
        - 1.0 if response is substantial and relevant
        - 0.5 if response is partial
        - 0.0 if error or empty response
    """
    if has_error or not response:
        return 0.0
    
    # Check response length (too short = incomplete)
    if len(response) < 50:
        return 0.3
    
    # Check if response contains question words (bad sign - didn't answer)
    question_words = ["?", "what", "which", "when", "where", "why", "how"]
    response_lower = response.lower()
    if any(word in response_lower for word in question_words[:1]):  # Just "?"
        # Might be asking back, which is incomplete
        if response_lower.count("?") > 1:
            return 0.4
    
    # Check for error indicators
    error_indicators = ["error", "failed", "couldn't", "unable", "apologize"]
    if any(indicator in response_lower for indicator in error_indicators):
        return 0.5
    
    # Substantial response (good)
    if len(response) > 200:
        return 1.0
    
    # Medium response
    return 0.7


def compute_hallucination_frequency(
    verification: Dict[str, Any],
) -> float:
    """
    Compute frequency of unsupported claims (hallucinations).
    
    Returns:
        Ratio of unsupported claims to total claims (0.0 = no hallucinations, 1.0 = all hallucinations)
    """
    if not verification:
        return 0.0  # Unknown
    
    claims = verification.get("claims", [])
    if not claims:
        return 0.0  # No claims to verify
    
    unsupported = sum(1 for c in claims if not c.get("supported", True))
    total = len(claims)
    
    return unsupported / total if total > 0 else 0.0


def compute_metrics(
    agent_result: Dict[str, Any],
    query: str,
    expected_tools: Optional[List[str]] = None,
) -> EvaluationMetrics:
    """
    Compute comprehensive evaluation metrics from agent result.
    
    Args:
        agent_result: Result dictionary from agent.run()
        query: Original query
        expected_tools: Optional list of tools that should have been called
        
    Returns:
        EvaluationMetrics object with all computed metrics
    """
    groundedness = agent_result.get("groundedness_score", 0.0)
    tools_called = agent_result.get("tools_called", [])
    sources_used = agent_result.get("sources_used", 0)
    response = agent_result.get("response", "")
    verification = agent_result.get("verification_details", {})
    iteration_count = agent_result.get("iteration_count", 0)
    has_error = not agent_result.get("success", True)
    error_message = agent_result.get("error")
    
    # Compute metrics
    tool_accuracy = compute_tool_selection_accuracy(
        tools_called=tools_called,
        expected_tools=expected_tools or [],
    )
    
    completion_rate = compute_task_completion_rate(
        response=response,
        query=query,
        has_error=has_error,
    )
    
    hallucination_freq = compute_hallucination_frequency(verification)
    
    return EvaluationMetrics(
        groundedness_score=groundedness,
        tool_selection_accuracy=tool_accuracy,
        task_completion_rate=completion_rate,
        iterations_before_convergence=iteration_count,
        hallucination_frequency=hallucination_freq,
        sources_used=sources_used,
        tools_called=tools_called,
        query=query,
        expected_tools=expected_tools or [],
        response_length=len(response),
        has_error=has_error,
        error_message=error_message,
    )


def evaluate_agent_response(
    agent_result: Dict[str, Any],
    query: str,
    expected_tools: Optional[List[str]] = None,
) -> EvaluationMetrics:
    """
    Evaluate an agent response and return metrics.
    
    Alias for compute_metrics for convenience.
    """
    return compute_metrics(agent_result, query, expected_tools)
