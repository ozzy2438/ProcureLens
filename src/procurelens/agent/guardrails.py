"""PII redaction and prompt-injection controls for every LLM boundary."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)
_presidio_disabled = False

_FALLBACK_PATTERNS = {
    "EMAIL": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+", re.IGNORECASE),
    "AU_PHONE_NUMBER": re.compile(r"(?<!\d)(?:\+?61|0)[2-478](?:[ -]?\d){8}(?!\d)"),
    # Context is mandatory for Australian tax identifiers. Bare 9/11-digit
    # values are common contract amounts and must not be corrupted as PII.
    "AU_ABN": re.compile(
        r"\b(?:ABN|Australian Business Number)(?:\s+is)?\s*[:#-]?\s*"
        r"\d{2}[ ]?\d{3}[ ]?\d{3}[ ]?\d{3}(?!\d)",
        re.IGNORECASE,
    ),
    "AU_TFN": re.compile(
        r"\b(?:TFN|Tax File Number)(?:\s+is)?\s*[:#-]?\s*"
        r"\d{3}[ ]?\d{3}[ ]?\d{3}(?!\d)",
        re.IGNORECASE,
    ),
    "CREDIT_CARD": re.compile(r"(?<![\d.])(?:\d[ -]*?){13,16}(?!\d)"),
}
_PRESIDIO_ENTITIES = [
    "CREDIT_CARD",
    "EMAIL_ADDRESS",
    "IBAN_CODE",
    "IP_ADDRESS",
]

_INJECTION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b",
        r"\bdisregard\s+(?:the\s+)?(?:system|developer|previous|prior)\b",
        r"\breveal\s+(?:the\s+)?(?:system\s+prompt|secrets?|credentials?|api\s+keys?)\b",
        r"\b(?:system|developer)\s+(?:prompt|message|instructions?)\s*:",
        r"\byou\s+are\s+now\b",
        r"\bact\s+as\s+(?:an?\s+)?(?:unrestricted|jailbroken)\b",
        r"<\s*/?\s*(?:script|system|developer)\b",
        r"\bexecute\s+(?:this|the following)\s+(?:command|sql|code)\b",
    )
)


class PromptInjectionError(ValueError):
    """Raised when untrusted content attempts to influence agent instructions."""


@dataclass(frozen=True)
class GuardedText:
    text: str
    pii_redacted: bool
    injection_detected: bool


@lru_cache(maxsize=1)
def _presidio_engines() -> tuple[object, object]:
    """Build pattern-based Presidio engines once without downloading an NLP model."""
    from presidio_analyzer import AnalyzerEngine
    from presidio_analyzer.nlp_engine import NoOpNlpEngine
    from presidio_anonymizer import AnonymizerEngine

    nlp_engine = NoOpNlpEngine(models=[{"lang_code": "en", "model_name": ""}])
    nlp_engine.load()
    return (
        AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"]),
        AnonymizerEngine(),
    )


def redact(text: str) -> str:
    """Redact PII with Presidio and safely degrade to AU-specific patterns."""
    global _presidio_disabled
    fallback_redacted = redact_fallback(text)
    if _presidio_disabled:
        return fallback_redacted
    try:
        analyzer, anonymizer = _presidio_engines()
        results = analyzer.analyze(  # type: ignore[attr-defined]
            text=fallback_redacted,
            language="en",
            entities=_PRESIDIO_ENTITIES,
        )
        return anonymizer.anonymize(  # type: ignore[attr-defined]
            text=fallback_redacted,
            analyzer_results=results,
        ).text
    except Exception as exc:  # Presidio can be installed without an NLP model.
        _presidio_disabled = True
        logger.info(
            "Presidio unavailable; using deterministic PII fallback: %s",
            type(exc).__name__,
        )
        return fallback_redacted


def redact_fallback(text: str) -> str:
    """Redact common Australian identifiers without external model downloads."""
    redacted = text
    for label, pattern in _FALLBACK_PATTERNS.items():
        redacted = pattern.sub(f"<{label}>", redacted)
    return redacted


def flag_injection(text: str) -> bool:
    """Detect instruction overrides in user input and retrieved/tool content."""
    normalised = unicodedata.normalize("NFKC", text)
    return any(pattern.search(normalised) for pattern in _INJECTION_PATTERNS)


def guard_text(text: str, *, reject_injection: bool = True) -> GuardedText:
    """Apply injection detection before PII redaction at an LLM boundary."""
    injection_detected = flag_injection(text)
    if injection_detected and reject_injection:
        raise PromptInjectionError("potential prompt injection detected")
    safe_text = redact(text)
    return GuardedText(
        text=safe_text,
        pii_redacted=safe_text != text,
        injection_detected=injection_detected,
    )
