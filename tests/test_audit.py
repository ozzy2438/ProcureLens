import json
from pathlib import Path

from procurelens.agent.audit import AuditLogger


def test_audit_log_is_jsonl_append_only_and_does_not_store_payload(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    secret = "analyst@example.gov.au"
    logger.log(
        session_id="session-1",
        actor="agent",
        step="guard_input",
        status="ok",
        tool=None,
        input_payload=secret,
        output_payload="safe",
    )
    logger.log(
        session_id="session-1",
        actor="agent",
        step="route",
        status="ok",
        tool=None,
        input_payload="safe",
        output_payload="rag",
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert len(records) == 2
    assert secret not in path.read_text(encoding="utf-8")
    assert records[0]["input_digest"]
    assert records[1]["step"] == "route"
    assert path.stat().st_mode & 0o077 == 0
