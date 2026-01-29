#!/usr/bin/env python
"""
Launch the Farmer RAG Advisory System.

Usage:
    python scripts/run_app.py
    python scripts/run_app.py --share
    python scripts/run_app.py --port 8080
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(
        description="Launch the Farmer RAG Advisory System"
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Create a public shareable link",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port to run the server on (default: 7860)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )

    args = parser.parse_args()

    from src.ui.app import launch_app

    launch_app(
        share=args.share,
        server_port=args.port,
        debug=args.debug,
    )


if __name__ == "__main__":
    main()
