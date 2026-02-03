"""
Market price tool with mock data for East African crops (LangChain @tool).
"""

import logging
import random
from datetime import datetime
from typing import List, Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

BASE_PRICES = {
    "maize": 0.30,
    "beans": 0.80,
    "tomatoes": 0.50,
}

REGION_MULTIPLIERS = {
    "Kigali": 1.15,
    "Nairobi": 1.20,
    "Kampala": 1.10,
    "Mwanza": 0.95,
    "Kisumu": 1.05,
    "Butare": 0.90,
    "Mombasa": 1.25,
    "Dar es Salaam": 1.18,
}

SEASONAL_PATTERNS = {
    "maize": {
        1: 1.15, 2: 1.20, 3: 1.25, 4: 1.20,
        5: 0.90, 6: 0.85, 7: 0.85, 8: 0.90,
        9: 0.95, 10: 1.00, 11: 1.05, 12: 1.10,
    },
    "beans": {
        1: 1.10, 2: 1.15, 3: 1.15, 4: 1.10,
        5: 0.95, 6: 0.90, 7: 0.90, 8: 0.95,
        9: 1.00, 10: 1.05, 11: 1.10, 12: 1.10,
    },
    "tomatoes": {
        1: 0.90, 2: 0.85, 3: 0.90, 4: 1.00,
        5: 1.10, 6: 1.20, 7: 1.25, 8: 1.20,
        9: 1.10, 10: 1.00, 11: 0.95, 12: 0.90,
    },
}


@tool("get_market_prices")
def get_market_prices(
    crop_type: str,
    region: Optional[str] = None,
    include_trends: bool = True,
) -> dict:
    """
    Get current market prices for crops in East African regions.
    """
    crop_type = crop_type.lower().strip()
    if crop_type not in BASE_PRICES:
        return {"error": f"Unknown crop type: {crop_type}. Supported: maize, beans, tomatoes"}

    current_month = datetime.now().month
    regions_to_check = (
        [region] if region and region in REGION_MULTIPLIERS else list(REGION_MULTIPLIERS.keys())
    )

    prices = []
    for reg in regions_to_check:
        price = _calculate_price(crop_type, reg, current_month)
        prices.append(
            {
                "region": reg,
                "price_usd_per_kg": round(price, 2),
                "price_local_estimate": _estimate_local_currency(price, reg),
            }
        )

    prices.sort(key=lambda x: x["price_usd_per_kg"], reverse=True)

    result = {
        "crop": crop_type,
        "query_date": datetime.now().isoformat(),
        "prices_by_region": prices,
        "best_market": prices[0] if prices else None,
        "average_price_usd": round(
            sum(p["price_usd_per_kg"] for p in prices) / len(prices), 2
        )
        if prices
        else 0,
    }

    if include_trends:
        trends = _calculate_trends(crop_type, current_month)
        result["trends"] = trends
        result["recommendations"] = _generate_recommendations(crop_type, prices, trends)

    return result

def _calculate_price(crop_type: str, region: str, month: int) -> float:
    """
    Calculate price for a crop in a region.

    Args:
        crop_type: Type of crop
        region: Region name
        month: Current month (1-12)

    Returns:
        Price in USD per kg
    """
    base = BASE_PRICES[crop_type]
    regional = REGION_MULTIPLIERS.get(region, 1.0)
    seasonal = SEASONAL_PATTERNS[crop_type].get(month, 1.0)
    variation = random.uniform(0.95, 1.05)
    return base * regional * seasonal * variation

def _estimate_local_currency(usd_price: float, region: str) -> dict:
    """
    Estimate local currency price.

    Args:
        usd_price: Price in USD
        region: Region name

    Returns:
        Local currency estimate
    """
    # Approximate exchange rates
    currencies = {
        "Kigali": ("RWF", 1250),
        "Butare": ("RWF", 1250),
        "Nairobi": ("KES", 155),
        "Kisumu": ("KES", 155),
        "Mombasa": ("KES", 155),
        "Kampala": ("UGX", 3800),
        "Mwanza": ("TZS", 2500),
        "Dar es Salaam": ("TZS", 2500),
    }
    currency, rate = currencies.get(region, ("USD", 1))
    return {"currency": currency, "amount": round(usd_price * rate, 0)}

def _calculate_trends(crop_type: str, current_month: int) -> dict:
    """
    Calculate price trends and predictions.

    Args:
        crop_type: Type of crop
        current_month: Current month

    Returns:
        Trend analysis
    """
    seasonal = SEASONAL_PATTERNS[crop_type]
    current_factor = seasonal[current_month]

    # Next month prediction
    next_month = (current_month % 12) + 1
    next_factor = seasonal[next_month]

    # Three month prediction
    future_month = ((current_month + 2) % 12) + 1
    future_factor = seasonal[future_month]

    trend = {
        "current_season_factor": current_factor,
        "next_month_prediction": "increasing"
        if next_factor > current_factor
        else "decreasing"
        if next_factor < current_factor
        else "stable",
        "three_month_outlook": "increasing"
        if future_factor > current_factor
        else "decreasing"
        if future_factor < current_factor
        else "stable",
        "price_change_percent_next_month": round(
            (next_factor - current_factor) / current_factor * 100, 1
        ),
        "is_harvest_season": current_factor < 0.95,
        "is_peak_price_season": current_factor > 1.10,
    }

    return trend

def _generate_recommendations(
    crop_type: str,
    prices: List[dict],
    trends: dict,
) -> List[str]:
    """
    Generate market-based recommendations.

    Args:
        crop_type: Type of crop
        prices: Price data by region
        trends: Trend analysis

    Returns:
        List of recommendations
    """
    recommendations = []

    if prices:
        best = prices[0]
        worst = prices[-1]
        price_diff = (
            (best["price_usd_per_kg"] - worst["price_usd_per_kg"])
            / worst["price_usd_per_kg"]
            * 100
        )
        if price_diff > 15:
            recommendations.append(
                f"Consider selling in {best['region']} - prices are "
                f"{price_diff:.0f}% higher than {worst['region']}"
            )

    if trends["is_harvest_season"]:
        recommendations.append(
            f"Currently harvest season with lower prices. "
            f"If possible, consider storing {crop_type} for better prices later."
        )
    elif trends["is_peak_price_season"]:
        recommendations.append(
            f"Currently peak price season - good time to sell {crop_type}."
        )

    if trends["price_change_percent_next_month"] > 5:
        recommendations.append(
            f"Prices expected to increase by ~{trends['price_change_percent_next_month']:.0f}% "
            f"next month. Consider waiting to sell if storage is available."
        )
    elif trends["price_change_percent_next_month"] < -5:
        recommendations.append(
            f"Prices expected to decrease by ~{abs(trends['price_change_percent_next_month']):.0f}% "
            f"next month. Consider selling soon."
        )

    return recommendations
