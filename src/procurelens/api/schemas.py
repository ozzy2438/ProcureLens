"""Strict Pydantic contracts for the model service."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


ProcurementMethod = Literal["open", "limited", "selective", "prequalified", "panel"]
FitBand = Literal["strong_fit", "review", "low_fit"]


class AmendmentRiskRequest(StrictRequest):
    agency: str = Field(min_length=2, max_length=240)
    unspsc_category: str = Field(pattern=r"^\d{2,8}$")
    procurement_method: ProcurementMethod
    contract_value_aud: float = Field(gt=0, le=1_000_000_000_000)
    contract_duration_days: int = Field(ge=0, le=36_600)
    award_date: date | None = None
    has_confidentiality: bool = False
    supplier_prior_contracts: int = Field(default=0, ge=0, le=10_000_000)
    supplier_prior_amendment_rate: float = Field(default=0.0, ge=0, le=1)
    supplier_agency_prior_contracts: int = Field(default=0, ge=0, le=10_000_000)


class ShapDriver(BaseModel):
    feature: str
    impact: float
    direction: Literal["increases_risk", "decreases_risk"]


class AmendmentRiskResponse(BaseModel):
    probability: float = Field(ge=0, le=1)
    risk_band: Literal["low", "medium", "high"]
    model_version: str
    top_drivers: list[ShapDriver] = Field(default_factory=list)


class AmendmentRiskBatchRequest(StrictRequest):
    items: list[AmendmentRiskRequest] = Field(min_length=1, max_length=100)


class AmendmentRiskBatchResponse(BaseModel):
    predictions: list[AmendmentRiskResponse]
    model_version: str
    count: int = Field(ge=1, le=100)


class FitScoreRequest(StrictRequest):
    tender_id: str = Field(min_length=1, max_length=160)
    unspsc_category: str = Field(pattern=r"^\d{2,8}$")
    agency: str = Field(min_length=2, max_length=240)
    estimated_value_aud: float | None = Field(default=None, gt=0, le=1_000_000_000_000)
    procurement_method: ProcurementMethod = "open"
    tender_title: str = Field(default="", max_length=500)
    tender_description: str = Field(default="", max_length=10_000)
    as_of_date: date = Field(default_factory=date.today)
    close_date: date | None = None
    agency_recent_tech_spend_aud: float = Field(default=0, ge=0)
    agency_familiarity_count: int = Field(default=0, ge=0)
    supplier_hhi: float | None = Field(default=None, ge=0, le=1)


class FitScoreResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    fit_band: FitBand
    positive_reasons: list[str] = Field(default_factory=list)
    negative_reasons: list[str] = Field(default_factory=list)
    scorer_version: str


class DataSummaryResponse(BaseModel):
    ready: bool
    snapshot_version: str
    contract_count: int = Field(ge=0)
    agency_count: int = Field(ge=0)
    last_award_date: str | None = None
    supplier_identifiers: Literal["pseudonymised"] = "pseudonymised"


class AgentSource(BaseModel):
    document: str
    page: int = Field(ge=1)
    url: str
    section: str = ""


class AgentRequest(StrictRequest):
    question: str = Field(min_length=3, max_length=4_000)
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]{1,128}$")
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("context")
    @classmethod
    def validate_context_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            encoded = json.dumps(value, default=str)
        except (TypeError, ValueError) as exc:
            raise ValueError("context must be JSON serialisable") from exc
        if len(encoded.encode("utf-8")) > 64_000:
            raise ValueError("context must not exceed 64 KB")
        return value


class AgentResponse(BaseModel):
    session_id: str
    answer: str
    route: Literal["sql", "rag", "ml", "brief"]
    sources: list[AgentSource] = Field(default_factory=list)
    brief: str | None = None
    error: str | None = None
