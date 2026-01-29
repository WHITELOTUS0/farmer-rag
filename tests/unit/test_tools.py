"""
Unit tests for tool implementations.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestWeatherTool:
    """Tests for the Weather tool."""

    def test_weather_tool_schema(self):
        """Test that weather tool has correct schema."""
        from src.tools.weather import WeatherTool

        tool = WeatherTool()
        schema = tool.get_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "get_weather_forecast"
        assert "latitude" in schema["function"]["parameters"]["properties"]
        assert "longitude" in schema["function"]["parameters"]["properties"]

    def test_weather_tool_validates_coordinates(self):
        """Test that weather tool validates coordinate ranges."""
        from src.tools.weather import WeatherToolArgs
        from pydantic import ValidationError

        # Valid coordinates
        args = WeatherToolArgs(latitude=-1.9403, longitude=29.8739)
        assert args.latitude == -1.9403

        # Invalid latitude
        with pytest.raises(ValidationError):
            WeatherToolArgs(latitude=100, longitude=29.8739)


class TestMarketTool:
    """Tests for the Market Price tool."""

    def test_market_tool_schema(self):
        """Test that market tool has correct schema."""
        from src.tools.market import MarketPriceTool

        tool = MarketPriceTool()
        schema = tool.get_schema()

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "get_market_prices"
        assert "crop_type" in schema["function"]["parameters"]["properties"]

    def test_market_tool_returns_prices(self):
        """Test that market tool returns price data."""
        from src.tools.market import MarketPriceTool

        tool = MarketPriceTool()
        result = tool.run(crop_type="maize")

        assert result.success
        assert "prices_by_region" in result.data
        assert "average_price_usd" in result.data
        assert result.data["crop"] == "maize"

    def test_market_tool_handles_invalid_crop(self):
        """Test that market tool handles invalid crop types."""
        from src.tools.market import MarketPriceTool

        tool = MarketPriceTool()
        result = tool.run(crop_type="invalid_crop")

        assert not result.success
        assert "Unknown crop type" in result.error


class TestToolRegistry:
    """Tests for the tool registry."""

    def test_registry_registers_tools(self):
        """Test that registry can register tools."""
        from src.tools.registry import ToolRegistry
        from src.tools.weather import WeatherTool

        registry = ToolRegistry()
        tool = WeatherTool()
        registry.register(tool)

        assert "get_weather_forecast" in registry
        assert registry.get("get_weather_forecast") is tool

    def test_registry_prevents_duplicate_registration(self):
        """Test that registry prevents duplicate tool names."""
        from src.tools.registry import ToolRegistry
        from src.tools.weather import WeatherTool

        registry = ToolRegistry()
        tool1 = WeatherTool()
        tool2 = WeatherTool()

        registry.register(tool1)
        with pytest.raises(ValueError):
            registry.register(tool2)

    def test_registry_executes_tools(self):
        """Test that registry can execute tools by name."""
        from src.tools.registry import ToolRegistry
        from src.tools.market import MarketPriceTool

        registry = ToolRegistry()
        registry.register(MarketPriceTool())

        result = registry.execute("get_market_prices", crop_type="beans")
        assert result.success
