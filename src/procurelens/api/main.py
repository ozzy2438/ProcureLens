"""FastAPI service for calibrated amendment risk and opportunity fit ranking."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any, cast
from uuid import uuid4

import pandas as pd
from fastapi import FastAPI, HTTPException, status

from procurelens.agent.graph import BidIntelligenceAgent
from procurelens.agent.guardrails import PromptInjectionError
from procurelens.api.predictors import AmendmentRiskPredictor
from procurelens.api.schemas import (
    AgentRequest,
    AgentResponse,
    AgentSource,
    AmendmentRiskBatchRequest,
    AmendmentRiskBatchResponse,
    AmendmentRiskRequest,
    AmendmentRiskResponse,
    DataSummaryResponse,
    FitBand,
    FitScoreRequest,
    FitScoreResponse,
    ShapDriver,
)
from procurelens.config import get_settings
from procurelens.models.train_fit_scorer import WeightedFitScorer, load_capability_profile

logger = logging.getLogger(__name__)


def _load_amendment_predictor() -> AmendmentRiskPredictor:
    return AmendmentRiskPredictor.from_registry(get_settings().mlflow_tracking_uri)


def _load_fit_scorer() -> WeightedFitScorer:
    return WeightedFitScorer(load_capability_profile())


def _load_bid_agent() -> BidIntelligenceAgent:
    return BidIntelligenceAgent()


def _unavailable(model_name: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": "model_unavailable",
            "model": model_name,
            "message": f"{model_name} is not ready; retry after its dependencies are restored",
        },
    )


def create_app(
    *,
    amendment_loader: Callable[[], Any] | None = None,
    fit_loader: Callable[[], Any] | None = None,
    agent_loader: Callable[[], Any] | None = None,
) -> FastAPI:
    """Create an application whose model dependencies load exactly once at startup."""
    amendment_loader = amendment_loader or _load_amendment_predictor
    fit_loader = fit_loader or _load_fit_scorer
    agent_loader = agent_loader or _load_bid_agent

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.amendment_predictor = None
        application.state.amendment_error = None
        application.state.fit_scorer = None
        application.state.fit_error = None
        application.state.bid_agent = None
        application.state.agent_error = None
        try:
            application.state.amendment_predictor = amendment_loader()
        except Exception:
            logger.exception("failed to load amendment-risk champion at startup")
            application.state.amendment_error = "registry champion could not be loaded"
        try:
            application.state.fit_scorer = fit_loader()
        except Exception:
            logger.exception("failed to load opportunity fit scorer at startup")
            application.state.fit_error = "capability profile could not be loaded"
        try:
            application.state.bid_agent = agent_loader()
        except Exception:
            logger.exception("failed to initialise bid intelligence agent at startup")
            application.state.agent_error = "agent dependencies could not be initialised"
        yield
        close_agent = getattr(application.state.bid_agent, "close", None)
        if callable(close_agent):
            close_agent()

    application = FastAPI(
        title="ProcureLens Model Service",
        version=get_settings().release_version,
        lifespan=lifespan,
    )

    def health_payload() -> dict[str, Any]:
        amendment = application.state.amendment_predictor
        fit_scorer = application.state.fit_scorer
        bid_agent = application.state.bid_agent
        observer = getattr(getattr(bid_agent, "dependencies", None), "observer", None)
        ready = amendment is not None and fit_scorer is not None and bid_agent is not None
        return {
            "status": "ok" if ready else "degraded",
            "release_version": get_settings().release_version,
            "models": {
                "amendment_risk": {
                    "ready": amendment is not None,
                    "version": getattr(amendment, "model_version", None),
                    "error": application.state.amendment_error,
                },
                "fit_scorer": {
                    "ready": fit_scorer is not None,
                    "version": getattr(fit_scorer, "version", None),
                    "error": application.state.fit_error,
                },
                "bid_agent": {
                    "ready": bid_agent is not None,
                    "version": getattr(bid_agent, "version", None),
                    "error": application.state.agent_error,
                },
            },
            "observability": {
                "provider": "langfuse",
                "enabled": bool(getattr(observer, "enabled", False)),
                "privacy": "sha256-only",
            },
        }

    def query_data_summary() -> DataSummaryResponse:
        bid_agent = application.state.bid_agent
        sql_tool = getattr(getattr(bid_agent, "dependencies", None), "sql_tool", None)
        if sql_tool is None:
            raise RuntimeError("SQL tool is unavailable")
        result = sql_tool.execute(
            """
            SELECT COALESCE(SUM(contracts_all_time), 0)::bigint AS contract_count,
                   COUNT(*)::integer AS agency_count,
                   MAX(last_award_date) AS last_award_date
            FROM analytics_marts.dim_agencies
            """
        )
        if not result.rows:
            raise RuntimeError("snapshot summary returned no rows")
        row = result.rows[0]
        contract_count = int(row.get("contract_count") or 0)
        agency_count = int(row.get("agency_count") or 0)
        if contract_count < 445_000:
            raise RuntimeError("snapshot is below the release row threshold")
        return DataSummaryResponse(
            ready=True,
            snapshot_version=get_settings().snapshot_version,
            contract_count=contract_count,
            agency_count=agency_count,
            last_award_date=(
                str(row["last_award_date"]) if row.get("last_award_date") is not None else None
            ),
        )

    @application.get("/health")
    def health() -> dict[str, Any]:
        return health_payload()

    @application.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "ok", "release_version": get_settings().release_version}

    @application.get("/health/ready")
    def health_ready() -> dict[str, Any]:
        payload = health_payload()
        if payload["status"] != "ok":
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=payload)
        try:
            data = query_data_summary()
        except Exception as exc:
            logger.warning("release snapshot readiness failed: %s", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    **payload,
                    "status": "degraded",
                    "data": {"ready": False, "error": "release snapshot is unavailable"},
                },
            ) from exc
        return {**payload, "data": data.model_dump()}

    @application.get("/data/summary", response_model=DataSummaryResponse)
    def data_summary() -> DataSummaryResponse:
        try:
            return query_data_summary()
        except Exception as exc:
            logger.warning("data summary failed: %s", type(exc).__name__)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "data_unavailable",
                    "message": "The versioned procurement snapshot is not ready.",
                },
            ) from exc

    def run_amendment_predictions(
        requests: list[AmendmentRiskRequest],
    ) -> list[AmendmentRiskResponse]:
        predictor = application.state.amendment_predictor
        if predictor is None:
            raise _unavailable("amendment_risk")
        try:
            predictions = predictor.predict([request.model_dump() for request in requests])
        except Exception as exc:
            logger.exception("amendment-risk inference failed")
            raise _unavailable("amendment_risk") from exc
        return [
            AmendmentRiskResponse(
                probability=prediction.probability,
                risk_band=prediction.risk_band,
                model_version=prediction.model_version,
                top_drivers=[
                    ShapDriver(
                        feature=driver.feature,
                        impact=driver.impact,
                        direction=driver.direction,
                    )
                    for driver in prediction.top_drivers
                ],
            )
            for prediction in predictions
        ]

    @application.post("/predict/amendment-risk", response_model=AmendmentRiskResponse)
    def predict_amendment_risk(request: AmendmentRiskRequest) -> AmendmentRiskResponse:
        return run_amendment_predictions([request])[0]

    @application.post(
        "/predict/amendment-risk/batch",
        response_model=AmendmentRiskBatchResponse,
    )
    def predict_amendment_risk_batch(
        request: AmendmentRiskBatchRequest,
    ) -> AmendmentRiskBatchResponse:
        predictions = run_amendment_predictions(request.items)
        return AmendmentRiskBatchResponse(
            predictions=predictions,
            model_version=predictions[0].model_version,
            count=len(predictions),
        )

    @application.post("/predict/fit-score", response_model=FitScoreResponse)
    def predict_fit_score(request: FitScoreRequest) -> FitScoreResponse:
        scorer = application.state.fit_scorer
        if scorer is None:
            raise _unavailable("fit_scorer")
        try:
            result = scorer.score_frame(pd.DataFrame([request.model_dump()])).iloc[0]
        except Exception as exc:
            logger.exception("opportunity fit scoring failed")
            raise _unavailable("fit_scorer") from exc
        return FitScoreResponse(
            score=int(result["fit_score"]),
            fit_band=cast(FitBand, str(result["fit_band"])),
            positive_reasons=list(result["positive_reasons"]),
            negative_reasons=list(result["negative_reasons"]),
            scorer_version=str(result["scorer_version"]),
        )

    @application.post("/agent/query", response_model=AgentResponse)
    def query_bid_agent(request: AgentRequest) -> AgentResponse:
        agent = application.state.bid_agent
        if agent is None:
            raise _unavailable("bid_agent")
        session_id = request.session_id or uuid4().hex
        try:
            result = agent.invoke(
                question=request.question,
                session_id=session_id,
                context=request.context,
            )
        except PromptInjectionError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "prompt_injection_detected",
                    "message": "The request contains unsafe instruction-like content.",
                },
            ) from exc
        except Exception as exc:
            logger.exception("bid intelligence agent failed")
            raise _unavailable("bid_agent") from exc
        return AgentResponse(
            session_id=result.session_id,
            answer=result.answer,
            route=cast(Any, result.route),
            sources=[AgentSource(**source) for source in result.sources],
            brief=result.brief,
            error=result.error,
        )

    return application


app = create_app()
