"""Render retraining result JSON into a GitHub Actions job summary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def render_summary(result: dict[str, Any]) -> str:
    promotion = (
        "promoted"
        if result.get("promotion_accepted") is True
        else "not promoted"
    )
    return "\n".join(
        [
            "## ProcureLens monthly retraining",
            "",
            f"- Registered version: `{result.get('registered_model_version', 'unknown')}`",
            f"- MLflow run: `{result.get('run_id', 'unknown')}`",
            f"- Snapshot SHA-256: `{result.get('data_snapshot_sha256', 'unknown')}`",
            f"- Rows: {result.get('train_rows', 'unknown')} train / "
            f"{result.get('holdout_rows', 'unknown')} holdout",
            f"- Promotion: **{promotion}** — {result.get('promotion_reason', 'unknown')}",
            "",
            "| Metric | Holdout |",
            "|---|---:|",
            f"| AUC-ROC | {float(result.get('holdout_auc_roc', 0)):.4f} |",
            f"| PR-AUC | {float(result.get('holdout_pr_auc', 0)):.4f} |",
            f"| Brier | {float(result.get('holdout_brier_score', 0)):.4f} |",
            f"| ECE | {float(result.get('holdout_ece', 0)):.4f} |",
            "",
        ]
    )


def main(metrics_path: str, summary_path: str | None = None) -> None:
    destination = Path(summary_path or os.environ.get("GITHUB_STEP_SUMMARY", "retrain-summary.md"))
    source = Path(metrics_path)
    if source.exists():
        summary = render_summary(json.loads(source.read_text(encoding="utf-8")))
    else:
        summary = (
            "## ProcureLens monthly retraining\n\n"
            "Training failed before metrics were written.\n"
        )
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--summary", default=None)
    arguments = parser.parse_args()
    main(arguments.metrics, arguments.summary)
