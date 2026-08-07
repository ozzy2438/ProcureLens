"""Offline Docker smoke for Langfuse instrumentation and Evidently drift."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from procurelens.monitoring.drift import DriftSummary, build_drift_report
from procurelens.monitoring.observability import SafeLangfuseObserver, _langfuse_mask


def run_langfuse_smoke(output_path: str | Path) -> dict[str, Any]:
    """Create real Langfuse SDK spans in memory and prove payload privacy."""
    from langfuse import Langfuse
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    client = Langfuse(
        # Langfuse caches clients by public key; isolate repeated test/smoke runs.
        public_key=f"pk-procurelens-smoke-{uuid4().hex}",
        secret_key="procurelens-smoke-secret",
        base_url="http://127.0.0.1:9",
        tracing_enabled=True,
        tracer_provider=tracer_provider,
        span_exporter=exporter,
        mask=_langfuse_mask,
        environment="test",
        release="week-5-smoke",
    )
    observer = SafeLangfuseObserver(
        client,  # type: ignore[arg-type]
        enabled=True,
        environment="test",
        release="week-5-smoke",
    )
    sensitive = "Email analyst@example.gov.au about the confidential bid"
    with observer.trace(session_id="private-session", input_payload=sensitive) as trace:
        observer.record_step(
            step="tool_ml",
            status="ok",
            tool="ml",
            input_payload=sensitive,
            output_payload={"probability": 0.21},
            latency_ms=12,
        )
        observer.record_step(
            step="llm_response",
            status="ok",
            input_payload=sensitive,
            output_payload={"answer": "redacted"},
            latency_ms=8,
            model="gpt-4o-mini",
            usage={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150},
            cost={"input": 0.000018, "output": 0.000018, "total": 0.000036},
        )
        trace.complete({"route": "ml", "status": "ok"})
    observer.flush()
    spans = exporter.get_finished_spans()
    records = [
        {"name": span.name, "attributes": dict(span.attributes or {})} for span in spans
    ]
    serialised = json.dumps(records, ensure_ascii=False, sort_keys=True, default=str)
    names = {record["name"] for record in records}
    observation_types = {
        str(span.attributes.get("langfuse.observation.type"))
        for span in spans
        if span.attributes is not None
    }
    privacy_verified = sensitive not in serialised and "analyst@example.gov.au" not in serialised
    requirements_met = (
        {"bid-intelligence-agent", "tool_ml", "llm_response"}.issubset(names)
        and {"agent", "tool", "generation"}.issubset(observation_types)
        and privacy_verified
        and "langfuse.observation.usage_details" in serialised
        and "langfuse.observation.cost_details" in serialised
        and "langfuse.observation.metadata.latency_ms" in serialised
    )
    observer.shutdown()
    if not requirements_met:
        raise RuntimeError("Langfuse smoke trace failed privacy or telemetry checks")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(records, indent=2, default=str) + "\n", encoding="utf-8")
    return {
        "span_count": len(records),
        "span_names": sorted(names),
        "privacy_verified": privacy_verified,
        "tool_call_verified": "tool" in observation_types,
        "generation_verified": "generation" in observation_types,
        "token_usage_verified": True,
        "cost_verified": True,
        "latency_verified": True,
        "output_path": str(output),
    }


def _drift_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(42)
    size = 300
    reference = pd.DataFrame(
        {
            "award_value_aud": rng.lognormal(12, 0.5, size),
            "contract_duration_days": rng.normal(365, 30, size),
            "procurement_method": ["open"] * size,
            "prediction": rng.beta(2, 8, size),
        }
    )
    current = pd.DataFrame(
        {
            "award_value_aud": rng.lognormal(14, 0.5, size),
            "contract_duration_days": rng.normal(800, 30, size),
            "procurement_method": ["limited"] * size,
            "prediction": rng.beta(8, 2, size),
        }
    )
    return reference, current


def run_drift_smoke(output_dir: str | Path) -> DriftSummary:
    """Generate deterministic reference/current batches and a real Evidently report."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    reference, current = _drift_frames()
    reference_path = destination / "reference.csv"
    current_path = destination / "current.csv"
    reference.to_csv(reference_path, index=False)
    current.to_csv(current_path, index=False)
    return build_drift_report(
        str(reference_path),
        str(current_path),
        str(destination / "drift-report.html"),
        out_json=str(destination / "drift-report.json"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="artifacts/monitoring-smoke")
    args = parser.parse_args(argv)
    destination = Path(args.output_dir)
    langfuse_summary = run_langfuse_smoke(destination / "langfuse-spans.json")
    drift_summary = run_drift_smoke(destination / "drift")
    summary = {
        "langfuse": langfuse_summary,
        "drift": drift_summary.to_dict(),
    }
    summary_path = destination / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
