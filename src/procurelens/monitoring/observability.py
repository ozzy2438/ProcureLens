"""Privacy-preserving Langfuse traces for agent and tool execution."""

from __future__ import annotations

import hashlib
import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Protocol, cast

from procurelens.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _canonical(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def safe_fingerprint(value: Any) -> dict[str, Any]:
    """Represent sensitive content without retaining reconstructable text."""
    encoded = _canonical(value).encode("utf-8")
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
        "redacted": True,
    }


_SAFE_TELEMETRY_KEYS = {
    "sha256",
    "bytes",
    "redacted",
    "session_sha256",
    "environment",
    "release",
    "privacy",
    "status",
    "tool",
    "latency_ms",
    "source_count",
}


def _langfuse_mask(*, data: Any, **_kwargs: Any) -> dict[str, Any]:
    """Preserve approved metrics but hash any unexpected exporter payload."""
    if isinstance(data, dict) and set(data).issubset(_SAFE_TELEMETRY_KEYS):
        return data
    return safe_fingerprint(data)


def extract_usage(response: Any) -> dict[str, int]:
    """Normalise common LangChain/OpenAI token metadata without prompt content."""
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, Mapping):
        metadata = getattr(response, "response_metadata", None)
        usage = metadata.get("token_usage", {}) if isinstance(metadata, Mapping) else {}
    aliases = {
        "input_tokens": ("input_tokens", "prompt_tokens"),
        "output_tokens": ("output_tokens", "completion_tokens"),
        "total_tokens": ("total_tokens",),
    }
    normalised: dict[str, int] = {}
    for target, candidates in aliases.items():
        for candidate in candidates:
            value = usage.get(candidate) if isinstance(usage, Mapping) else None
            if isinstance(value, (int, float)):
                normalised[target] = max(int(value), 0)
                break
    if "total_tokens" not in normalised and normalised:
        normalised["total_tokens"] = normalised.get("input_tokens", 0) + normalised.get(
            "output_tokens", 0
        )
    return normalised


def calculate_cost(
    usage: Mapping[str, int], *, input_per_1k: float, output_per_1k: float
) -> dict[str, float]:
    """Calculate explicit per-generation cost using configured contractual rates."""
    input_cost = usage.get("input_tokens", 0) / 1_000 * max(input_per_1k, 0.0)
    output_cost = usage.get("output_tokens", 0) / 1_000 * max(output_per_1k, 0.0)
    return {
        "input": round(input_cost, 8),
        "output": round(output_cost, 8),
        "total": round(input_cost + output_cost, 8),
    }


class Observation(Protocol):
    def update(self, **kwargs: Any) -> Any: ...


class ObservationClient(Protocol):
    def start_as_current_observation(self, **kwargs: Any) -> Any: ...

    def flush(self) -> None: ...

    def shutdown(self) -> None: ...


@dataclass
class TraceHandle:
    observation: Observation | None

    def complete(self, output: Any, *, status: str = "ok") -> None:
        if self.observation is not None:
            self.observation.update(
                output=safe_fingerprint(output),
                metadata={"status": status},
                level="ERROR" if status == "error" else "DEFAULT",
            )


class SafeLangfuseObserver:
    """Emit Langfuse observations containing metrics and hashes, never payload bodies."""

    def __init__(
        self,
        client: ObservationClient | None = None,
        *,
        enabled: bool = False,
        environment: str = "dev",
        release: str = "local",
    ) -> None:
        self.client = client
        self.enabled = bool(enabled and client is not None)
        self.environment = environment
        self.release = release

    @contextmanager
    def trace(self, *, session_id: str, input_payload: Any) -> Iterator[TraceHandle]:
        if not self.enabled or self.client is None:
            yield TraceHandle(None)
            return
        metadata = {
            "session_sha256": safe_fingerprint(session_id)["sha256"],
            "environment": self.environment,
            "release": self.release,
            "privacy": "sha256-only",
        }
        try:
            manager = self.client.start_as_current_observation(
                name="bid-intelligence-agent",
                as_type="agent",
                input=safe_fingerprint(input_payload),
                metadata=metadata,
                version=self.release,
            )
        except Exception:
            logger.exception("Langfuse trace creation failed; agent execution continues")
            yield TraceHandle(None)
            return
        with manager as observation:
            yield TraceHandle(observation)

    def record_step(
        self,
        *,
        step: str,
        status: str,
        input_payload: Any,
        output_payload: Any,
        tool: str | None = None,
        latency_ms: int | None = None,
        source_count: int = 0,
        model: str | None = None,
        usage: Mapping[str, int] | None = None,
        cost: Mapping[str, float] | None = None,
    ) -> None:
        if not self.enabled or self.client is None:
            return
        observation_type = "generation" if model else _observation_type(step, tool)
        metadata = {
            "status": status,
            "tool": tool,
            "latency_ms": latency_ms,
            "source_count": source_count,
            "privacy": "sha256-only",
        }
        try:
            with self.client.start_as_current_observation(
                name=step,
                as_type=observation_type,
                input=safe_fingerprint(input_payload),
                output=safe_fingerprint(output_payload),
                metadata=metadata,
                level="ERROR" if status in {"error", "blocked"} else "DEFAULT",
                model=model,
                usage_details=dict(usage or {}),
                cost_details=dict(cost or {}),
            ):
                pass
        except Exception:
            logger.exception("Langfuse step emission failed; agent execution continues")

    def flush(self) -> None:
        if self.enabled and self.client is not None:
            self.client.flush()

    def shutdown(self) -> None:
        if self.enabled and self.client is not None:
            self.client.shutdown()


def _observation_type(step: str, tool: str | None) -> str:
    if step == "guard_input":
        return "guardrail"
    if tool == "rag":
        return "retriever"
    if tool is not None:
        return "tool"
    return "span"


def build_observer(settings: Settings | None = None) -> SafeLangfuseObserver:
    """Create an optional Langfuse SDK client from explicit safe settings."""
    settings = settings or get_settings()
    if not settings.langfuse_tracing_enabled:
        return SafeLangfuseObserver()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning("Langfuse tracing requested without credentials; tracing disabled")
        return SafeLangfuseObserver()
    from langfuse import Langfuse

    client = Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        base_url=settings.langfuse_host,
        tracing_enabled=True,
        sample_rate=settings.langfuse_sample_rate,
        environment=settings.env,
        release=settings.langfuse_release,
        mask=_langfuse_mask,
        blocked_instrumentation_scopes=["sqlalchemy", "psycopg"],
    )
    return SafeLangfuseObserver(
        cast(ObservationClient, client),
        enabled=True,
        environment=settings.env,
        release=settings.langfuse_release,
    )
