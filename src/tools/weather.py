"""
Weather tool using Open-Meteo API.

Provides real-time and forecast weather data for agricultural
decision-making, completely free and without API key.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List

import httpx
from pydantic import BaseModel, Field

from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class WeatherToolArgs(BaseModel):
    """Arguments for the weather tool."""
    latitude: float = Field(
        ...,
        description="Latitude of the location (-90 to 90)",
        ge=-90,
        le=90,
    )
    longitude: float = Field(
        ...,
        description="Longitude of the location (-180 to 180)",
        ge=-180,
        le=180,
    )
    days: int = Field(
        default=7,
        description="Number of forecast days (1-16)",
        ge=1,
        le=16,
    )


class WeatherTool(BaseTool):
    """
    Weather forecast tool using Open-Meteo API.

    Provides:
    - Current weather conditions
    - Daily forecasts (precipitation, temperature, humidity)
    - Agricultural-relevant metrics (soil moisture, evapotranspiration)

    Open-Meteo is completely free, no API key required, and has
    excellent coverage for Africa.
    """

    name = "get_weather_forecast"
    description = (
        "Get weather forecast for a location. Provides precipitation probability, "
        "temperature, humidity, and other agricultural metrics. Use this when the "
        "farmer asks about weather, planting conditions, irrigation needs, or when "
        "weather affects agricultural decisions like spraying or fertilizing."
    )
    args_schema = WeatherToolArgs

    # Open-Meteo API endpoint
    API_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, timeout: int = 30):
        """
        Initialize the weather tool.

        Args:
            timeout: API request timeout in seconds
        """
        super().__init__()
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def _execute(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ) -> ToolResult:
        """
        Fetch weather forecast from Open-Meteo.

        Args:
            latitude: Location latitude
            longitude: Location longitude
            days: Number of forecast days

        Returns:
            ToolResult with weather data
        """
        try:
            # Build API request
            params = {
                "latitude": latitude,
                "longitude": longitude,
                "daily": [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "precipitation_sum",
                    "precipitation_probability_max",
                    "wind_speed_10m_max",
                    "relative_humidity_2m_mean",
                    "et0_fao_evapotranspiration",  # Agricultural evapotranspiration
                ],
                "current": [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "precipitation",
                    "weather_code",
                ],
                "timezone": "auto",
                "forecast_days": days,
            }

            # Make API request
            response = self.client.get(self.API_URL, params=params)
            response.raise_for_status()
            data = response.json()

            # Parse and format the response
            formatted_data = self._format_response(data)

            return ToolResult(
                success=True,
                data=formatted_data,
                source="Open-Meteo API",
                metadata={
                    "latitude": latitude,
                    "longitude": longitude,
                    "forecast_days": days,
                    "timezone": data.get("timezone", "unknown"),
                },
            )

        except httpx.HTTPError as e:
            logger.error(f"Weather API request failed: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=f"Weather API request failed: {str(e)}",
                source="Open-Meteo API",
            )
        except Exception as e:
            logger.error(f"Weather tool error: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=f"Weather tool error: {str(e)}",
                source="Open-Meteo API",
            )

    def _format_response(self, data: dict) -> dict:
        """
        Format API response for agent consumption.

        Args:
            data: Raw API response

        Returns:
            Formatted weather data with agricultural context
        """
        result = {
            "location": {
                "latitude": data.get("latitude"),
                "longitude": data.get("longitude"),
                "timezone": data.get("timezone"),
            },
            "current_conditions": None,
            "daily_forecast": [],
            "agricultural_summary": {},
        }

        # Current conditions
        current = data.get("current", {})
        if current:
            result["current_conditions"] = {
                "temperature_c": current.get("temperature_2m"),
                "humidity_percent": current.get("relative_humidity_2m"),
                "precipitation_mm": current.get("precipitation"),
                "conditions": self._get_weather_description(
                    current.get("weather_code")
                ),
            }

        # Daily forecast
        daily = data.get("daily", {})
        if daily and "time" in daily:
            for i, date in enumerate(daily["time"]):
                day_data = {
                    "date": date,
                    "temperature_max_c": daily.get("temperature_2m_max", [None])[i],
                    "temperature_min_c": daily.get("temperature_2m_min", [None])[i],
                    "precipitation_mm": daily.get("precipitation_sum", [None])[i],
                    "precipitation_probability": daily.get(
                        "precipitation_probability_max", [None]
                    )[i],
                    "humidity_percent": daily.get(
                        "relative_humidity_2m_mean", [None]
                    )[i],
                    "wind_speed_kmh": daily.get("wind_speed_10m_max", [None])[i],
                    "evapotranspiration_mm": daily.get(
                        "et0_fao_evapotranspiration", [None]
                    )[i],
                    "conditions": self._get_weather_description(
                        daily.get("weather_code", [None])[i]
                    ),
                }
                result["daily_forecast"].append(day_data)

        # Agricultural summary
        result["agricultural_summary"] = self._generate_agricultural_summary(
            result["daily_forecast"]
        )

        return result

    def _get_weather_description(self, code: Optional[int]) -> str:
        """
        Convert WMO weather code to description.

        Args:
            code: WMO weather code

        Returns:
            Human-readable weather description
        """
        if code is None:
            return "Unknown"

        # WMO Weather interpretation codes
        descriptions = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail",
        }

        return descriptions.get(code, f"Weather code {code}")

    def _generate_agricultural_summary(
        self,
        daily_forecast: List[dict],
    ) -> dict:
        """
        Generate agricultural-relevant summary from forecast.

        Args:
            daily_forecast: List of daily forecast data

        Returns:
            Agricultural summary with recommendations
        """
        if not daily_forecast:
            return {}

        # Calculate aggregates
        total_precip = sum(
            d["precipitation_mm"] or 0 for d in daily_forecast
        )
        avg_temp = sum(
            (d["temperature_max_c"] or 0) + (d["temperature_min_c"] or 0)
            for d in daily_forecast
        ) / (len(daily_forecast) * 2)

        max_rain_prob = max(
            d["precipitation_probability"] or 0 for d in daily_forecast
        )

        # Days with significant rain (>5mm)
        rainy_days = sum(
            1 for d in daily_forecast if (d["precipitation_mm"] or 0) > 5
        )

        # Total evapotranspiration
        total_et = sum(
            d["evapotranspiration_mm"] or 0 for d in daily_forecast
        )

        # Water balance (simplified)
        water_balance = total_precip - total_et

        summary = {
            "total_precipitation_mm": round(total_precip, 1),
            "average_temperature_c": round(avg_temp, 1),
            "max_rain_probability_percent": max_rain_prob,
            "rainy_days_count": rainy_days,
            "total_evapotranspiration_mm": round(total_et, 1),
            "water_balance_mm": round(water_balance, 1),
            "recommendations": [],
        }

        # Generate recommendations
        if max_rain_prob > 70:
            summary["recommendations"].append(
                "High rain probability - delay fertilizer application to prevent runoff"
            )
        if max_rain_prob > 50 and rainy_days >= 2:
            summary["recommendations"].append(
                "Multiple rainy days expected - good conditions for planting"
            )
        if water_balance < -20:
            summary["recommendations"].append(
                "Negative water balance - consider irrigation if available"
            )
        if avg_temp > 30:
            summary["recommendations"].append(
                "High temperatures - ensure adequate water for crops"
            )
        if max_rain_prob < 20 and total_precip < 5:
            summary["recommendations"].append(
                "Dry conditions expected - suitable for spraying pesticides"
            )

        return summary

    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, 'client'):
            self.client.close()
