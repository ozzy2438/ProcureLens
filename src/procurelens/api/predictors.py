"""Serving adapters for calibrated amendment-risk inference and SHAP drivers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

import numpy as np
import pandas as pd

from procurelens.models.registry import LoadedModel, load_champion
from procurelens.models.train_amendment_risk import MODEL_FEATURES, REGISTERED_MODEL


@dataclass(frozen=True)
class DriverValue:
    feature: str
    impact: float
    direction: str


@dataclass(frozen=True)
class AmendmentPrediction:
    probability: float
    risk_band: str
    model_version: str
    top_drivers: list[DriverValue]


def _value_band(value: float) -> str:
    if value < 10_000:
        return "under_10k"
    if value < 80_000:
        return "10k_to_80k"
    if value < 1_000_000:
        return "80k_to_1m"
    if value < 10_000_000:
        return "1m_to_10m"
    return "10m_plus"


def amendment_records_to_frame(records: list[Mapping[str, Any]]) -> pd.DataFrame:
    """Translate validated API records into the exact training feature contract."""
    rows: list[dict[str, Any]] = []
    for record in records:
        value = float(record["contract_value_aud"])
        award_date = record.get("award_date")
        award_month = award_date.month if isinstance(award_date, (date, datetime)) else None
        category_digits = "".join(
            character
            for character in str(record["unspsc_category"])
            if character.isdigit()
        )
        rows.append(
            {
                "agency": str(record["agency"]).strip().upper(),
                "unspsc_category": category_digits[:2] or "unknown",
                "procurement_method": str(record["procurement_method"]).strip().lower(),
                "value_band": _value_band(value),
                "award_value_aud": value,
                "log_award_value": float(np.log1p(value)),
                "contract_duration_days": float(record["contract_duration_days"]),
                "is_eofy_award": float(award_month == 6),
                "has_confidentiality": float(bool(record.get("has_confidentiality", False))),
                "supplier_prior_contract_count": float(record.get("supplier_prior_contracts", 0)),
                "supplier_prior_amendment_rate": float(
                    record.get("supplier_prior_amendment_rate", 0.0)
                ),
                "supplier_agency_prior_contract_count": float(
                    record.get("supplier_agency_prior_contracts", 0)
                ),
                "supplier_has_agency_history": float(
                    int(record.get("supplier_agency_prior_contracts", 0) > 0)
                ),
            }
        )
    return pd.DataFrame(rows, columns=MODEL_FEATURES)


class ShapDriverExtractor:
    """Average XGBoost SHAP values across isotonic-calibration folds."""

    def __init__(self, calibrated_model: Any) -> None:
        import shap

        self._folds: list[tuple[Any, Any, Any]] = []
        classifiers = getattr(calibrated_model, "calibrated_classifiers_", None)
        if not classifiers:
            raise TypeError("champion model is not a fitted CalibratedClassifierCV")
        for calibrated_classifier in classifiers:
            pipeline = calibrated_classifier.estimator
            preprocessor = pipeline.named_steps["preprocessor"]
            classifier = pipeline.named_steps["classifier"]
            self._folds.append((preprocessor, shap.TreeExplainer(classifier), classifier))

    @staticmethod
    def _human_feature_name(name: str) -> str:
        name = name.removeprefix("categorical__").removeprefix("numeric__")
        for categorical_name in ("agency", "unspsc_category", "procurement_method", "value_band"):
            if name.startswith(f"{categorical_name}_"):
                return categorical_name
        return name

    def explain(self, frame: pd.DataFrame, limit: int = 5) -> list[list[DriverValue]]:
        row_impacts: list[dict[str, list[float]]] = [{} for _ in range(len(frame))]
        for preprocessor, explainer, _classifier in self._folds:
            transformed = preprocessor.transform(frame)
            if hasattr(transformed, "toarray"):
                transformed = transformed.toarray()
            values = np.asarray(explainer(transformed).values)
            if values.ndim == 3:
                values = values[:, :, -1]
            feature_names = preprocessor.get_feature_names_out()
            for row_index, row_values in enumerate(values):
                grouped_impacts: dict[str, float] = {}
                for name, impact in zip(feature_names, row_values, strict=True):
                    human_name = self._human_feature_name(str(name))
                    grouped_impacts[human_name] = grouped_impacts.get(human_name, 0.0) + float(
                        impact
                    )
                for name, impact in grouped_impacts.items():
                    row_impacts[row_index].setdefault(name, []).append(impact)

        explanations: list[list[DriverValue]] = []
        for impacts in row_impacts:
            averaged = [(name, float(np.mean(values))) for name, values in impacts.items()]
            averaged.sort(key=lambda item: (-abs(item[1]), item[0]))
            explanations.append(
                [
                    DriverValue(
                        feature=name,
                        impact=round(impact, 6),
                        direction="increases_risk" if impact >= 0 else "decreases_risk",
                    )
                    for name, impact in averaged[:limit]
                ]
            )
        return explanations


class AmendmentRiskPredictor:
    """Calibrated probability serving facade with immutable model metadata."""

    def __init__(self, loaded: LoadedModel, driver_extractor: Any | None = None) -> None:
        if not hasattr(loaded.model, "predict_proba"):
            raise TypeError("champion model does not expose predict_proba")
        self._model = loaded.model
        self.model_version = loaded.version
        self.model_run_id = loaded.run_id
        self._driver_extractor = driver_extractor or ShapDriverExtractor(loaded.model)

    @classmethod
    def from_registry(cls, tracking_uri: str) -> AmendmentRiskPredictor:
        return cls(load_champion(REGISTERED_MODEL, tracking_uri=tracking_uri))

    @staticmethod
    def _band(probability: float) -> str:
        if probability < 0.15:
            return "low"
        if probability < 0.35:
            return "medium"
        return "high"

    def predict(self, records: list[Mapping[str, Any]]) -> list[AmendmentPrediction]:
        frame = amendment_records_to_frame(records)
        probabilities = np.asarray(self._model.predict_proba(frame))
        if probabilities.ndim != 2 or probabilities.shape != (len(frame), 2):
            raise RuntimeError("champion predict_proba returned an invalid shape")
        explanations = self._driver_extractor.explain(frame)
        return [
            AmendmentPrediction(
                probability=float(probability),
                risk_band=self._band(float(probability)),
                model_version=self.model_version,
                top_drivers=drivers,
            )
            for probability, drivers in zip(probabilities[:, 1], explanations, strict=True)
        ]
