"""Data / prediction drift reports (Evidently), published as HTML artefacts.

Run monthly alongside retraining; alert when PSI on key features > 0.2.
"""
from __future__ import annotations


def build_drift_report(reference_path: str, current_path: str, out_html: str) -> None:
    # TODO(week-5)
    raise NotImplementedError
