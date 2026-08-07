#!/usr/bin/env python3
"""Fail a release when secrets, personal identifiers or local paths are bundled."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dbt_packages",
    "dist",
    "htmlcov",
    "logs",
    "target",
}
BINARY_SUFFIXES = {".dump", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".pyc"}
PATTERNS = {
    "macOS absolute user path": re.compile(rb"/Users/[A-Za-z0-9._-]+/"),
    "Linux absolute home path": re.compile(rb"/home/[A-Za-z0-9._-]+/"),
    "Windows absolute user path": re.compile(rb"[A-Za-z]:\\\\Users\\\\[^\\\\]+"),
    "operator commit email": re.compile(
        b"15340" + b"@" + rb"coderacademy\.edu\.au", re.IGNORECASE
    ),
    "OpenAI-style secret": re.compile(rb"sk-[A-Za-z0-9_-]{12,}"),
    "AWS access key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(rb"BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY"),
    "GitHub token": re.compile(rb"gh[opusr]_[A-Za-z0-9]{20,}"),
}


def candidates(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if path.is_dir() or any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.name == ".env" or path.suffix.lower() in BINARY_SUFFIXES:
            continue
        paths.append(path)
    return paths


def scan(root: Path) -> list[str]:
    failures: list[str] = []
    if (root / ".env").exists():
        failures.append(".env must not be present in a release package")

    for path in candidates(root):
        try:
            payload = path.read_bytes()
        except OSError as exc:
            failures.append(f"could not read {path.relative_to(root)}: {exc}")
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(payload):
                failures.append(f"{label}: {path.relative_to(root)}")

    mlflow_db = root / "mlruns/mlflow.db"
    if mlflow_db.exists():
        payload = mlflow_db.read_bytes()
        for label, pattern in PATTERNS.items():
            if pattern.search(payload):
                failures.append(f"{label}: mlruns/mlflow.db")

    if (root / ".git").exists():
        tracked_env = subprocess.run(
            ["git", "ls-files", ".env"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        if tracked_env:
            failures.append(".env is tracked by git")

    manifest_path = root / "data/snapshots/procurelens-marts-v1.0.0.manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        privacy = manifest.get("privacy", {})
        if privacy.get("raw_release_payloads_included") is not False:
            failures.append("snapshot manifest does not exclude raw release payloads")
        if manifest.get("contract_rows") != 445_029:
            failures.append("snapshot manifest does not identify the 445,029-row release cohort")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    failures = scan(root)
    if failures:
        print("Release privacy/security audit: FAIL", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(f"Release privacy/security audit: PASS ({root})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
