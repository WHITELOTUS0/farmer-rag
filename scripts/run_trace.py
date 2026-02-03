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

    settings = get_settings()
    if settings.langchain_tracing_v2 and settings.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint

    agent = create_agent()

    query = (
        "I am a maize farmer in Kigali. Please: "
        "1) fetch the weather forecast for my location, "
        "2) fetch current market prices for maize in the region, and "
        "3) use the knowledge base to give best-practice advice for planting. "
        "Cite sources and be specific."
    )

    result = agent.run(
        query=query,
        farmer_context={
            "farmer": {
                "name": "Trace Farmer",
                "region": "Kigali",
                "location": {"lat": -1.9441, "lon": 30.0619},
            },
            "farms": [
                {
                    "name": "Trace Farm",
                    "crops": [{"type": "maize", "growth_stage": "planting"}],
                }
            ],
        },
    )

    logs_dir = project_root / "logs"
    logs_dir.mkdir(exist_ok=True)
    trace_file = logs_dir / f"trace_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    trace_file.write_text(json.dumps(_sanitize_result(result), indent=2))
    print(f"Trace saved to: {trace_file}")


if __name__ == "__main__":
    main()
