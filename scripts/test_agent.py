#!/usr/bin/env python
"""
Quick test script for the Farmer RAG Agent.

Usage:
    python scripts/test_agent.py
    python scripts/test_agent.py "Your question here"
"""

import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_agent(query: str = None):
    """Test the agent with a sample query."""
    from src.agent import create_agent

    # Default test queries
    test_queries = [
        "When should I apply fertilizer to my maize?",
        "What's the weather like for planting?",
        "What are the current prices for beans?",
    ]

    if query:
        test_queries = [query]

    # Sample farmer context
    farmer_context = {
        "farmer": {
            "name": "Test Farmer",
            "region": "Kigali",
            "location": {"lat": -1.9403, "lon": 29.8739},
        },
        "farms": [
            {
                "name": "Main Farm",
                "crops": [
                    {"type": "maize", "growth_stage": "vegetative", "planting_date": "2026-01-01"},
                    {"type": "beans", "growth_stage": "flowering"},
                ],
            }
        ],
    }

    print("=" * 60)
    print("FARMER RAG AGENT TEST")
    print("=" * 60)
    print(f"\nFarmer Context:")
    print(json.dumps(farmer_context, indent=2))
    print()

    # Create agent
    agent = create_agent()

    for query in test_queries:
        print("-" * 60)
        print(f"\n📝 Query: {query}\n")

        result = agent.run(query, farmer_context=farmer_context)

        print(f"✅ Success: {result['success']}")
        print(f"📊 Groundedness Score: {result['groundedness_score']:.2f}")
        print(f"🔧 Tools Called: {result['tools_called']}")
        print(f"📚 Sources Used: {result['sources_used']}")
        print(f"\n🤖 Response:\n{result['response']}")
        print()


def test_tools():
    """Test individual tools."""
    print("=" * 60)
    print("TOOL TESTS")
    print("=" * 60)

    # Test Weather Tool
    print("\n--- Weather Tool ---")
    from src.tools.weather import WeatherTool
    weather = WeatherTool()
    result = weather.run(latitude=-1.9403, longitude=29.8739, days=3)
    print(f"Success: {result.success}")
    if result.success:
        summary = result.data.get("agricultural_summary", {})
        print(f"Total Precipitation: {summary.get('total_precipitation_mm', 0):.1f}mm")
        print(f"Recommendations: {summary.get('recommendations', [])}")

    # Test Market Tool
    print("\n--- Market Tool ---")
    from src.tools.market import MarketPriceTool
    market = MarketPriceTool()
    result = market.run(crop_type="maize")
    print(f"Success: {result.success}")
    if result.success:
        print(f"Average Price: ${result.data.get('average_price_usd', 0):.2f}/kg")
        print(f"Best Market: {result.data.get('best_market', {}).get('region', 'N/A')}")

    # Test Knowledge Tool
    print("\n--- Knowledge Tool ---")
    from src.tools.knowledge import KnowledgeBaseTool
    kb = KnowledgeBaseTool()
    result = kb.run(query="fertilizer application", crop_type="maize", top_k=2)
    print(f"Success: {result.success}")
    if result.success:
        print(f"Results Found: {len(result.data.get('results', []))}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test the Farmer RAG Agent")
    parser.add_argument("query", nargs="?", help="Query to test")
    parser.add_argument("--tools-only", action="store_true", help="Only test tools")

    args = parser.parse_args()

    if args.tools_only:
        test_tools()
    else:
        test_agent(args.query)
