from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from procurelens.monitoring.drift import (
    _metric_summary,
    _read_frame,
    _sample,
    build_drift_report,
    main,
)


def _frame(*, shifted: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    size = 300
    return pd.DataFrame(
        {
            "award_value_aud": rng.lognormal(12.0 + (2.0 if shifted else 0.0), 0.5, size),
            "contract_duration_days": rng.normal(800 if shifted else 365, 30, size),
            "procurement_method": ["limited" if shifted else "open"] * size,
            "prediction": rng.beta(8, 2, size) if shifted else rng.beta(2, 8, size),
        }
    )


def test_evidently_report_writes_html_json_and_prediction_drift(tmp_path: Path):
    reference = tmp_path / "reference.csv"
    current = tmp_path / "current.csv"
    html = tmp_path / "drift.html"
    _frame().to_csv(reference, index=False)
    _frame(shifted=True).to_csv(current, index=False)

    summary = build_drift_report(str(reference), str(current), str(html))

    assert html.exists() and html.stat().st_size > 1_000
    assert Path(summary.json_path).exists()
    assert Path(summary.json_path).with_name("drift.summary.json").exists()
    assert summary.reference_rows == 300
    assert summary.current_rows == 300
    assert summary.prediction_drifted is True
    assert summary.prediction_drift_score >= 0.2
    assert summary.dataset_drift is True


def test_identical_batches_do_not_trigger_prediction_drift(tmp_path: Path):
    frame = _frame()
    reference = tmp_path / "reference.jsonl"
    current = tmp_path / "current.jsonl"
    frame.to_json(reference, orient="records", lines=True)
    frame.to_json(current, orient="records", lines=True)
    summary = build_drift_report(
        str(reference),
        str(current),
        str(tmp_path / "stable.html"),
    )
    assert summary.prediction_drifted is False
    assert summary.prediction_drift_score == 0.0
    assert summary.dataset_drift is False


def test_drift_cli_prints_summary_and_uses_explicit_json_path(tmp_path: Path, capsys):
    reference = tmp_path / "reference.csv"
    current = tmp_path / "current.csv"
    output_json = tmp_path / "evidently.json"
    _frame().to_csv(reference, index=False)
    _frame().to_csv(current, index=False)
    assert (
        main(
            [
                "--reference",
                str(reference),
                "--current",
                str(current),
                "--output-html",
                str(tmp_path / "report.html"),
                "--output-json",
                str(output_json),
            ]
        )
        == 0
    )
    assert output_json.exists()
    assert json.loads(capsys.readouterr().out)["prediction_column"] == "prediction"


@pytest.mark.parametrize("suffix", [".json", ".parquet"])
def test_supported_drift_input_formats(tmp_path: Path, suffix: str):
    path = tmp_path / f"data{suffix}"
    frame = _frame().head(100)
    if suffix == ".json":
        frame.to_json(path, orient="records")
    else:
        frame.to_parquet(path)
    loaded = _read_frame(path)
    assert len(loaded) == 100


def test_drift_validation_rejects_bad_inputs(tmp_path: Path):
    empty = tmp_path / "empty.csv"
    missing_prediction = tmp_path / "missing.csv"
    other = tmp_path / "other.csv"
    pd.DataFrame(columns=["prediction"]).to_csv(empty, index=False)
    pd.DataFrame({"feature": range(100)}).to_csv(missing_prediction, index=False)
    pd.DataFrame({"feature": range(100), "prediction": range(100)}).to_csv(other, index=False)
    with pytest.raises(ValueError, match="non-empty"):
        build_drift_report(str(empty), str(other), str(tmp_path / "x.html"))
    with pytest.raises(ValueError, match="columns differ"):
        build_drift_report(
            str(missing_prediction), str(other), str(tmp_path / "x.html")
        )
    with pytest.raises(ValueError, match="threshold"):
        build_drift_report(str(other), str(other), str(tmp_path / "x.html"), threshold=0)
    with pytest.raises(ValueError, match="dataset drift share"):
        build_drift_report(
            str(other), str(other), str(tmp_path / "x.html"), dataset_drift_share=2
        )


def test_drift_helpers_reject_unknown_format_small_sample_and_missing_metric(tmp_path: Path):
    unknown = tmp_path / "data.txt"
    unknown.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="CSV, Parquet"):
        _read_frame(unknown)
    with pytest.raises(FileNotFoundError):
        _read_frame(tmp_path / "absent.csv")
    with pytest.raises(ValueError, match="at least 100"):
        _sample(_frame(), 99)
    with pytest.raises(RuntimeError, match="prediction drift"):
        _metric_summary({"metrics": []}, prediction_column="prediction")
