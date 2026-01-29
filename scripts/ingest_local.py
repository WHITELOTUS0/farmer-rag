#!/usr/bin/env python
"""
Ingest documents from a local directory.

Usage:
    python scripts/ingest_local.py /path/to/documents
    python scripts/ingest_local.py /path/to/documents --recursive
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(
        description="Ingest documents into the knowledge base"
    )
    parser.add_argument(
        "path",
        type=str,
        help="Path to document or directory",
    )
    parser.add_argument(
        "--recursive",
        "-r",
        action="store_true",
        help="Search subdirectories recursively",
    )

    args = parser.parse_args()
    path = Path(args.path)

    if not path.exists():
        print(f"Error: Path does not exist: {path}")
        sys.exit(1)

    from src.ingestion.pipeline import IngestionPipeline

    pipeline = IngestionPipeline()

    if path.is_file():
        print(f"Ingesting file: {path}")
        result = pipeline.ingest_file(str(path))

        if result["success"]:
            print(f"✅ Success: {result['chunk_count']} chunks created")
        else:
            print(f"❌ Failed: {result['error']}")
    else:
        print(f"Ingesting directory: {path}")
        result = pipeline.ingest_directory(str(path), recursive=args.recursive)

        print(f"\nResults:")
        print(f"  Total files: {result['total_files']}")
        print(f"  Successful: {result['successful']}")
        print(f"  Failed: {result['failed']}")

        if result["failed"] > 0:
            print("\nFailed files:")
            for r in result["results"]:
                if not r["success"]:
                    print(f"  - {r['document'].get('filename', 'Unknown')}: {r['error']}")


if __name__ == "__main__":
    main()
