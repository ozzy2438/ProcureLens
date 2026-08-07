from __future__ import annotations

import json
from pathlib import Path

import pytest

from procurelens.evals.harness import (
    CASE_TYPES,
    THRESHOLDS,
    evaluate_golden_set,
    load_golden_set,
    render_markdown,
)

GOLDEN = Path("evals/golden_set.jsonl")


def test_golden_set_has_at_least_40_unique_cases_and_all_required_categories():
    cases = load_golden_set(GOLDEN)
    assert len(cases) == 45
    assert len({case["id"] for case in cases}) == len(cases)
    assert {case["type"] for case in cases} == CASE_TYPES


def test_real_golden_evaluation_meets_every_ci_gate():
    report = evaluate_golden_set(GOLDEN)
    assert report.case_count == 45
    assert report.passed is True
    assert report.failures == {}
    assert report.metrics["groundedness"] >= THRESHOLDS["groundedness"]
    assert report.metrics["sql_accuracy"] >= THRESHOLDS["sql_accuracy"]
    assert report.metrics["tool_routing"] >= THRESHOLDS["tool_routing"]
    assert report.metrics["guardrail_pass"] == 1.0
    assert report.metrics["citation_accuracy"] == 1.0
    assert report.metrics["brief_quality"] == 1.0


def test_gate_fails_when_observed_metric_is_below_configured_threshold():
    report = evaluate_golden_set(GOLDEN, thresholds={"tool_routing": 1.01})
    assert report.passed is False
    assert report.failures["tool_routing"] == {"actual": 1.0, "threshold": 1.01}


def test_markdown_and_json_reports_contain_observed_scores():
    report = evaluate_golden_set(GOLDEN)
    summary = render_markdown(report)
    payload = report.to_dict()
    assert "Golden cases: **45**" in summary
    assert "groundedness" in summary
    assert "Overall: **PASS**" in summary
    assert payload["case_count"] == 45
    assert len(payload["cases"]) == 45


@pytest.mark.parametrize(
    "content, message",
    [
        ("not-json\n", "invalid JSON"),
        (json.dumps(["not", "an", "object"]), "must be a JSON object"),
        (json.dumps({"id": "x", "type": "sql"}), "is missing"),
        (
            json.dumps({"id": "x", "type": "unsupported", "question": "hello"}),
            "unsupported golden case type",
        ),
    ],
)
def test_invalid_golden_rows_are_rejected(tmp_path: Path, content: str, message: str):
    path = tmp_path / "invalid.jsonl"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_golden_set(path, minimum_cases=1)


def test_duplicate_ids_are_rejected(tmp_path: Path):
    path = tmp_path / "duplicates.jsonl"
    row = json.dumps({"id": "same", "type": "sql", "question": "show contracts"})
    path.write_text(f"{row}\n{row}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be unique"):
        load_golden_set(path, minimum_cases=2)


def test_incomplete_category_coverage_is_rejected(tmp_path: Path):
    path = tmp_path / "one-type.jsonl"
    path.write_text(
        json.dumps({"id": "one", "type": "sql", "question": "show contracts"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must cover every case type"):
        load_golden_set(path, minimum_cases=1)
