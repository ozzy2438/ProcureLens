"""Agent tool wrapper around the FastAPI model service."""
from __future__ import annotations

import httpx

API_BASE = "http://localhost:8000"


def amendment_risk(payload: dict) -> dict:
    resp = httpx.post(f"{API_BASE}/predict/amendment-risk", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fit_score(payload: dict) -> dict:
    resp = httpx.post(f"{API_BASE}/predict/fit-score", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()
