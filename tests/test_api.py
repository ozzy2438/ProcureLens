from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from procurelens.agent.graph import AgentResult
from procurelens.api.main import create_app
from procurelens.api.predictors import AmendmentPrediction, DriverValue
from procurelens.models.train_fit_scorer import WeightedFitScorer, load_capability_profile


class FakeAmendmentPredictor:
    model_version = "7"

    def predict(self, records: list[dict]) -> list[AmendmentPrediction]:
        return [
            AmendmentPrediction(
                probability=0.42,
                risk_band="high",
                model_version=self.model_version,
                top_drivers=[
                    DriverValue(
                        feature="award_value_aud",
                        impact=0.31,
                        direction="increases_risk",
                    )
                ],
            )
            for _ in records
        ]


class FakeBidAgent:
    version = "test-agent"

    def __init__(self) -> None:
        self.dependencies = SimpleNamespace(
            sql_tool=SimpleNamespace(
                execute=lambda _query: SimpleNamespace(
                    rows=[
                        {
                            "contract_count": 445_029,
                            "agency_count": 151,
                            "last_award_date": "2025-12-31T00:00:00+00:00",
                        }
                    ]
                )
            ),
            observer=None,
        )

    def invoke(self, *, question: str, session_id: str, context: dict) -> AgentResult:
        return AgentResult(
            session_id=session_id,
            answer=f"Grounded answer for: {question}",
            route="rag",
            sources=[
                {
                    "document": "Commonwealth Procurement Rules — 17 November 2025",
                    "page": 12,
                    "url": "https://www.finance.gov.au/cpr.pdf",
                    "section": "Value for money",
                }
            ],
            brief=None,
            error=None,
        )


def _fit_scorer() -> WeightedFitScorer:
    return WeightedFitScorer(load_capability_profile())


def _amendment_payload() -> dict:
    return {
        "agency": "Department of Finance",
        "unspsc_category": "81110000",
        "procurement_method": "open",
        "contract_value_aud": 250_000,
        "contract_duration_days": 365,
        "award_date": "2026-06-15",
    }


def test_champion_loads_once_at_application_startup():
    loads = 0

    def loader() -> FakeAmendmentPredictor:
        nonlocal loads
        loads += 1
        return FakeAmendmentPredictor()

    application = create_app(amendment_loader=loader, fit_loader=_fit_scorer)
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        assert client.post("/predict/amendment-risk", json=_amendment_payload()).status_code == 200
        assert client.post("/predict/amendment-risk", json=_amendment_payload()).status_code == 200
    assert loads == 1


def test_health_reports_model_readiness_and_versions():
    application = create_app(
        amendment_loader=FakeAmendmentPredictor,
        fit_loader=_fit_scorer,
        agent_loader=FakeBidAgent,
    )
    with TestClient(application) as client:
        body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["models"]["amendment_risk"] == {
        "ready": True,
        "version": "7",
        "error": None,
    }
    assert body["models"]["fit_scorer"]["version"] == "1.0.0"
    assert body["observability"] == {
        "provider": "langfuse",
        "enabled": False,
        "privacy": "sha256-only",
    }


def test_liveness_readiness_and_data_summary_contracts():
    application = create_app(
        amendment_loader=FakeAmendmentPredictor,
        fit_loader=_fit_scorer,
        agent_loader=FakeBidAgent,
    )
    with TestClient(application) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        summary = client.get("/data/summary")
    assert live.status_code == 200
    assert live.json()["release_version"] == "1.0.0"
    assert ready.status_code == 200
    assert ready.json()["data"]["contract_count"] == 445_029
    assert summary.json() == {
        "ready": True,
        "snapshot_version": "1.0.0",
        "contract_count": 445_029,
        "agency_count": 151,
        "last_award_date": "2025-12-31T00:00:00+00:00",
        "supplier_identifiers": "pseudonymised",
    }


def test_readiness_is_503_when_release_snapshot_is_missing():
    class AgentWithoutData:
        version = "test-agent"

    application = create_app(
        amendment_loader=FakeAmendmentPredictor,
        fit_loader=_fit_scorer,
        agent_loader=AgentWithoutData,
    )
    with TestClient(application) as client:
        ready = client.get("/health/ready")
        summary = client.get("/data/summary")
    assert ready.status_code == 503
    assert ready.json()["detail"]["data"]["ready"] is False
    assert summary.status_code == 503
    assert summary.json()["detail"]["code"] == "data_unavailable"


def test_amendment_risk_response_is_real_model_contract():
    application = create_app(
        amendment_loader=FakeAmendmentPredictor,
        fit_loader=_fit_scorer,
    )
    with TestClient(application) as client:
        response = client.post("/predict/amendment-risk", json=_amendment_payload())
    assert response.status_code == 200
    assert response.json() == {
        "probability": 0.42,
        "risk_band": "high",
        "model_version": "7",
        "top_drivers": [
            {
                "feature": "award_value_aud",
                "impact": 0.31,
                "direction": "increases_risk",
            }
        ],
    }


def test_mlflow_unavailable_returns_controlled_503():
    def unavailable_loader():
        raise ConnectionError("secret internal endpoint details")

    application = create_app(amendment_loader=unavailable_loader, fit_loader=_fit_scorer)
    with TestClient(application) as client:
        health = client.get("/health").json()
        response = client.post("/predict/amendment-risk", json=_amendment_payload())
    assert health["status"] == "degraded"
    assert health["models"]["amendment_risk"]["ready"] is False
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "model_unavailable"
    assert "secret internal" not in response.text


def test_batch_prediction_preserves_order_and_version():
    application = create_app(
        amendment_loader=FakeAmendmentPredictor,
        fit_loader=_fit_scorer,
    )
    with TestClient(application) as client:
        response = client.post(
            "/predict/amendment-risk/batch",
            json={"items": [_amendment_payload(), _amendment_payload()]},
        )
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert response.json()["model_version"] == "7"
    assert len(response.json()["predictions"]) == 2


def test_batch_prediction_rejects_empty_or_oversized_payloads():
    application = create_app(
        amendment_loader=FakeAmendmentPredictor,
        fit_loader=_fit_scorer,
    )
    with TestClient(application) as client:
        assert client.post("/predict/amendment-risk/batch", json={"items": []}).status_code == 422
        oversized = [_amendment_payload() for _ in range(101)]
        assert (
            client.post("/predict/amendment-risk/batch", json={"items": oversized}).status_code
            == 422
        )


def test_amendment_request_rejects_unknown_fields_and_methods():
    application = create_app(
        amendment_loader=FakeAmendmentPredictor,
        fit_loader=_fit_scorer,
    )
    bad_method = {**_amendment_payload(), "procurement_method": "sole-mate"}
    extra_field = {**_amendment_payload(), "future_outcome": True}
    with TestClient(application) as client:
        assert client.post("/predict/amendment-risk", json=bad_method).status_code == 422
        assert client.post("/predict/amendment-risk", json=extra_field).status_code == 422


def test_fit_score_endpoint_returns_explainable_ranking():
    application = create_app(
        amendment_loader=FakeAmendmentPredictor,
        fit_loader=_fit_scorer,
    )
    payload = {
        "tender_id": "ATM-001",
        "unspsc_category": "81110000",
        "agency": "Department of Finance",
        "estimated_value_aud": 750_000,
        "procurement_method": "open",
        "tender_title": "Responsible AI and machine learning advisory",
        "tender_description": "Build a data platform with MLOps and data governance",
        "as_of_date": "2026-08-07",
        "close_date": "2026-09-15",
        "agency_recent_tech_spend_aud": 80_000_000,
        "agency_familiarity_count": 2,
        "supplier_hhi": 0.2,
    }
    with TestClient(application) as client:
        response = client.post("/predict/fit-score", json=payload)
    body = response.json()
    assert response.status_code == 200
    assert 0 <= body["score"] <= 100
    assert body["fit_band"] in {"strong_fit", "review", "low_fit"}
    assert body["positive_reasons"]
    assert body["negative_reasons"]
    assert body["scorer_version"] == "1.0.0"


def test_agent_endpoint_returns_routing_and_citation_contract():
    application = create_app(
        amendment_loader=FakeAmendmentPredictor,
        fit_loader=_fit_scorer,
        agent_loader=FakeBidAgent,
    )
    with TestClient(application) as client:
        response = client.post(
            "/agent/query",
            json={
                "question": "What do the CPRs say about value for money?",
                "session_id": "api-agent-session",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "rag"
    assert body["sources"][0]["page"] == 12
    assert body["session_id"] == "api-agent-session"
