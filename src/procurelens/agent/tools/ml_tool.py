"""Typed agent adapter for the Amendment Risk and Opportunity Fit APIs."""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from procurelens.config import get_settings


class MLToolError(RuntimeError):
    """Controlled model-service failure exposed to the graph."""


class ProcurementMLTool:
    def __init__(
        self,
        base_url: str,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None

    def _post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(f"{self.base_url}{path}", json=dict(payload))
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise MLToolError(
                "model service is unavailable or returned an invalid response"
            ) from exc
        if not isinstance(body, dict):
            raise MLToolError("model service response must be a JSON object")
        return body

    def amendment_risk(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._post("/predict/amendment-risk", payload)

    def fit_score(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._post("/predict/fit-score", payload)

    def score_context(self, context: Mapping[str, Any]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        amendment_payload = context.get("amendment_risk")
        fit_payload = context.get("fit_score")
        if isinstance(amendment_payload, Mapping):
            output["amendment_risk"] = self.amendment_risk(amendment_payload)
        if isinstance(fit_payload, Mapping):
            output["fit_score"] = self.fit_score(fit_payload)
        if not output:
            raise MLToolError(
                "ML routing requires context.amendment_risk and/or context.fit_score payloads"
            )
        return output

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


def build_ml_tool(base_url: str | None = None) -> ProcurementMLTool:
    return ProcurementMLTool(base_url or get_settings().model_service_url)


def amendment_risk(payload: dict[str, Any]) -> dict[str, Any]:
    tool = build_ml_tool()
    try:
        return tool.amendment_risk(payload)
    finally:
        tool.close()


def fit_score(payload: dict[str, Any]) -> dict[str, Any]:
    tool = build_ml_tool()
    try:
        return tool.fit_score(payload)
    finally:
        tool.close()
