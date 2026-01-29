"""
Base classes for tool implementations.

Defines the interface for all tools that the agent can use,
with standardized input/output schemas and error handling.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Type
from pydantic import BaseModel


@dataclass
class ToolResult:
    """
    Standardized result from tool execution.

    Attributes:
        success: Whether the tool execution succeeded
        data: The output data from the tool
        error: Error message if execution failed
        source: Identifier of the data source
        metadata: Additional execution metadata
    """
    success: bool
    data: Any
    error: Optional[str] = None
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "source": self.source,
            "metadata": self.metadata,
        }

    def to_string(self) -> str:
        """Convert result to string for LLM context."""
        if self.success:
            if isinstance(self.data, dict):
                import json
                return json.dumps(self.data, indent=2, default=str)
            return str(self.data)
        else:
            return f"Error: {self.error}"


class BaseTool(ABC):
    """
    Abstract base class for all tools.

    Each tool must define:
    - name: Unique identifier for the tool
    - description: What the tool does (for agent understanding)
    - args_schema: Pydantic model defining expected inputs
    - _execute: The actual tool logic
    """

    name: str = "base_tool"
    description: str = "Base tool description"
    args_schema: Type[BaseModel] = BaseModel

    def __init__(self):
        """Initialize the tool."""
        pass

    @abstractmethod
    def _execute(self, **kwargs) -> ToolResult:
        """
        Execute the tool with the given arguments.

        Args:
            **kwargs: Tool-specific arguments

        Returns:
            ToolResult with execution outcome
        """
        pass

    def run(self, **kwargs) -> ToolResult:
        """
        Run the tool with validation and error handling.

        Args:
            **kwargs: Tool arguments

        Returns:
            ToolResult with execution outcome
        """
        try:
            # Validate arguments using Pydantic schema
            validated_args = self.args_schema(**kwargs)
            # Execute with validated arguments
            return self._execute(**validated_args.model_dump())
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error=f"Tool execution failed: {str(e)}",
                source=self.name,
            )

    def get_schema(self) -> Dict[str, Any]:
        """
        Get the OpenAI-compatible tool schema.

        Returns:
            Dictionary with tool definition for function calling
        """
        # Get Pydantic schema
        schema = self.args_schema.model_json_schema()

        # Remove title and description from nested properties
        if "properties" in schema:
            for prop in schema["properties"].values():
                prop.pop("title", None)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                },
            },
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}')>"
