"""Evidently data and prediction drift reports for amendment-risk monitoring."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class DriftSummary:
    reference_rows: int
    current_rows: int
    drifted_columns: int
    drifted_share: float
    dataset_drift: bool
    prediction_column: str
    prediction_drift_score: float
    prediction_drifted: bool
    method: str
    threshold: float
    html_path: str
    json_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_frame(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(source)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(source)
    if suffix == ".jsonl":
        return pd.read_json(source, lines=True)
    if suffix == ".json":
        return pd.read_json(source)
    raise ValueError("drift inputs must be CSV, Parquet, JSON or JSONL")


def _validate_frames(
    reference: pd.DataFrame,
    current: pd.DataFrame,
    *,
    prediction_column: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if reference.empty or current.empty:
        raise ValueError("reference and current drift datasets must be non-empty")
    if reference.columns.duplicated().any() or current.columns.duplicated().any():
        raise ValueError("drift datasets cannot contain duplicate column names")
    if set(reference.columns) != set(current.columns):
        missing_current = sorted(set(reference.columns).difference(current.columns))
        extra_current = sorted(set(current.columns).difference(reference.columns))
        raise ValueError(
            f"drift dataset columns differ; missing={missing_current}, extra={extra_current}"
        )
    if prediction_column not in reference.columns:
        raise ValueError(f"prediction column is missing: {prediction_column}")
    return reference, current.loc[:, reference.columns]


def _sample(frame: pd.DataFrame, sample_size: int) -> pd.DataFrame:
    if sample_size < 100:
        raise ValueError("sample_size must be at least 100")
    if len(frame) <= sample_size:
        return frame
    return frame.sample(sample_size, random_state=42).reset_index(drop=True)


def _metric_summary(
    payload: dict[str, Any], *, prediction_column: str
) -> tuple[int, float, float]:
    drifted_columns = 0
    drifted_share = 0.0
    prediction_score: float | None = None
    for metric in payload.get("metrics", []):
        if not isinstance(metric, dict):
            continue
        config = metric.get("config", {})
        metric_type = str(config.get("type", "")) if isinstance(config, dict) else ""
        if metric_type.endswith("DriftedColumnsCount"):
            value = metric.get("value", {})
            if isinstance(value, dict):
                drifted_columns = int(float(value.get("count", 0)))
                drifted_share = float(value.get("share", 0.0))
        elif metric_type.endswith("ValueDrift") and config.get("column") == prediction_column:
            prediction_score = float(metric.get("value", 0.0))
    if prediction_score is None:
        raise RuntimeError("Evidently report did not contain prediction drift")
    return drifted_columns, drifted_share, prediction_score


def build_drift_report(
    reference_path: str,
    current_path: str,
    out_html: str,
    *,
    out_json: str | None = None,
    prediction_column: str = "prediction",
    method: str = "psi",
    threshold: float = 0.2,
    dataset_drift_share: float = 0.5,
    sample_size: int = 100_000,
) -> DriftSummary:
    """Build local HTML/JSON drift artefacts and return machine-readable signals."""
    if not 0 < threshold <= 1:
        raise ValueError("drift threshold must be in (0, 1]")
    if not 0 < dataset_drift_share <= 1:
        raise ValueError("dataset drift share must be in (0, 1]")
    reference_raw = _read_frame(reference_path)
    current_raw = _read_frame(current_path)
    reference, current = _validate_frames(
        reference_raw,
        current_raw,
        prediction_column=prediction_column,
    )
    reference_eval = _sample(reference, sample_size)
    current_eval = _sample(current, sample_size)

    from evidently import Report
    from evidently.metrics import ValueDrift
    from evidently.presets import DataDriftPreset

    report = Report(
        [
            DataDriftPreset(
                drift_share=dataset_drift_share,
                method=method,
                threshold=threshold,
            ),
            ValueDrift(column=prediction_column, method=method, threshold=threshold),
        ],
        include_tests=True,
        tags=["procurelens", "amendment-risk", "drift"],
        metadata={
            "prediction_column": prediction_column,
            "method": method,
            "threshold": str(threshold),
        },
    )
    snapshot = report.run(current_data=current_eval, reference_data=reference_eval)
    payload = snapshot.dict()
    drifted_columns, drifted_share, prediction_score = _metric_summary(
        payload, prediction_column=prediction_column
    )

    html_path = Path(out_html)
    json_path = Path(out_json) if out_json else html_path.with_suffix(".json")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot.save_html(str(html_path))
    snapshot.save_json(str(json_path))
    summary = DriftSummary(
        reference_rows=len(reference_raw),
        current_rows=len(current_raw),
        drifted_columns=drifted_columns,
        drifted_share=round(drifted_share, 6),
        dataset_drift=drifted_share >= dataset_drift_share,
        prediction_column=prediction_column,
        prediction_drift_score=round(prediction_score, 6),
        prediction_drifted=prediction_score >= threshold,
        method=method,
        threshold=threshold,
        html_path=str(html_path),
        json_path=str(json_path),
    )
    summary_path = json_path.with_name(f"{json_path.stem}.summary.json")
    summary_path.write_text(
        json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True)
    parser.add_argument("--current", required=True)
    parser.add_argument("--output-html", required=True)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--prediction-column", default="prediction")
    parser.add_argument("--method", default="psi")
    parser.add_argument("--threshold", type=float, default=0.2)
    args = parser.parse_args(argv)
    summary = build_drift_report(
        args.reference,
        args.current,
        args.output_html,
        out_json=args.output_json,
        prediction_column=args.prediction_column,
        method=args.method,
        threshold=args.threshold,
    )
    print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
