"""Version and register the explainable Opportunity Fit Scorer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from procurelens.config import get_settings
from procurelens.features.build_features import FIT_COMPONENTS, build_fit_features

REGISTERED_MODEL = "procurelens-fit-scorer"
EXPERIMENT = "opportunity_fit_scorer"


def load_capability_profile(path: str | Path | None = None) -> dict[str, Any]:
    profile_path = Path(path or get_settings().capability_profile_path)
    if not profile_path.is_absolute():
        profile_path = Path.cwd() / profile_path
    if not profile_path.exists():
        raise FileNotFoundError(f"capability profile not found: {profile_path}")
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict):
        raise ValueError("capability profile must be a YAML mapping")
    return profile


class WeightedFitScorer:
    """Transparent weighted ranking model; explicitly not a win probability."""

    def __init__(self, profile: dict[str, Any]) -> None:
        self.profile = profile
        self.version = str(profile["version"])

    @staticmethod
    def _fit_band(score: int, profile: dict[str, Any]) -> str:
        bands = profile["score_bands"]
        if score >= int(bands["strong_fit"]):
            return "strong_fit"
        if score >= int(bands["review"]):
            return "review"
        return "low_fit"

    @staticmethod
    def _reason(component: str, row: pd.Series, positive: bool) -> str:
        if component == "category_match":
            verb = "matches" if positive else "does not match"
            return f"UNSPSC segment {row['unspsc_segment']} {verb} the target profile"
        if component == "keyword_match":
            keywords = ", ".join(row["matched_keywords"][:4])
            return (
                f"Matched capability terms: {keywords}"
                if positive and keywords
                else "Few or no target capability terms were found"
            )
        if component == "agency_tech_spend":
            amount = float(row["agency_recent_tech_spend_aud"])
            adjective = "strong" if positive else "limited"
            return f"Agency has {adjective} recent target-category spend (AUD {amount:,.0f})"
        if component == "value_fit":
            return (
                "Estimated value is within the preferred engagement range"
                if positive
                else "Estimated value is unknown or outside the preferred engagement range"
            )
        if component == "agency_familiarity":
            count = int(row["agency_familiarity_count"])
            return (
                f"Firm has {count} prior contract(s) with the agency"
                if positive
                else "No meaningful prior agency familiarity is recorded"
            )
        if component == "supplier_diversity":
            hhi = row["supplier_hhi"]
            return (
                "Supplier spend is relatively diversified"
                if positive
                else (
                    "Supplier concentration is high"
                    if pd.notna(hhi)
                    else "Supplier concentration is unknown"
                )
            )
        if component == "procurement_access":
            return (
                f"{row['procurement_method']} procurement provides accessible competition"
                if positive
                else f"{row['procurement_method']} procurement limits market access"
            )
        if component == "lead_time":
            days = row["days_to_close"]
            return (
                f"Bid lead time is workable ({days:.0f} days)"
                if positive and pd.notna(days)
                else "Bid lead time is short or unavailable"
            )
        raise ValueError(f"unknown fit component: {component}")

    def score_frame(
        self,
        tenders: pd.DataFrame,
        contract_history: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        features = build_fit_features(tenders, self.profile, contract_history)
        if features.empty:
            return features.assign(
                fit_band=pd.Series(dtype="string"),
                positive_reasons=pd.Series(dtype="object"),
                negative_reasons=pd.Series(dtype="object"),
                scorer_version=pd.Series(dtype="string"),
            )
        weights = self.profile["weights"]
        positive_reasons: list[list[str]] = []
        negative_reasons: list[list[str]] = []
        for _, row in features.iterrows():
            positives = sorted(
                (
                    (float(weights[name]) * float(row[name]), name)
                    for name in FIT_COMPONENTS
                    if float(row[name]) >= 0.6
                ),
                key=lambda item: (-item[0], item[1]),
            )
            negatives = sorted(
                (
                    (float(weights[name]) * (1 - float(row[name])), name)
                    for name in FIT_COMPONENTS
                    if float(row[name]) <= 0.4
                ),
                key=lambda item: (-item[0], item[1]),
            )
            positive_reasons.append(
                [self._reason(name, row, True) for _, name in positives[:3]]
                or ["No strong positive fit signals were detected"]
            )
            negative_reasons.append(
                [self._reason(name, row, False) for _, name in negatives[:3]]
                or ["No material negative fit signals were detected"]
            )
        result = features.copy()
        result["fit_band"] = result["fit_score"].map(
            lambda score: self._fit_band(int(score), self.profile)
        )
        result["positive_reasons"] = positive_reasons
        result["negative_reasons"] = negative_reasons
        result["scorer_version"] = self.version
        return result


def train(
    *,
    profile_path: str | Path | None = None,
    tracking_uri: str | None = None,
) -> dict[str, str]:
    """Register the versioned ranking policy as an MLflow pyfunc model."""
    import mlflow
    import mlflow.pyfunc
    from mlflow.models import infer_signature
    from mlflow.tracking import MlflowClient

    profile = load_capability_profile(profile_path)
    scorer = WeightedFitScorer(profile)
    example = pd.DataFrame(
        [
            {
                "tender_id": "example-1",
                "unspsc_category": "81110000",
                "agency": "Department of Finance",
                "estimated_value_aud": 500_000,
                "procurement_method": "open",
                "tender_title": "Machine learning and data platform advisory",
                "tender_description": "Responsible AI, MLOps and data governance services",
                "as_of_date": "2026-08-07",
                "close_date": "2026-09-07",
                "agency_recent_tech_spend_aud": 50_000_000,
                "agency_familiarity_count": 1,
                "supplier_hhi": 0.25,
            }
        ]
    )
    example_output = scorer.score_frame(example)[["fit_score"]]

    class FitScorerPyfunc(mlflow.pyfunc.PythonModel):  # type: ignore[name-defined]
        def __init__(self, stored_profile: dict[str, Any]) -> None:
            self.stored_profile = stored_profile

        def predict(
            self, context: Any, model_input: pd.DataFrame, params: dict[str, Any] | None = None
        ) -> pd.DataFrame:
            del context, params
            return WeightedFitScorer(self.stored_profile).score_frame(model_input)[["fit_score"]]

    settings = get_settings()
    mlflow.set_tracking_uri(tracking_uri or settings.mlflow_tracking_uri)
    mlflow.set_experiment(EXPERIMENT)
    with mlflow.start_run() as run:
        mlflow.log_param("scorer_type", "explainable_weighted_ranking")
        mlflow.log_param("scorer_version", scorer.version)
        mlflow.log_param("supervised_win_probability", False)
        for name, value in profile["weights"].items():
            mlflow.log_param(f"weight_{name}", value)
        model_info = mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=FitScorerPyfunc(profile),
            registered_model_name=REGISTERED_MODEL,
            signature=infer_signature(example, example_output),
            input_example=example,
            code_paths=["src"],
        )
        run_id = run.info.run_id

    version = getattr(model_info, "registered_model_version", None)
    if version is None:
        raise RuntimeError("MLflow did not return a fit-scorer model version")
    client = MlflowClient()
    client.set_registered_model_alias(REGISTERED_MODEL, "challenger", str(version))
    try:
        client.get_model_version_by_alias(REGISTERED_MODEL, "champion")
    except Exception:
        client.set_registered_model_alias(REGISTERED_MODEL, "champion", str(version))
    return {"run_id": run_id, "model_version": str(version), "scorer_version": scorer.version}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default=None)
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    result = train(profile_path=args.profile, tracking_uri=args.tracking_uri)
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
