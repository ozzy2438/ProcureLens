"""Executable golden-set evaluation over the real governed agent components."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from procurelens.agent.graph import route_question
from procurelens.agent.guardrails import PromptInjectionError, guard_text
from procurelens.agent.tools.brief_tool import DRAFT_BANNER, BidBriefTool
from procurelens.agent.tools.rag_tool import ProcurementRAGTool
from procurelens.agent.tools.sql_tool import plan_nl_query

THRESHOLDS = {
    "groundedness": 0.80,
    "sql_accuracy": 0.85,
    "tool_routing": 0.90,
    "guardrail_pass": 1.0,
}
CASE_TYPES = {"sql", "rag", "routing", "brief", "guardrail"}
OFFICIAL_SOURCE_PREFIXES = (
    "https://www.finance.gov.au/",
    "https://www.anao.gov.au/",
)


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    case_type: str
    passed: bool
    scores: dict[str, float]
    details: dict[str, Any]


@dataclass(frozen=True)
class EvalReport:
    generated_at: str
    case_count: int
    metrics: dict[str, float]
    thresholds: dict[str, float]
    passed: bool
    failures: dict[str, dict[str, float]]
    cases: list[CaseResult]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cases"] = [asdict(case) for case in self.cases]
        return payload


def load_golden_set(path: str | Path, *, minimum_cases: int = 40) -> list[dict[str, Any]]:
    """Load and strictly validate the versioned JSONL evaluation contract."""
    source = Path(path)
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on golden-set line {line_number}") from exc
        if not isinstance(case, dict):
            raise ValueError(f"golden-set line {line_number} must be a JSON object")
        missing = {"id", "type", "question"}.difference(case)
        if missing:
            raise ValueError(f"golden-set line {line_number} is missing {sorted(missing)}")
        if case["type"] not in CASE_TYPES:
            raise ValueError(f"unsupported golden case type: {case['type']}")
        if not isinstance(case["question"], str) or not case["question"].strip():
            raise ValueError(f"golden case {case['id']} has an empty question")
        cases.append(case)
    if len(cases) < minimum_cases:
        raise ValueError(f"golden set requires at least {minimum_cases} cases; found {len(cases)}")
    identifiers = [str(case["id"]) for case in cases]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("golden-set case ids must be unique")
    present_types = {str(case["type"]) for case in cases}
    if present_types != CASE_TYPES:
        raise ValueError(f"golden set must cover every case type: {sorted(CASE_TYPES)}")
    return cases


def _contains_all(text: str, expected: list[Any]) -> bool:
    lowered = text.lower()
    return all(str(value).lower() in lowered for value in expected)


def _routing_score(case: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    expected_route = case.get("expected_route")
    if expected_route is None:
        return {}, {}
    actual_route = route_question(str(case["question"]), case.get("context"))
    passed = actual_route == expected_route
    return {"tool_routing": float(passed)}, {
        "expected_route": expected_route,
        "actual_route": actual_route,
    }


def _evaluate_sql(case: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    expected = dict(case.get("expected", {}))
    plan = plan_nl_query(str(case["question"]), case.get("context"))
    checks = {
        "intent": plan.intent == expected.get("intent"),
        "agency": plan.params.get("agency_pattern") == expected.get("agency_pattern"),
        "query_fragments": _contains_all(plan.query, list(expected.get("query_contains", []))),
    }
    if "limit" in expected:
        checks["limit"] = plan.params.get("requested_limit") == expected["limit"]
    passed = all(checks.values())
    return {"sql_accuracy": float(passed)}, {
        "intent": plan.intent,
        "params": plan.params,
        "checks": checks,
    }


def _evaluate_rag(
    case: Mapping[str, Any], rag_tool: ProcurementRAGTool
) -> tuple[dict[str, float], dict[str, Any]]:
    expected = dict(case.get("expected", {}))
    result = rag_tool.answer(str(case["question"]), k=4)
    chunk_ids = [chunk.chunk_id for chunk in result.chunks]
    expected_ids = [str(value) for value in expected.get("source_ids", [])]
    claims_are_extractive = all(chunk.content in result.answer for chunk in result.chunks)
    expected_sources_found = all(identifier in chunk_ids for identifier in expected_ids)
    expected_phrases_found = _contains_all(
        result.answer, list(expected.get("answer_contains", []))
    )
    grounded = bool(result.chunks) and all(
        (claims_are_extractive, expected_sources_found, expected_phrases_found)
    )
    citations_valid = bool(result.sources) and len(result.sources) == len(result.chunks)
    citations_valid = citations_valid and all(
        source.page > 0
        and source.url.startswith(OFFICIAL_SOURCE_PREFIXES)
        and source.url in result.answer
        and bool(source.document)
        for source in result.sources
    )
    return {
        "groundedness": float(grounded),
        "citation_accuracy": float(citations_valid),
    }, {
        "retrieved_ids": chunk_ids,
        "expected_ids": expected_ids,
        "claims_are_extractive": claims_are_extractive,
        "expected_phrases_found": expected_phrases_found,
        "citations_valid": citations_valid,
    }


def _evaluate_brief(
    case: Mapping[str, Any], rag_tool: ProcurementRAGTool, brief_tool: BidBriefTool
) -> tuple[dict[str, float], dict[str, Any]]:
    context = dict(case.get("context", {}))
    score = context.get("fit_score")
    fit_payload: dict[str, Any] = {
        "score": score,
        "fit_band": context.get("fit_band"),
        "positive_reasons": ["Capability evidence matches the opportunity"],
        "negative_reasons": ["Analyst must validate delivery capacity"],
        "scorer_version": "golden-1.0",
    }
    rag_result = rag_tool.answer("value for money procurement risk").model_dump()
    result = brief_tool.compose(
        tender={
            "tender_id": context.get("tender_id"),
            "tender_title": context.get("title"),
            "agency": context.get("agency"),
            "estimated_value_aud": 750_000,
            "procurement_method": "open",
            "close_date": "2026-09-30",
        },
        ml_result={
            "fit_score": fit_payload,
            "amendment_risk": {
                "probability": 0.2,
                "risk_band": context.get("risk_band"),
                "model_version": "golden-1",
            },
        },
        sql_result={
            "rows": [{"agency": context.get("agency"), "contracts_all_time": 12}]
        },
        rag_result=rag_result,
    )
    expected_recommendation = str(dict(case.get("expected", {})).get("recommendation"))
    checks = {
        "banner": result.markdown.count(DRAFT_BANNER) >= 2,
        "recommendation": result.recommendation == expected_recommendation,
        "fit_evidence": "### Model signals" in result.markdown,
        "market_evidence": "### Market evidence from dbt marts" in result.markdown,
        "governance_evidence": "### Governance considerations" in result.markdown,
        "citations": bool(result.sources)
        and all(str(source["url"]) in result.markdown for source in result.sources),
        "one_page_budget": len(result.markdown.split()) <= 650,
    }
    passed = all(checks.values())
    return {"brief_quality": float(passed)}, {
        "recommendation": result.recommendation,
        "word_count": len(result.markdown.split()),
        "checks": checks,
    }


def _evaluate_guardrail(case: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
    expected = dict(case.get("expected", {}))
    behaviour = str(expected.get("behaviour"))
    blocked = False
    output = ""
    try:
        output = guard_text(str(case["question"]), reject_injection=True).text
    except PromptInjectionError:
        blocked = True

    if behaviour == "block":
        passed = blocked
    elif behaviour in {"redact", "allow"}:
        passed = not blocked
        passed = passed and _contains_all(output, list(expected.get("contains", [])))
        passed = passed and not any(
            str(value).lower() in output.lower() for value in expected.get("absent", [])
        )
        if behaviour == "redact":
            passed = passed and output != str(case["question"])
    else:
        passed = False
    return {"guardrail_pass": float(passed)}, {
        "expected_behaviour": behaviour,
        "blocked": blocked,
        "output_changed": output != str(case["question"]),
    }


def evaluate_case(
    case: Mapping[str, Any],
    *,
    rag_tool: ProcurementRAGTool,
    brief_tool: BidBriefTool,
) -> CaseResult:
    """Evaluate one case and retain only non-sensitive diagnostic metadata."""
    scores, details = _routing_score(case)
    case_type = str(case["type"])
    if case_type == "sql":
        component_scores, component_details = _evaluate_sql(case)
    elif case_type == "rag":
        component_scores, component_details = _evaluate_rag(case, rag_tool)
    elif case_type == "brief":
        component_scores, component_details = _evaluate_brief(case, rag_tool, brief_tool)
    elif case_type == "guardrail":
        component_scores, component_details = _evaluate_guardrail(case)
    else:
        component_scores, component_details = {}, {}
    scores.update(component_scores)
    details.update(component_details)
    return CaseResult(
        case_id=str(case["id"]),
        case_type=case_type,
        passed=bool(scores) and all(value == 1.0 for value in scores.values()),
        scores=scores,
        details=details,
    )


def evaluate_golden_set(
    golden_path: str | Path,
    *,
    corpus_path: str | Path = "config/rag_corpus.json",
    thresholds: Mapping[str, float] | None = None,
) -> EvalReport:
    """Run every case and calculate observed rates used by the CI gate."""
    cases = load_golden_set(golden_path)
    rag_tool = ProcurementRAGTool(corpus_path)
    brief_tool = BidBriefTool()
    results = [
        evaluate_case(case, rag_tool=rag_tool, brief_tool=brief_tool) for case in cases
    ]
    samples: dict[str, list[float]] = {}
    for result in results:
        for metric, value in result.scores.items():
            samples.setdefault(metric, []).append(value)
    metrics = {
        metric: round(sum(values) / len(values), 4)
        for metric, values in sorted(samples.items())
    }
    gates = dict(thresholds or THRESHOLDS)
    failures = {
        metric: {"actual": metrics.get(metric, 0.0), "threshold": threshold}
        for metric, threshold in gates.items()
        if metrics.get(metric, 0.0) < threshold
    }
    return EvalReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        case_count=len(cases),
        metrics=metrics,
        thresholds=gates,
        passed=not failures,
        failures=failures,
        cases=results,
    )


def render_markdown(report: EvalReport) -> str:
    """Render a compact GitHub workflow summary."""
    lines = [
        "## ProcureLens agent evaluation",
        "",
        f"Golden cases: **{report.case_count}**",
        "",
        "| Metric | Actual | Gate | Status |",
        "|---|---:|---:|---|",
    ]
    for metric, value in report.metrics.items():
        threshold = report.thresholds.get(metric)
        if threshold is None:
            status = "informational"
            threshold_text = "—"
        else:
            status = "pass" if value >= threshold else "FAIL"
            threshold_text = f"{threshold:.2f}"
        lines.append(f"| {metric} | {value:.4f} | {threshold_text} | {status} |")
    lines.extend(["", f"Overall: **{'PASS' if report.passed else 'FAIL'}**"])
    return "\n".join(lines) + "\n"
