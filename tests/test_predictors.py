from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from procurelens.api import predictors
from procurelens.api.predictors import (
    AmendmentRiskPredictor,
    DriverValue,
    ShapDriverExtractor,
    amendment_records_to_frame,
)
from procurelens.models.registry import LoadedModel
from procurelens.models.train_amendment_risk import MODEL_FEATURES


@pytest.mark.parametrize(
    ("value", "band"),
    [
        (9_999, "under_10k"),
        (10_000, "10k_to_80k"),
        (80_000, "80k_to_1m"),
        (1_000_000, "1m_to_10m"),
        (10_000_000, "10m_plus"),
    ],
)
def test_value_band_boundaries(value: float, band: str):
    assert predictors._value_band(value) == band


def test_api_records_translate_to_exact_training_contract():
    frame = amendment_records_to_frame(
        [
            {
                "agency": " Department of Finance ",
                "unspsc_category": "8111-0000",
                "procurement_method": "OPEN",
                "contract_value_aud": 250_000,
                "contract_duration_days": 365,
                "award_date": date(2026, 6, 15),
                "has_confidentiality": True,
                "supplier_prior_contracts": 4,
                "supplier_prior_amendment_rate": 0.25,
                "supplier_agency_prior_contracts": 2,
            },
            {
                "agency": "Unknown",
                "unspsc_category": "not supplied",
                "procurement_method": "limited",
                "contract_value_aud": 20_000_000,
                "contract_duration_days": 30,
            },
        ]
    )
    assert list(frame.columns) == MODEL_FEATURES
    assert frame.loc[0, "agency"] == "DEPARTMENT OF FINANCE"
    assert frame.loc[0, "unspsc_category"] == "81"
    assert frame.loc[0, "is_eofy_award"] == 1.0
    assert frame.loc[0, "supplier_has_agency_history"] == 1.0
    assert frame.loc[1, "unspsc_category"] == "unknown"
    assert frame.loc[1, "value_band"] == "10m_plus"


class FakePreprocessor:
    def transform(self, frame: Any) -> np.ndarray:
        return np.tile(np.array([[1.0, 2.0, 3.0]]), (len(frame), 1))

    def get_feature_names_out(self) -> np.ndarray:
        return np.array(
            [
                "categorical__agency_DEPARTMENT OF FINANCE",
                "numeric__award_value_aud",
                "numeric__contract_duration_days",
            ]
        )


class FakePipeline:
    named_steps = {"preprocessor": FakePreprocessor(), "classifier": object()}


class FakeExplainer:
    def __call__(self, transformed: np.ndarray) -> Any:
        values = np.tile(np.array([[0.1, 0.7, -0.4]]), (len(transformed), 1))
        return SimpleNamespace(values=values)


def test_shap_driver_extractor_groups_human_features_and_sorts_impacts(monkeypatch):
    import shap

    monkeypatch.setattr(shap, "TreeExplainer", lambda _classifier: FakeExplainer())
    model = SimpleNamespace(
        calibrated_classifiers_=[SimpleNamespace(estimator=FakePipeline())]
    )
    extractor = ShapDriverExtractor(model)
    frame = amendment_records_to_frame(
        [
            {
                "agency": "Finance",
                "unspsc_category": "81",
                "procurement_method": "open",
                "contract_value_aud": 100_000,
                "contract_duration_days": 365,
            }
        ]
    )
    drivers = extractor.explain(frame, limit=2)[0]
    assert [driver.feature for driver in drivers] == [
        "award_value_aud",
        "contract_duration_days",
    ]
    assert drivers[0].direction == "increases_risk"
    assert drivers[1].direction == "decreases_risk"


class FakeProbabilityModel:
    def __init__(self, probabilities: np.ndarray | None = None) -> None:
        self.probabilities = (
            probabilities if probabilities is not None else np.array([[0.9, 0.1], [0.2, 0.8]])
        )

    def predict_proba(self, _frame: Any) -> np.ndarray:
        return self.probabilities


class FakeDriverExtractor:
    def explain(self, frame: Any) -> list[list[DriverValue]]:
        return [
            [DriverValue("award_value_aud", 0.2, "increases_risk")] for _ in range(len(frame))
        ]


def _loaded(model: Any) -> LoadedModel:
    return LoadedModel(
        model=model,
        name="procurelens-amendment-risk",
        alias="champion",
        version="9",
        run_id="run-9",
    )


def _records() -> list[dict[str, Any]]:
    return [
        {
            "agency": "Finance",
            "unspsc_category": "81",
            "procurement_method": "open",
            "contract_value_aud": 100_000,
            "contract_duration_days": 365,
        },
        {
            "agency": "Defence",
            "unspsc_category": "43",
            "procurement_method": "limited",
            "contract_value_aud": 2_000_000,
            "contract_duration_days": 1_000,
        },
    ]


def test_predictor_returns_calibrated_bands_version_and_drivers():
    predictor = AmendmentRiskPredictor(_loaded(FakeProbabilityModel()), FakeDriverExtractor())
    predictions = predictor.predict(_records())
    assert [prediction.risk_band for prediction in predictions] == ["low", "high"]
    assert [prediction.probability for prediction in predictions] == [0.1, 0.8]
    assert all(prediction.model_version == "9" for prediction in predictions)
    assert predictions[0].top_drivers[0].feature == "award_value_aud"
    assert predictor.model_run_id == "run-9"


def test_predictor_rejects_wrong_model_contract_or_probability_shape():
    with pytest.raises(TypeError, match="predict_proba"):
        AmendmentRiskPredictor(_loaded(object()))
    bad_model = FakeProbabilityModel(np.array([0.1, 0.2]))
    predictor = AmendmentRiskPredictor(_loaded(bad_model), FakeDriverExtractor())
    with pytest.raises(RuntimeError, match="invalid shape"):
        predictor.predict(_records())


def test_predictor_loads_champion_alias_from_registry(monkeypatch):
    monkeypatch.setattr(
        predictors,
        "load_champion",
        lambda name, tracking_uri: _loaded(FakeProbabilityModel()),
    )
    monkeypatch.setattr(predictors, "ShapDriverExtractor", lambda _model: FakeDriverExtractor())
    predictor = AmendmentRiskPredictor.from_registry("http://mlflow")
    assert predictor.model_version == "9"


@pytest.mark.parametrize(
    ("probability", "band"),
    [(0.0, "low"), (0.1499, "low"), (0.15, "medium"), (0.3499, "medium"), (0.35, "high")],
)
def test_risk_band_boundaries(probability: float, band: str):
    assert AmendmentRiskPredictor._band(probability) == band
