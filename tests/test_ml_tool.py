import httpx
import pytest

from procurelens.agent.tools.ml_tool import MLToolError, ProcurementMLTool


def test_ml_tool_calls_both_model_api_contracts():
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("fit-score"):
            return httpx.Response(200, json={"score": 81, "scorer_version": "1.0.0"})
        return httpx.Response(200, json={"probability": 0.2, "model_version": "3"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    tool = ProcurementMLTool("http://model-service", client=client)
    result = tool.score_context(
        {
            "fit_score": {"tender_id": "ATM-1"},
            "amendment_risk": {"agency": "Finance"},
        }
    )

    assert result["fit_score"]["score"] == 81
    assert result["amendment_risk"]["model_version"] == "3"
    assert paths == ["/predict/amendment-risk", "/predict/fit-score"]


def test_ml_tool_converts_http_failure_to_controlled_error():
    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(503, json={"detail": "down"}))
    )
    tool = ProcurementMLTool("http://model-service", client=client)
    with pytest.raises(MLToolError, match="model service is unavailable"):
        tool.fit_score({"tender_id": "ATM-1"})
