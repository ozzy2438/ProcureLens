import json
from pathlib import Path

from procurelens.monitoring.smoke import main, run_drift_smoke, run_langfuse_smoke


def test_real_langfuse_sdk_smoke_exports_only_safe_span_attributes(tmp_path: Path):
    output = tmp_path / "langfuse.json"
    summary = run_langfuse_smoke(output)
    payload = output.read_text(encoding="utf-8")
    assert summary["span_count"] == 3
    assert summary["privacy_verified"] is True
    assert summary["tool_call_verified"] is True
    assert summary["generation_verified"] is True
    assert summary["token_usage_verified"] is True
    assert "bid-intelligence-agent" in summary["span_names"]
    assert "analyst@example.gov.au" not in payload
    assert "sha256" in payload


def test_monitoring_smoke_generates_drift_artifacts(tmp_path: Path):
    summary = run_drift_smoke(tmp_path)
    assert summary.dataset_drift is True
    assert summary.prediction_drifted is True
    assert Path(summary.html_path).exists()
    assert Path(summary.json_path).exists()


def test_monitoring_smoke_cli_writes_combined_summary(tmp_path: Path, capsys):
    assert main(["--output-dir", str(tmp_path)]) == 0
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["langfuse"]["privacy_verified"] is True
    assert summary["drift"]["prediction_drifted"] is True
    assert "langfuse" in capsys.readouterr().out
