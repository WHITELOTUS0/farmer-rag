#!/usr/bin/env python
"""
Generate an implementation trace (LangSmith + local log output).

Usage:
    python scripts/run_trace.py
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# Add project root to path
project_root = Path(__file__).parent.parent
import sys

sys.path.insert(0, str(project_root))


def _sanitize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Convert non-JSON-serializable message objects into dicts."""
    sanitized = dict(result)
    messages = sanitized.get("messages", [])
    safe_messages = []
    for msg in messages:
        if hasattr(msg, "type") and hasattr(msg, "content"):
            safe_messages.append({"role": getattr(msg, "type"), "content": msg.content})
        elif isinstance(msg, dict):
            safe_messages.append(msg)
        else:
            safe_messages.append({"role": "unknown", "content": str(msg)})
    sanitized["messages"] = safe_messages
    return sanitized


def main() -> None:
    from src.config.settings import get_settings
    from src.agent import create_agent

    # Disable LangSmith tracing for trace generation (payloads too large - exceeds 26MB limit)
    # We'll save a local trace file instead which is sufficient for HW3
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    
    print("=" * 80)
    print("GENERATING EXECUTION TRACE")
    print("=" * 80)
    print("Note: LangSmith tracing disabled to avoid payload size limits")
    print("Trace will be saved locally to logs/ directory")
    print()

    agent = create_agent()

    query = (
        "I am a maize farmer in Kigali. Please: "
        "1) fetch the weather forecast for my location, "
        "2) fetch current market prices for maize in the region, and "
        "3) use the knowledge base to give best-practice advice for planting. "
        "Cite sources and be specific."
    )

    print(f"Running agent query: {query[:60]}...")
    print("This may take 30-60 seconds...")
    print()

    # General context: no specific farmer/farms required. Query provides crop + region.
    farmer_context = {
        "farmer": {
            "name": "Trace User",
            "region": "Kigali",
            "location": {"lat": -1.9441, "lon": 30.0619},
        },
    }

    result = agent.run(
        query=query,
        farmer_context=farmer_context,
    )

    # Add execution metadata (defensive: handle None farmer/farms/crops)
    _farmer = (farmer_context or {}).get("farmer") or {}
    _farms = (farmer_context or {}).get("farms") or []
    trace_data = {
        "query": query,
        "farmer_context": {
            "farmer": _farmer.get("name", "Unknown") if isinstance(_farmer, dict) else str(_farmer),
            "region": _farmer.get("region", "Unknown") if isinstance(_farmer, dict) else "Unknown",
            "crops": [
                (c or {}).get("type", "unknown")
                for f in _farms
                for c in ((f or {}).get("crops") or [])
                if c is not None
            ],
        },
        "execution_result": result,
        "trace_metadata": {
            "generated_at": datetime.now().isoformat(),
            "purpose": "Homework 3 - Execution Trace",
            "shows": [
                "Multi-step reasoning (Observe → Reason → Decide → Act → Evaluate → Update)",
                "Tool calls and results",
                "Verification and groundedness scoring",
                "Adaptive control (re-retrieval, tool retries)",
            ],
        },
    }
    
    # Truncate large fields for trace file (keep it readable)
    sanitized = _sanitize_result(trace_data)
    
    # Truncate very long messages/content to keep file size manageable
    if "execution_result" in sanitized and "messages" in sanitized["execution_result"]:
        for msg in sanitized["execution_result"]["messages"]:
            if isinstance(msg, dict) and "content" in msg:
                content = msg["content"]
                if isinstance(content, str) and len(content) > 5000:
                    msg["content"] = content[:5000] + f"\n... [truncated {len(content) - 5000} chars]"
    
    # Truncate response if too long
    if "execution_result" in sanitized and "response" in sanitized["execution_result"]:
        response = sanitized["execution_result"]["response"]
        if isinstance(response, str) and len(response) > 10000:
            sanitized["execution_result"]["response"] = response[:10000] + f"\n... [truncated {len(response) - 10000} chars]"

    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    trace_file = logs_dir / f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    trace_file.write_text(json.dumps(sanitized, indent=2))
    
    print("=" * 80)
    print("TRACE GENERATION COMPLETE")
    print("=" * 80)
    print(f"✅ Trace saved to: {trace_file}")
    print(f"   Response length: {len(result.get('response', ''))} chars")
    print(f"   Groundedness: {result.get('groundedness_score', 0.0):.2f}")
    print(f"   Tools called: {', '.join(result.get('tools_called', []))}")
    print(f"   Sources used: {result.get('sources_used', 0)}")
    print(f"   Iterations: {result.get('iteration_count', 0)}")
    print()
    print("This trace file shows:")
    print("  - Multi-step reasoning (Observe → Reason → Decide → Act)")
    print("  - Tool calls and results")
    print("  - Verification and groundedness scoring")
    print("  - Adaptive control (if triggered)")


if __name__ == "__main__":
    main()
