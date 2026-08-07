"""Privacy-preserving, append-only JSONL audit records for agent steps."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_WRITE_LOCK = threading.Lock()


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditRecord:
    ts: str
    session_id: str
    actor: str
    step: str
    status: str
    tool: str | None
    input_digest: str
    output_digest: str
    sources: list[str] = field(default_factory=list)
    model: str | None = None
    latency_ms: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AuditLogger:
    """Write one complete JSON object per line without retaining prompt bodies."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def log(
        self,
        *,
        session_id: str,
        actor: str,
        step: str,
        status: str,
        input_payload: str,
        output_payload: str = "",
        tool: str | None = None,
        sources: list[str] | None = None,
        model: str | None = None,
        latency_ms: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            ts=datetime.now(timezone.utc).isoformat(),
            session_id=session_id,
            actor=actor,
            step=step,
            status=status,
            tool=tool,
            input_digest=_digest(input_payload),
            output_digest=_digest(output_payload),
            sources=sources or [],
            model=model,
            latency_ms=latency_ms,
            metadata=metadata or {},
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n").encode()
        with _WRITE_LOCK:
            descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                os.write(descriptor, encoded)
            finally:
                os.close(descriptor)
        return record


def audit_event(
    path: str,
    session_id: str,
    step: str,
    tool: str | None,
    payload: str,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Backward-compatible facade for callers created during the initial scaffold."""
    record = AuditLogger(path).log(
        session_id=session_id,
        actor="agent",
        step=step,
        status="ok",
        tool=tool,
        input_payload=payload,
        sources=sources,
    )
    return asdict(record)
