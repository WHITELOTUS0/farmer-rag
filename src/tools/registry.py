"""
Tool registry for managing available tools.

Provides centralized access to all tools and their schemas
for the agent orchestrator.
"""

import logging
from typing import Dict, List, Optional, Any

from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing and accessing tools.

    Provides:
    - Tool registration and lookup
    - Schema generation for LLM function calling
    - Tool execution by name
    """

    def __init__(self):
        """Initialize an empty tool registry."""
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool with the registry.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If a tool with the same name is already registered
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")

        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def register_multiple(self, tools: List[BaseTool]) -> None:
        """
        Register multiple tools at once.

        Args:
            tools: List of tool instances to register
        """
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Optional[BaseTool]:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def execute(self, name: str, **kwargs) -> ToolResult:
        """
        Execute a tool by name.

        Args:
            name: Tool name
            **kwargs: Arguments to pass to the tool

        Returns:
            ToolResult from execution
        """
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                data=None,
                error=f"Unknown tool: {name}",
                source="registry",
            )

        logger.info(f"Executing tool: {name}")
        result = tool.run(**kwargs)
        logger.info(f"Tool {name} completed: success={result.success}")

        return result

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """
        Get OpenAI-compatible schemas for all registered tools.

        Returns:
            List of tool schemas for function calling
        """
        return [tool.get_schema() for tool in self._tools.values()]

    def get_tool_descriptions(self) -> str:
        """
        Get a formatted string describing all available tools.

        Useful for including in system prompts.

        Returns:
            Formatted tool descriptions
        """
        if not self._tools:
            return "No tools available."

        descriptions = ["Available tools:"]
        for tool in self._tools.values():
            descriptions.append(f"\n- {tool.name}: {tool.description}")

        return "\n".join(descriptions)

    def list_tools(self) -> List[str]:
        """
        Get list of registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def create_default_registry() -> ToolRegistry:
    """
    Create a registry with all default tools.

    Returns:
        ToolRegistry with standard tools registered
    """
    from src.tools.weather import WeatherTool
    from src.tools.market import MarketPriceTool
    from src.tools.knowledge import KnowledgeBaseTool

    registry = ToolRegistry()
    registry.register_multiple([
        WeatherTool(),
        MarketPriceTool(),
        KnowledgeBaseTool(),
    ])

    return registry
