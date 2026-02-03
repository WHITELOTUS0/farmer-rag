"""
LangGraph-based agent orchestration using the prebuilt ReAct agent.
"""

import json
import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.config.settings import get_settings
from src.tools import (
    get_market_prices,
    get_weather_forecast,
    query_agricultural_knowledge,
)
from src.verification.groundedness import VerificationService

logger = logging.getLogger(__name__)


class FarmerAdvisoryAgent:
    """
    High-level interface for the farmer advisory agent.

    Provides a simple API for running queries through the agent
    with proper state management.
    """

    def __init__(self):
        """Initialize the agent with LangGraph prebuilt ReAct agent."""
        self.settings = get_settings()
        self.llm = ChatOpenAI(
            model=self.settings.primary_model,
            temperature=self.settings.model_temperature,
            api_key=self.settings.openai_api_key,
        )
        tools = [query_agricultural_knowledge, get_weather_forecast, get_market_prices]
        self.agent = create_react_agent(self.llm, tools)
        self.verifier = VerificationService()

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
        logger.info(f"Running agent for query: {query[:50]}...")

        try:
            messages = []
            if conversation_history:
                messages.extend(conversation_history)
            messages.append(HumanMessage(content=query))

            final_state = self.agent.invoke({"messages": messages})
            response_message = final_state["messages"][-1]
            response = response_message.content
            messages = final_state.get("messages", [])
            sources = _extract_sources(messages)
            tools_called = _extract_tools_called(messages)
            verification = self.verifier.verify(response, sources)

            return {
                "success": True,
                "response": response,
                "groundedness_score": verification.get("groundedness_score", 0.0),
                "is_reliable": verification.get("is_reliable", False),
                "sources_used": len(sources),
                "tools_called": tools_called,
                "verification_details": verification,
                "messages": messages,
            }

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return {
                "success": False,
                "response": f"I apologize, but I encountered an error: {str(e)}",
                "groundedness_score": 0.0,
                "is_reliable": False,
                "sources_used": 0,
                "error": str(e),
            }

    async def arun(
        self,
        query: str,
        farmer_context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[list] = None,
    ) -> Dict[str, Any]:
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


def _extract_sources(messages: list) -> list:
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
    tools = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            tools.append(msg.name)
    return tools
