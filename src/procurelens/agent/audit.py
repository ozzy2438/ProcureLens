"""Structured audit trail: every agent step is an append-only JSONL record.

Record shape:
{ts, session_id, actor, step, tool, input_digest, sources, model, latency_ms}
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone


def audit_event(path: str, session_id: str, step: str, tool: str | None,
                payload: str, sources: list[str] | None = None) -> dict:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "step": step,
        "tool": tool,
        "input_digest": hashlib.sha256(payload.encode()).hexdigest()[:16],
        "sources": sources or [],
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return record
