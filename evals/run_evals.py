"""Command-line entrypoint for the deterministic ProcureLens CI evaluation gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from procurelens.evals.harness import evaluate_golden_set, render_markdown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", action="store_true", help="exit non-zero when a gate fails")
    parser.add_argument("--golden", default="evals/golden_set.jsonl")
    parser.add_argument("--corpus", default="config/rag_corpus.json")
    parser.add_argument("--output", default=None, help="optional JSON report path")
    parser.add_argument("--summary-output", default=None, help="optional Markdown summary path")
    args = parser.parse_args(argv)

    report = evaluate_golden_set(args.golden, corpus_path=args.corpus)
    payload = json.dumps(report.to_dict(), indent=2, ensure_ascii=False)
    summary = render_markdown(report)
    print(summary, end="")
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    if args.summary_output:
        summary_output = Path(args.summary_output)
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_output.write_text(summary, encoding="utf-8")
    if args.gate and not report.passed:
        print(f"EVAL GATE FAILED: {json.dumps(report.failures, sort_keys=True)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
