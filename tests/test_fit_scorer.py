from copy import deepcopy

import pandas as pd
import pytest

from procurelens.features.build_features import FIT_FEATURE_COLUMNS, build_fit_features
from procurelens.models.train_fit_scorer import WeightedFitScorer, load_capability_profile


def _strong_tender() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "tender_id": "ATM-001",
                "unspsc_category": "81110000",
                "agency": "Department A",
                "estimated_value_aud": 800_000,
                "procurement_method": "open",
                "tender_title": "Responsible AI and machine learning advisory",
                "tender_description": "MLOps data platform and data governance",
                "as_of_date": "2025-01-01",
                "close_date": "2025-02-15",
                "agency_recent_tech_spend_aud": 100_000_000,
                "agency_familiarity_count": 3,
                "supplier_hhi": 0.2,
            }
        ]
    )


def test_fit_features_empty_input_has_stable_schema():
    result = build_fit_features(pd.DataFrame(), load_capability_profile())
    assert result.empty
    assert list(result.columns) == FIT_FEATURE_COLUMNS


def test_fit_score_is_bounded_and_strong_profile_scores_higher():
    profile = load_capability_profile()
    scorer = WeightedFitScorer(profile)
    strong = scorer.score_frame(_strong_tender()).iloc[0]
    weak_tender = _strong_tender().assign(
        unspsc_category="15100000",
        estimated_value_aud=40_000_000,
        procurement_method="limited",
        tender_title="Office furniture supply",
        tender_description="Desks and chairs",
        agency_recent_tech_spend_aud=0,
        agency_familiarity_count=0,
        supplier_hhi=0.95,
        close_date="2025-01-03",
    )
    weak = scorer.score_frame(weak_tender).iloc[0]
    assert 0 <= weak["fit_score"] < strong["fit_score"] <= 100
    assert strong["fit_band"] == "strong_fit"
    assert weak["fit_band"] == "low_fit"


def test_fit_scorer_reasons_are_deterministic():
    scorer = WeightedFitScorer(load_capability_profile())
    first = scorer.score_frame(_strong_tender()).iloc[0]
    second = scorer.score_frame(_strong_tender()).iloc[0]
    assert first["positive_reasons"] == second["positive_reasons"]
    assert first["negative_reasons"] == second["negative_reasons"]


def test_future_contracts_do_not_change_fit_history_features():
    profile = load_capability_profile()
    tender = _strong_tender().drop(
        columns=["agency_recent_tech_spend_aud", "agency_familiarity_count", "supplier_hhi"]
    )
    prior = {
        "agency": "Department A",
        "award_date": "2024-06-01",
        "award_value_aud": 2_000_000,
        "unspsc_code": "81110000",
        "supplier_name": "ProcureLens Advisory Pty Ltd",
    }
    future = {
        "agency": "Department A",
        "award_date": "2026-06-01",
        "award_value_aud": 500_000_000,
        "unspsc_code": "81110000",
        "supplier_name": "Future Supplier",
    }
    baseline = build_fit_features(tender, profile, pd.DataFrame([prior])).iloc[0]
    with_future = build_fit_features(tender, profile, pd.DataFrame([prior, future])).iloc[0]
    columns = [
        "agency_recent_tech_spend_aud",
        "agency_familiarity_count",
        "supplier_hhi",
        "agency_tech_spend",
        "agency_familiarity",
        "supplier_diversity",
        "fit_score",
    ]
    pd.testing.assert_series_equal(baseline[columns], with_future[columns])


def test_fit_profile_weights_must_sum_to_one():
    profile = deepcopy(load_capability_profile())
    profile["weights"]["category_match"] = 0.5
    with pytest.raises(ValueError, match="sum to 1.0"):
        build_fit_features(_strong_tender(), profile)
