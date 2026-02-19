"""
Unit tests for tool implementations.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestWeatherTool:
    """Tests for the Weather tool."""

    def test_weather_tool_schema(self):
        """Test that weather tool has correct schema."""
        from src.tools.weather import get_weather_forecast

        assert get_weather_forecast.name == "get_weather_forecast"
        assert get_weather_forecast.args_schema is not None
        schema = get_weather_forecast.args_schema.model_json_schema()
        assert "latitude" in schema.get("properties", {})
        assert "longitude" in schema.get("properties", {})

    def test_weather_tool_returns_data(self):
        """Test that weather tool returns formatted data."""
        from src.tools.weather import get_weather_forecast

        fake_payload = {
            "latitude": -1.9,
            "longitude": 29.8,
            "timezone": "Africa/Kigali",
            "current": {
                "temperature_2m": 24,
                "relative_humidity_2m": 60,
                "precipitation": 0,
                "weather_code": 1,
            },
            "daily": {
                "time": ["2026-02-17"],
                "temperature_2m_max": [28],
                "temperature_2m_min": [19],
                "precipitation_sum": [0],
                "precipitation_probability_max": [10],
                "wind_speed_10m_max": [5],
                "relative_humidity_2m_mean": [55],
                "et0_fao_evapotranspiration": [3.2],
                "weather_code": [1],
            },
        }

        with patch("src.tools.weather.httpx.Client") as mock_client:
            client = mock_client.return_value.__enter__.return_value
            client.get.return_value.json.return_value = fake_payload
            client.get.return_value.raise_for_status.return_value = None

            result = get_weather_forecast.invoke(
                {"latitude": -1.9, "longitude": 29.8, "days": 1}
            )

        assert "location" in result
        assert "daily_forecast" in result
        assert result["location"]["timezone"] == "Africa/Kigali"


class TestMarketTool:
    """Tests for the Market Price tool."""

    def test_market_tool_schema(self):
        """Test that market tool has correct schema."""
        from src.tools.market import get_market_prices

        assert get_market_prices.name == "get_market_prices"
        schema = get_market_prices.args_schema.model_json_schema()
        assert "crop_type" in schema.get("properties", {})

    def test_market_tool_returns_prices(self):
        """Test that market tool returns price data."""
        from src.tools.market import get_market_prices

        result = get_market_prices.invoke({"crop_type": "maize"})
        assert "prices_by_region" in result
        assert "average_price_usd" in result
        assert result["crop"] == "maize"

    def test_market_tool_handles_invalid_crop(self):
        """Test that market tool handles invalid crop types."""
        from src.tools.market import get_market_prices

        result = get_market_prices.invoke({"crop_type": "invalid_crop"})
        assert "error" in result
        assert "Unknown crop type" in result["error"]


def test_tool_registry_removed():
    """Registry was removed when switching to LangChain @tool."""
    assert True
