"""Deterministic, evidence-linked one-page bid/no-bid brief generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from procurelens.agent.guardrails import guard_text

DRAFT_BANNER = "DRAFT — analyst review required"


@dataclass(frozen=True)
class BriefResult:
    markdown: str
    recommendation: str
    sources: list[dict[str, Any]]


def _safe(value: Any) -> str:
    return guard_text(str(value or "Not provided"), reject_injection=True).text


def _reason_lines(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "- Not available"
    return "\n".join(f"- {_safe(value)}" for value in values[:4])


def _recommendation(fit_score: int | None, risk_band: str | None) -> tuple[str, str]:
    if fit_score is None:
        return "REVIEW", "Fit scoring evidence is incomplete."
    if fit_score >= 70 and risk_band != "high":
        return "BID", "Strong capability fit with no high amendment-risk signal."
    if fit_score >= 55:
        return "REVIEW", "Potential fit exists, but commercial or delivery risks need mitigation."
    return "NO-BID", "Capability fit is below the configured review threshold."


class BidBriefTool:
    """Compose only from supplied tool evidence; missing facts remain explicit."""

    def compose(
        self,
        *,
        tender: Mapping[str, Any],
        ml_result: Mapping[str, Any] | None = None,
        sql_result: Mapping[str, Any] | None = None,
        rag_result: Mapping[str, Any] | None = None,
    ) -> BriefResult:
        ml_result = ml_result or {}
        sql_result = sql_result or {}
        rag_result = rag_result or {}
        fit = ml_result.get("fit_score") if isinstance(ml_result.get("fit_score"), Mapping) else {}
        amendment = (
            ml_result.get("amendment_risk")
            if isinstance(ml_result.get("amendment_risk"), Mapping)
            else {}
        )
        raw_fit_score = fit.get("score") if isinstance(fit, Mapping) else None
        fit_score = int(raw_fit_score) if isinstance(raw_fit_score, (int, float)) else None
        risk_band = str(amendment.get("risk_band")) if amendment else None
        recommendation, rationale = _recommendation(fit_score, risk_band)

        market_rows = sql_result.get("rows", [])
        if isinstance(market_rows, list) and market_rows:
            market_lines = "\n".join(
                f"- `{_safe(row)}`" for row in market_rows[:3] if isinstance(row, Mapping)
            )
        else:
            market_lines = "- No dbt-mart evidence was supplied."

        sources = rag_result.get("sources", [])
        clean_sources = [source for source in sources if isinstance(source, dict)]
        if clean_sources:
            source_lines = "\n".join(
                f"- [{_safe(source.get('document'))}, p. {int(source.get('page', 0))}]"
                f"({_safe(source.get('url'))})"
                for source in clean_sources[:5]
            )
        else:
            source_lines = "- No governance source was retrieved; analyst verification is required."

        fit_band_display = fit.get("fit_band") if fit else None
        fit_version = fit.get("scorer_version") if fit else None
        amendment_probability = amendment.get("probability") if amendment else None
        amendment_version = amendment.get("model_version") if amendment else None

        markdown = f"""# {DRAFT_BANNER}

## Bid / No-Bid Brief — {_safe(tender.get('tender_id'))}

### Opportunity

- **Title:** {_safe(tender.get('tender_title'))}
- **Agency:** {_safe(tender.get('agency'))}
- **Estimated value:** {_safe(tender.get('estimated_value_aud'))} AUD
- **Procurement method:** {_safe(tender.get('procurement_method'))}
- **Close date:** {_safe(tender.get('close_date'))}

### Model signals

- **Fit:** {_safe(fit_score)}/100 ({_safe(fit_band_display)}) — scorer {_safe(fit_version)}
- **Amendment risk:** {_safe(amendment_probability)} ({_safe(risk_band)})
  — model {_safe(amendment_version)}

**Positive fit evidence**
{_reason_lines(fit.get('positive_reasons') if fit else None)}

**Negative fit evidence**
{_reason_lines(fit.get('negative_reasons') if fit else None)}

### Market evidence from dbt marts

{market_lines}

### Governance considerations

{_safe(rag_result.get('answer', 'No guidance retrieved.'))}

### Recommendation: {recommendation}

{rationale} Validate mandatory criteria, conflicts, delivery capacity, pricing and probity
before approval.

### Sources

{source_lines}

---
{DRAFT_BANNER}
"""
        if DRAFT_BANNER not in markdown:
            raise RuntimeError("draft review banner is mandatory")
        return BriefResult(
            markdown=markdown,
            recommendation=recommendation,
            sources=clean_sources,
        )


def compose_brief(
    tender_id: str,
    *,
    tender: Mapping[str, Any] | None = None,
    ml_result: Mapping[str, Any] | None = None,
    sql_result: Mapping[str, Any] | None = None,
    rag_result: Mapping[str, Any] | None = None,
) -> str:
    payload = {**dict(tender or {}), "tender_id": tender_id}
    return BidBriefTool().compose(
        tender=payload,
        ml_result=ml_result,
        sql_result=sql_result,
        rag_result=rag_result,
    ).markdown
