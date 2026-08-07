"""Pydantic request/response schemas for the model service."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AmendmentRiskRequest(BaseModel):
    agency: str
    unspsc_category: str
    procurement_method: str = Field(pattern="^(open|limited|prequalified)$")
    contract_value_aud: float = Field(gt=0)
    contract_duration_days: int = Field(gt=0)
    supplier_prior_contracts: int = 0
    supplier_prior_amendment_rate: float = Field(0.0, ge=0, le=1)


class AmendmentRiskResponse(BaseModel):
    probability: float = Field(ge=0, le=1)
    risk_band: str  # low / medium / high
    model_version: str
    top_drivers: list[str] = []


class FitScoreRequest(BaseModel):
    tender_id: str
    unspsc_category: str
    agency: str
    estimated_value_aud: float | None = None


class FitScoreResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    rationale: list[str] = []
    model_version: str
