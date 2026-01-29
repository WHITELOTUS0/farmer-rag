"""
Market price tool with mock data for East African crops.

Provides simulated market prices for maize, beans, and tomatoes
with realistic regional variations and seasonal patterns.
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Optional, List

from pydantic import BaseModel, Field

from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class MarketPriceArgs(BaseModel):
    """Arguments for the market price tool."""
    crop_type: str = Field(
        ...,
        description="Type of crop (maize, beans, or tomatoes)",
    )
    region: Optional[str] = Field(
        default=None,
        description="Region name (e.g., Kigali, Nairobi, Kampala). If not specified, returns all regions.",
    )
    include_trends: bool = Field(
        default=True,
        description="Whether to include price trend analysis",
    )


class MarketPriceTool(BaseTool):
    """
    Market price tool with realistic mock data.

    Provides:
    - Current prices by crop and region
    - Historical price trends
    - Price comparisons across markets
    - Harvest timing recommendations based on prices

    Note: This uses mock data for demonstration. In production,
    connect to a real market price API like EAGC or regional
    commodity exchanges.
    """

    name = "get_market_prices"
    description = (
        "Get current market prices for crops in different regions. Provides "
        "prices per kg for maize, beans, and tomatoes across East African markets. "
        "Use this when farmers ask about selling prices, best markets, or optimal "
        "harvest timing based on prices."
    )
    args_schema = MarketPriceArgs

    # Base prices in USD per kg (realistic for East Africa)
    BASE_PRICES = {
        "maize": 0.30,      # ~300 USD/ton
        "beans": 0.80,      # Higher value crop
        "tomatoes": 0.50,   # Perishable, variable
    }

    # Regional price multipliers
    REGION_MULTIPLIERS = {
        "Kigali": 1.15,      # Capital city premium
        "Nairobi": 1.20,     # Major hub
        "Kampala": 1.10,     # Uganda capital
        "Mwanza": 0.95,      # Rural Tanzania
        "Kisumu": 1.05,      # Kenya regional
        "Butare": 0.90,      # Rwanda rural
        "Mombasa": 1.25,     # Port city premium
        "Dar es Salaam": 1.18,  # Tanzania capital
    }

    # Seasonal patterns (month -> multiplier)
    SEASONAL_PATTERNS = {
        "maize": {
            1: 1.15, 2: 1.20, 3: 1.25, 4: 1.20,   # Pre-harvest high
            5: 0.90, 6: 0.85, 7: 0.85, 8: 0.90,   # Main harvest low
            9: 0.95, 10: 1.00, 11: 1.05, 12: 1.10, # Building up
        },
        "beans": {
            1: 1.10, 2: 1.15, 3: 1.15, 4: 1.10,
            5: 0.95, 6: 0.90, 7: 0.90, 8: 0.95,
            9: 1.00, 10: 1.05, 11: 1.10, 12: 1.10,
        },
        "tomatoes": {
            1: 0.90, 2: 0.85, 3: 0.90, 4: 1.00,   # Peak supply = low price
            5: 1.10, 6: 1.20, 7: 1.25, 8: 1.20,   # Dry season = high price
            9: 1.10, 10: 1.00, 11: 0.95, 12: 0.90,
        },
    }

    def _execute(
        self,
        crop_type: str,
        region: Optional[str] = None,
        include_trends: bool = True,
    ) -> ToolResult:
        """
        Get market prices for a crop.

        Args:
            crop_type: Type of crop
            region: Optional region filter
            include_trends: Whether to include trend analysis

        Returns:
            ToolResult with price data
        """
        crop_type = crop_type.lower().strip()

        # Validate crop type
        if crop_type not in self.BASE_PRICES:
            return ToolResult(
                success=False,
                data=None,
                error=f"Unknown crop type: {crop_type}. Supported: maize, beans, tomatoes",
                source="Market Price Database",
            )

        try:
            # Get current month for seasonal adjustment
            current_month = datetime.now().month

            # Calculate prices for all or specified regions
            regions_to_check = (
                [region] if region and region in self.REGION_MULTIPLIERS
                else list(self.REGION_MULTIPLIERS.keys())
            )

            prices = []
            for reg in regions_to_check:
                price = self._calculate_price(crop_type, reg, current_month)
                prices.append({
                    "region": reg,
                    "price_usd_per_kg": round(price, 2),
                    "price_local_estimate": self._estimate_local_currency(price, reg),
                })

            # Sort by price descending
            prices.sort(key=lambda x: x["price_usd_per_kg"], reverse=True)

            result = {
                "crop": crop_type,
                "query_date": datetime.now().isoformat(),
                "prices_by_region": prices,
                "best_market": prices[0] if prices else None,
                "average_price_usd": round(
                    sum(p["price_usd_per_kg"] for p in prices) / len(prices), 2
                ) if prices else 0,
            }

            # Add trend analysis if requested
            if include_trends:
                result["trends"] = self._calculate_trends(crop_type, current_month)
                result["recommendations"] = self._generate_recommendations(
                    crop_type, prices, result["trends"]
                )

            return ToolResult(
                success=True,
                data=result,
                source="Market Price Database (Mock)",
                metadata={
                    "data_source": "simulated",
                    "regions_queried": len(regions_to_check),
                },
            )

        except Exception as e:
            logger.error(f"Market price tool error: {e}")
            return ToolResult(
                success=False,
                data=None,
                error=f"Failed to get market prices: {str(e)}",
                source="Market Price Database",
            )

    def _calculate_price(
        self,
        crop_type: str,
        region: str,
        month: int,
    ) -> float:
        """
        Calculate price for a crop in a region.

        Args:
            crop_type: Type of crop
            region: Region name
            month: Current month (1-12)

        Returns:
            Price in USD per kg
        """
        base = self.BASE_PRICES[crop_type]
        regional = self.REGION_MULTIPLIERS.get(region, 1.0)
        seasonal = self.SEASONAL_PATTERNS[crop_type].get(month, 1.0)

        # Add some random variation (±5%)
        variation = random.uniform(0.95, 1.05)

        return base * regional * seasonal * variation

    def _estimate_local_currency(self, usd_price: float, region: str) -> dict:
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
        return {
            "currency": currency,
            "amount": round(usd_price * rate, 0),
        }

    def _calculate_trends(self, crop_type: str, current_month: int) -> dict:
        """
        Calculate price trends and predictions.

        Args:
            crop_type: Type of crop
            current_month: Current month

        Returns:
            Trend analysis
        """
        seasonal = self.SEASONAL_PATTERNS[crop_type]
        current_factor = seasonal[current_month]

        # Next month prediction
        next_month = (current_month % 12) + 1
        next_factor = seasonal[next_month]

        # Three month prediction
        future_month = ((current_month + 2) % 12) + 1
        future_factor = seasonal[future_month]

        trend = {
            "current_season_factor": current_factor,
            "next_month_prediction": "increasing" if next_factor > current_factor else "decreasing" if next_factor < current_factor else "stable",
            "three_month_outlook": "increasing" if future_factor > current_factor else "decreasing" if future_factor < current_factor else "stable",
            "price_change_percent_next_month": round((next_factor - current_factor) / current_factor * 100, 1),
            "is_harvest_season": current_factor < 0.95,
            "is_peak_price_season": current_factor > 1.10,
        }

        return trend

    def _generate_recommendations(
        self,
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

        # Best market recommendation
        if prices:
            best = prices[0]
            worst = prices[-1]
            price_diff = ((best["price_usd_per_kg"] - worst["price_usd_per_kg"])
                         / worst["price_usd_per_kg"] * 100)
            if price_diff > 15:
                recommendations.append(
                    f"Consider selling in {best['region']} - prices are "
                    f"{price_diff:.0f}% higher than {worst['region']}"
                )

        # Timing recommendations
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
