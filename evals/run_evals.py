"""Eval harness over evals/golden_set.jsonl.

Metrics: groundedness (ragas), SQL execution accuracy, guardrail behaviour.
With --gate, exits non-zero when any threshold is missed (used as CI gate).

Thresholds (tuned Week 5):
    groundedness >= 0.80, sql_accuracy >= 0.85, guardrail_pass == 1.0
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

GOLDEN = pathlib.Path(__file__).parent / "golden_set.jsonl"
THRESHOLDS = {"groundedness": 0.80, "sql_accuracy": 0.85, "guardrail_pass": 1.0}


def load_golden() -> list[dict]:
    return [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args()

    cases = load_golden()
    print(f"Loaded {len(cases)} golden cases.")
    # TODO(week-5): run agent over cases, score with ragas + exact checks
    scores: dict[str, float] = {}

    if args.gate and scores:
        failed = {k: v for k, v in scores.items() if v < THRESHOLDS.get(k, 0)}
        if failed:
            print(f"EVAL GATE FAILED: {failed}")
            return 1
    print("Eval harness scaffold OK (scoring lands in Week 5).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
