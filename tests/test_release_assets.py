from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data/snapshots/procurelens-marts-v1.0.0.dump"


def test_demo_catalogue_is_versioned_and_honest() -> None:
    catalogue = json.loads((ROOT / "config/demo_opportunities.json").read_text())

    assert catalogue["version"] == "1.0.0"
    assert catalogue["dataset"]["contract_count"] == 445_029
    assert "not live AusTender listings" in catalogue["disclaimer"]
    assert len(catalogue["opportunities"]) >= 6
    assert all(item["tender_id"].startswith("DEMO-") for item in catalogue["opportunities"])
    assert all(item["source_url"].startswith("https://") for item in catalogue["opportunities"])


def test_release_snapshot_matches_manifest_and_checksum() -> None:
    manifest = json.loads(
        (ROOT / "data/snapshots/procurelens-marts-v1.0.0.manifest.json").read_text()
    )
    expected_hash = (
        (ROOT / "data/snapshots/procurelens-marts-v1.0.0.dump.sha256")
        .read_text()
        .split()[0]
    )

    digest = hashlib.sha256()
    with SNAPSHOT.open("rb") as archive:
        for block in iter(lambda: archive.read(1024 * 1024), b""):
            digest.update(block)

    assert SNAPSHOT.stat().st_size == manifest["archive_bytes"]
    assert digest.hexdigest() == manifest["sha256"] == expected_hash
    assert manifest["contract_rows"] == 445_029
    assert manifest["privacy"]["raw_release_payloads_included"] is False
    assert manifest["privacy"]["supplier_identifiers"] == "deterministically pseudonymised"


def test_snapshot_restore_has_integrity_and_atomicity_guards() -> None:
    script = (ROOT / "scripts/restore_snapshot.sh").read_text()
    package_script = (ROOT / "scripts/package_release.sh").read_text()

    assert "sha256sum --check" in script
    assert "SNAPSHOT_EXPECTED_ROWS:-445029" in script
    assert "begin;" in script and "commit;" in script
    assert "alter schema ${snapshot_schema} rename to ${target_schema}" in script
    assert "grant select on all tables" in script
    assert "--exclude '/artifacts/'" in package_script
    assert "scripts/sanitize_mlflow_registry.py" in package_script
    assert "mlruns/artifacts" not in package_script


def test_azure_template_has_release_safety_controls() -> None:
    template = (ROOT / "deploy/azure/main.bicep").read_text()

    assert "activeRevisionsMode: 'Multiple'" in template
    assert "path: '/health/live'" in template
    assert "path: '/health/ready'" in template
    assert "@secure()\nparam databaseUrl" in template
    assert "secretRef: 'agent-database-url'" in template
    assert "imageTag string = 'v1.0.0'" in template
    assert ":latest" not in template
