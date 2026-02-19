#!/usr/bin/env python
"""
Run the agent evaluation test suite.

Usage:
    python scripts/run_evaluation.py
    python scripts/run_evaluation.py --output results.md
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agent import create_agent
from src.evaluation.test_suite import (
    run_test_suite,
    format_results_table,
    get_summary_stats,
)


def main():
    parser = argparse.ArgumentParser(description="Run agent evaluation test suite")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file for results (default: print to stdout)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )
    args = parser.parse_args()
    
    print("=" * 80)
    print("AGENT EVALUATION TEST SUITE")
    print("=" * 80)
    print()
    
    # Create agent
    print("Initializing agent...")
    agent = create_agent()
    
    # Sample farmer context
    farmer_context = {
        "user_id": "test_user",
        "farms": [
            {
                "name": "Test Farm",
                "crops": [
                    {"type": "maize", "growth_stage": "vegetative"},
                    {"type": "beans", "growth_stage": "flowering"},
                ],
            }
        ],
    }
    
    # Run test suite
    print("Running test suite...")
    print()
    
    results = run_test_suite(
        agent_run_fn=agent.run,
        farmer_context=farmer_context,
    )
    
    # Format results
    table = format_results_table(results)
    summary = get_summary_stats(results)
    
    # Output
    output_lines = [
        "# Agent Evaluation Results",
        f"Generated: {datetime.now().isoformat()}",
        "",
        "## Summary Statistics",
        "",
        f"- Total Tests: {summary['total_tests']}",
        f"- Passed: {summary['passed_tests']}",
        f"- Failed: {summary['failed_tests']}",
        f"- Average Groundedness: {summary['avg_groundedness']:.2f}",
        f"- Average Tool Accuracy: {summary['avg_tool_accuracy']:.2f}",
        f"- Average Completion Rate: {summary['avg_completion_rate']:.2f}",
        f"- Average Iterations: {summary['avg_iterations']:.1f}",
        f"- Average Hallucination Frequency: {summary['avg_hallucination_freq']:.2f}",
        "",
        "## Detailed Results",
        "",
        table,
    ]
    
    output_text = "\n".join(output_lines)
    
    if args.json:
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
            "results": [
                {
                    "test_case": {
                        "id": r["test_case"].id,
                        "query": r["test_case"].query,
                        "category": r["test_case"].category,
                    },
                    "metrics": r["metrics"].to_dict() if r.get("metrics") else None,
                    "passed": r.get("passed", False),
                }
                for r in results
            ],
        }
        output_text = json.dumps(output_data, indent=2)
    
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output_text)
        print(f"Results saved to {output_path}")
    else:
        print(output_text)
    
    # Print summary to console
    print()
    print("=" * 80)
    print("EVALUATION COMPLETE")
    print("=" * 80)
    print(f"Passed: {summary['passed_tests']}/{summary['total_tests']}")


if __name__ == "__main__":
    main()
