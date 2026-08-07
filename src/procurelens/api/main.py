"""FastAPI model service.

Serves calibrated predictions from the MLflow 'champion' models.
Every response carries the model version for auditability.
"""
from __future__ import annotations

from fastapi import FastAPI

from procurelens.api.schemas import (
    AmendmentRiskRequest,
    AmendmentRiskResponse,
    FitScoreRequest,
    FitScoreResponse,
)

app = FastAPI(title="ProcureLens Model Service", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/predict/amendment-risk", response_model=AmendmentRiskResponse)
def predict_amendment_risk(req: AmendmentRiskRequest) -> AmendmentRiskResponse:
    # TODO(week-3): registry.load_champion + real inference + SHAP top drivers
    return AmendmentRiskResponse(
        probability=0.5, risk_band="medium", model_version="stub", top_drivers=[]
    )


@app.post("/predict/fit-score", response_model=FitScoreResponse)
def predict_fit_score(req: FitScoreRequest) -> FitScoreResponse:
    # TODO(week-3)
    return FitScoreResponse(score=50, rationale=["stub"], model_version="stub")
