"""MLflow registry loading and guarded champion-promotion helpers."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Callable, Mapping

DEFAULT_MAX_ECE = 0.05
REQUIRED_PROMOTION_METRICS = (
    "holdout_auc_roc",
    "holdout_brier_score",
    "holdout_ece",
)


@dataclass(frozen=True)
class LoadedModel:
    """A model plus immutable registry metadata needed by serving."""

    model: Any
    name: str
    alias: str
    version: str
    run_id: str


@dataclass(frozen=True)
class PromotionDecision:
    """Auditable outcome of a challenger/champion comparison."""

    accepted: bool
    reason: str
    challenger_version: str
    champion_version: str | None
    challenger_metrics: dict[str, float]
    champion_metrics: dict[str, float]


def load_model_alias(
    model_name: str,
    alias: str,
    *,
    tracking_uri: str | None = None,
    client: Any | None = None,
    model_loader: Callable[[str], Any] | None = None,
) -> LoadedModel:
    """Load an sklearn-flavour model and resolve its registry version once."""
    import mlflow
    import mlflow.sklearn
    from mlflow.tracking import MlflowClient

    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    registry_client = client or MlflowClient()
    version = registry_client.get_model_version_by_alias(model_name, alias)
    run_id = getattr(version, "run_id", None)
    if not run_id:
        raise RuntimeError(f"model {model_name}@{alias} has no source run")
    uri = f"models:/{model_name}@{alias}"
    loader = model_loader or mlflow.sklearn.load_model
    return LoadedModel(
        model=loader(uri),
        name=model_name,
        alias=alias,
        version=str(version.version),
        run_id=str(run_id),
    )


def load_champion(
    model_name: str,
    *,
    tracking_uri: str | None = None,
    client: Any | None = None,
    model_loader: Callable[[str], Any] | None = None,
) -> LoadedModel:
    """Load the model version assigned the ``champion`` alias."""
    return load_model_alias(
        model_name,
        "champion",
        tracking_uri=tracking_uri,
        client=client,
        model_loader=model_loader,
    )


def _validated_metrics(metrics: Mapping[str, float], label: str) -> dict[str, float]:
    values: dict[str, float] = {}
    for key in REQUIRED_PROMOTION_METRICS:
        if key not in metrics:
            raise ValueError(f"{label} is missing required metric {key}")
        value = float(metrics[key])
        if not isfinite(value):
            raise ValueError(f"{label} metric {key} is not finite")
        values[key] = value
    return values


def _is_missing_alias_error(exc: Exception) -> bool:
    error_code = str(getattr(exc, "error_code", "")).upper()
    message = str(exc).lower()
    return error_code == "RESOURCE_DOES_NOT_EXIST" or any(
        token in message for token in ("does not exist", "not found", "missing", "not set")
    )


def _log_promotion_decision(client: Any, run_id: str, decision: PromotionDecision) -> None:
    client.log_metric(run_id, "promotion_accepted", float(decision.accepted))
    for key, value in decision.challenger_metrics.items():
        client.log_metric(run_id, f"promotion_challenger_{key.removeprefix('holdout_')}", value)
    for key, value in decision.champion_metrics.items():
        client.log_metric(run_id, f"promotion_champion_{key.removeprefix('holdout_')}", value)
    client.set_tag(run_id, "promotion.reason", decision.reason)
    client.set_tag(run_id, "promotion.challenger_version", decision.challenger_version)
    client.set_tag(run_id, "promotion.champion_version", decision.champion_version or "none")


def promote_model_if_better(
    client: Any,
    *,
    model_name: str,
    challenger_version: str,
    challenger_run_id: str,
    challenger_metrics: Mapping[str, float],
    max_ece: float = DEFAULT_MAX_ECE,
) -> PromotionDecision:
    """Promote only when ranking does not regress and calibration stays safe.

    The challenger alias is updated for every successfully registered candidate.
    The champion alias changes only after metrics and the audit record have been
    validated and written.
    """
    if not 0 <= max_ece <= 1:
        raise ValueError("max_ece must be between 0 and 1")
    candidate = _validated_metrics(challenger_metrics, "challenger")
    client.set_registered_model_alias(model_name, "challenger", challenger_version)

    champion = None
    try:
        champion = client.get_model_version_by_alias(model_name, "champion")
    except Exception as exc:
        if not _is_missing_alias_error(exc):
            raise

    champion_version = str(champion.version) if champion is not None else None
    incumbent: dict[str, float] = {}
    if champion is not None:
        champion_run_id = getattr(champion, "run_id", None)
        if not champion_run_id:
            raise RuntimeError("champion model version has no source run")
        champion_run = client.get_run(champion_run_id)
        incumbent = _validated_metrics(champion_run.data.metrics, "champion")

    checks = {
        "ece_within_threshold": candidate["holdout_ece"] <= max_ece,
        "auc_not_lower": (
            not incumbent
            or candidate["holdout_auc_roc"] >= incumbent["holdout_auc_roc"]
        ),
        "brier_not_worse": (
            not incumbent
            or candidate["holdout_brier_score"] <= incumbent["holdout_brier_score"]
        ),
    }
    accepted = all(checks.values())
    failed_checks = [name for name, passed in checks.items() if not passed]
    reason = "accepted: all promotion gates passed" if accepted else (
        "rejected: " + ", ".join(failed_checks)
    )
    decision = PromotionDecision(
        accepted=accepted,
        reason=reason,
        challenger_version=str(challenger_version),
        champion_version=champion_version,
        challenger_metrics=candidate,
        champion_metrics=incumbent,
    )
    _log_promotion_decision(client, challenger_run_id, decision)
    if accepted:
        client.set_registered_model_alias(model_name, "champion", challenger_version)
        client.set_tag(challenger_run_id, "promotion.applied", "true")
    else:
        client.set_tag(challenger_run_id, "promotion.applied", "false")
    return decision
