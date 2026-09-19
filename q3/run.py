"""Command-line entry point for the Q3 evaluation harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluator import evaluate_dataset
from src.loader import load_captured_fields, load_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Blooming Health Q3 conversations.")
    parser.add_argument("--input", required=True, help="Path to candidate-facing conversation JSON.")
    parser.add_argument("--output", required=True, help="Path to write structured JSON results.")
    parser.add_argument(
        "--captured-fields",
        help="Optional JSON containing claimed captured fields by thread.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = load_dataset(Path(args.input))
    captured_fields = load_captured_fields(Path(args.captured_fields)) if args.captured_fields else None
    report = evaluate_dataset(dataset, captured_fields=captured_fields)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
