"""
Weather tool using Open-Meteo API (LangChain @tool).
"""

import logging
from typing import List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

API_URL = "https://api.open-meteo.com/v1/forecast"


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError)),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
)
def _fetch_weather(params: dict) -> dict:
    with httpx.Client(timeout=30) as client:
        response = client.get(API_URL, params=params)
        response.raise_for_status()
        return response.json()


@tool("get_weather_forecast")
def get_weather_forecast(latitude: float, longitude: float, days: int = 7) -> dict:
    """
    Get weather forecast for a location.

    Returns precipitation probability, temperature, humidity, and
    agricultural metrics from Open-Meteo.
    """
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
            "et0_fao_evapotranspiration",
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

    try:
        data = _fetch_weather(params)
    except Exception as e:
        logger.error("Weather API request failed: %s", e)
        return {"error": f"Weather API request failed: {str(e)}"}

    return _format_response(data)


def _get_weather_description(code: Optional[int]) -> str:
    if code is None:
        return "Unknown"

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


def _generate_agricultural_summary(daily_forecast: List[dict]) -> dict:
    if not daily_forecast:
        return {}

    total_precip = sum(d["precipitation_mm"] or 0 for d in daily_forecast)
    avg_temp = sum(
        (d["temperature_max_c"] or 0) + (d["temperature_min_c"] or 0)
        for d in daily_forecast
    ) / (len(daily_forecast) * 2)
    max_rain_prob = max(d["precipitation_probability"] or 0 for d in daily_forecast)
    rainy_days = sum(1 for d in daily_forecast if (d["precipitation_mm"] or 0) > 5)
    total_et = sum(d["evapotranspiration_mm"] or 0 for d in daily_forecast)
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


def _format_response(data: dict) -> dict:
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

    current = data.get("current", {})
    if current:
        result["current_conditions"] = {
            "temperature_c": current.get("temperature_2m"),
            "humidity_percent": current.get("relative_humidity_2m"),
            "precipitation_mm": current.get("precipitation"),
            "conditions": _get_weather_description(current.get("weather_code")),
        }

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
                "humidity_percent": daily.get("relative_humidity_2m_mean", [None])[i],
                "wind_speed_kmh": daily.get("wind_speed_10m_max", [None])[i],
                "evapotranspiration_mm": daily.get(
                    "et0_fao_evapotranspiration", [None]
                )[i],
                "conditions": _get_weather_description(
                    daily.get("weather_code", [None])[i]
                ),
            }
            result["daily_forecast"].append(day_data)

    result["agricultural_summary"] = _generate_agricultural_summary(
        result["daily_forecast"]
    )

    return result
