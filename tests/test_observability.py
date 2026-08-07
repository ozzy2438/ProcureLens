from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from procurelens.agent.audit import AuditLogger
from procurelens.agent.graph import AgentDependencies, BidIntelligenceAgent
from procurelens.agent.tools.brief_tool import BidBriefTool
from procurelens.agent.tools.rag_tool import ProcurementRAGTool
from procurelens.monitoring.observability import (
    SafeLangfuseObserver,
    build_observer,
    calculate_cost,
    extract_usage,
    safe_fingerprint,
)


class FakeObservation:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


class FakeObservationManager:
    def __init__(self, observation: FakeObservation) -> None:
        self.observation = observation

    def __enter__(self) -> FakeObservation:
        return self.observation

    def __exit__(self, *_args: object) -> None:
        return None


class FakeLangfuseClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.observations: list[FakeObservation] = []
        self.flushed = False
        self.stopped = False

    def start_as_current_observation(self, **kwargs: Any) -> FakeObservationManager:
        self.calls.append(kwargs)
        observation = FakeObservation()
        self.observations.append(observation)
        return FakeObservationManager(observation)

    def flush(self) -> None:
        self.flushed = True

    def shutdown(self) -> None:
        self.stopped = True


class FakeSQLResult:
    def model_dump(self) -> dict[str, Any]:
        return {"rows": [], "columns": [], "row_count": 0, "truncated": False, "query": "SELECT"}


class FakeSQLTool:
    def answer_question(self, _question: str, _context: dict[str, Any]) -> FakeSQLResult:
        return FakeSQLResult()

    def close(self) -> None:
        return None


class FakeMLTool:
    def score_context(self, _context: dict[str, Any]) -> dict[str, Any]:
        return {"fit_score": {"score": 80}}

    def close(self) -> None:
        return None


def test_safe_fingerprint_is_stable_and_non_reconstructable():
    first = safe_fingerprint("analyst@example.gov.au")
    second = safe_fingerprint("analyst@example.gov.au")
    assert first == second
    assert first["redacted"] is True
    assert len(first["sha256"]) == 64
    assert "analyst" not in json.dumps(first)


def test_observer_records_latency_usage_and_cost_without_payload_text():
    client = FakeLangfuseClient()
    observer = SafeLangfuseObserver(client, enabled=True, environment="test", release="r5")
    secret_prompt = "Contact analyst@example.gov.au about the restricted bid"
    with observer.trace(session_id="session-private", input_payload=secret_prompt) as trace:
        observer.record_step(
            step="tool_ml",
            status="ok",
            tool="ml",
            input_payload=secret_prompt,
            output_payload={"probability": 0.2},
            latency_ms=17,
            model="gpt-test",
            usage={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
            cost={"input": 0.001, "output": 0.002, "total": 0.003},
        )
        trace.complete({"route": "ml"})
    serialised = json.dumps(client.calls, default=str)
    assert secret_prompt not in serialised
    assert "analyst@example.gov.au" not in serialised
    assert "session-private" not in serialised
    assert client.calls[0]["as_type"] == "agent"
    assert client.calls[1]["as_type"] == "generation"
    assert client.calls[1]["metadata"]["latency_ms"] == 17
    assert client.calls[1]["usage_details"]["total_tokens"] == 14
    assert client.calls[1]["cost_details"]["total"] == 0.003


def test_graph_emits_agent_retriever_and_guardrail_observations(tmp_path):
    client = FakeLangfuseClient()
    observer = SafeLangfuseObserver(client, enabled=True)
    dependencies = AgentDependencies(
        sql_tool=FakeSQLTool(),  # type: ignore[arg-type]
        rag_tool=ProcurementRAGTool("config/rag_corpus.json"),
        ml_tool=FakeMLTool(),  # type: ignore[arg-type]
        brief_tool=BidBriefTool(),
        audit=AuditLogger(tmp_path / "audit.jsonl"),
        observer=observer,
    )
    agent = BidIntelligenceAgent(dependencies)
    result = agent.invoke(
        question="What do the CPRs say about value for money?",
        session_id="safe-observer-test",
    )
    assert result.route == "rag"
    assert client.calls[0]["as_type"] == "agent"
    types = {call["as_type"] for call in client.calls[1:]}
    assert "guardrail" in types
    assert "retriever" in types
    agent.close()
    assert client.stopped is True


def test_usage_and_cost_normalisation_supports_common_response_shapes():
    direct = extract_usage(
        SimpleNamespace(
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
        )
    )
    nested = extract_usage(
        SimpleNamespace(
            usage_metadata=None,
            response_metadata={"token_usage": {"prompt_tokens": 50, "completion_tokens": 10}},
        )
    )
    assert direct == {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
    assert nested == {"input_tokens": 50, "output_tokens": 10, "total_tokens": 60}
    assert calculate_cost(direct, input_per_1k=0.01, output_per_1k=0.03) == {
        "input": 0.001,
        "output": 0.0006,
        "total": 0.0016,
    }


def test_disabled_or_misconfigured_observer_is_a_safe_noop():
    client = FakeLangfuseClient()
    observer = SafeLangfuseObserver(client, enabled=False)
    with observer.trace(session_id="x", input_payload="raw") as trace:
        trace.complete("output")
    observer.record_step(
        step="route",
        status="ok",
        input_payload="raw",
        output_payload="raw",
    )
    observer.flush()
    observer.shutdown()
    assert client.calls == []
    assert build_observer(
        SimpleNamespace(
            langfuse_tracing_enabled=True,
            langfuse_public_key="",
            langfuse_secret_key="",
        )
    ).enabled is False
