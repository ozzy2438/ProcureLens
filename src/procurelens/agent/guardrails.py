"""PII redaction + prompt-injection defences applied to all LLM inputs/outputs.

Primary engine: Microsoft Presidio (lazy import). A regex fallback covers
common Australian identifiers so the guardrail degrades safely if Presidio
is unavailable.
"""
from __future__ import annotations

import re

_FALLBACK_PATTERNS = {
    "EMAIL": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "AU_PHONE": re.compile(r"(?:\+61|0)[2-478](?:[ -]?\d){8}"),
    "AU_ABN": re.compile(r"\b\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3}\b"),
    "AU_TFN": re.compile(r"\b\d{3}[ ]?\d{3}[ ]?\d{3}\b"),
}

INJECTION_MARKERS = (
    "ignore previous instructions",
    "disregard your system prompt",
    "you are now",
)


def redact(text: str) -> str:
    """Redact PII. Presidio if available, regex fallback otherwise."""
    try:
        return _redact_presidio(text)
    except ImportError:
        return redact_fallback(text)


def redact_fallback(text: str) -> str:
    for label, pattern in _FALLBACK_PATTERNS.items():
        text = pattern.sub(f"<{label}>", text)
    return text


def _redact_presidio(text: str) -> str:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine

    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()
    results = analyzer.analyze(text=text, language="en")
    return anonymizer.anonymize(text=text, analyzer_results=results).text


def flag_injection(text: str) -> bool:
    """Heuristic prompt-injection detector for tool outputs and user input."""
    lowered = text.lower()
    return any(marker in lowered for marker in INJECTION_MARKERS)
