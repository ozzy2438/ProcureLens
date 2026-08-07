import pandas as pd
import pytest

from procurelens.features.build_features import FEATURE_COLUMNS, build_amendment_features


def _contracts() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ocid": "c1",
                "agency": "Agency A",
                "supplier_name": "Supplier One",
                "unspsc_code": "81110000",
                "procurement_method": "open",
                "award_date": "2020-01-01T00:00:00Z",
                "contract_start_date": "2020-01-01T00:00:00Z",
                "contract_end_date": "2021-01-01T00:00:00Z",
                "award_value_aud": 50_000,
                "was_amended_up": False,
            },
            {
                "ocid": "c2",
                "agency": "Agency B",
                "supplier_name": "Supplier One",
                "unspsc_code": "43230000",
                "procurement_method": "limited",
                "award_date": "2021-01-01T00:00:00Z",
                "contract_start_date": "2021-01-01T00:00:00Z",
                "contract_end_date": "2021-07-01T00:00:00Z",
                "award_value_aud": 200_000,
                "was_amended_up": True,
                "first_upward_amendment_date": "2021-09-01T00:00:00Z",
            },
            {
                "ocid": "c3",
                "agency": "Agency A",
                "supplier_name": "Supplier One",
                "unspsc_code": "81110000",
                "procurement_method": "open",
                "award_date": "2022-06-15T00:00:00Z",
                "contract_start_date": "2022-06-15T00:00:00Z",
                "contract_end_date": "2023-06-15T00:00:00Z",
                "award_value_aud": 2_000_000,
                "was_amended_up": False,
            },
            {
                "ocid": "c4",
                "agency": "Agency A",
                "supplier_name": "Supplier One",
                "unspsc_code": "81110000",
                "procurement_method": "open",
                "award_date": "2022-06-15T00:00:00Z",
                "contract_start_date": "2022-06-15T00:00:00Z",
                "contract_end_date": "2024-06-15T00:00:00Z",
                "award_value_aud": 3_000_000,
                "was_amended_up": True,
            },
            {
                "ocid": "c5",
                "agency": "Agency A",
                "supplier_name": "Supplier One",
                "unspsc_code": "81110000",
                "procurement_method": "open",
                "award_date": "2023-01-01T00:00:00Z",
                "contract_start_date": "2023-01-01T00:00:00Z",
                "contract_end_date": "2024-01-01T00:00:00Z",
                "award_value_aud": 4_000_000,
                "was_amended_up": True,
            },
        ]
    )


def test_empty_input_returns_stable_schema():
    result = build_amendment_features(pd.DataFrame())
    assert result.empty
    assert list(result.columns) == FEATURE_COLUMNS


def test_supplier_histories_use_only_strictly_prior_awards():
    result = build_amendment_features(_contracts()).set_index("ocid")

    assert result.loc["c1", "supplier_prior_contract_count"] == 0
    assert result.loc["c2", "supplier_prior_contract_count"] == 1
    assert result.loc["c3", "supplier_prior_contract_count"] == 2
    assert result.loc["c4", "supplier_prior_contract_count"] == 2
    assert result.loc["c3", "supplier_prior_amendment_rate"] == pytest.approx(0.5)
    assert result.loc["c4", "supplier_prior_amendment_rate"] == pytest.approx(0.5)
    assert result.loc["c3", "supplier_agency_prior_contract_count"] == 1
    assert result.loc["c5", "supplier_prior_contract_count"] == 4


def test_future_or_current_targets_cannot_leak_into_prior_features():
    baseline = build_amendment_features(_contracts()).set_index("ocid")
    changed = _contracts()
    changed.loc[changed["ocid"].isin(["c3", "c5"]), "was_amended_up"] = True
    rebuilt = build_amendment_features(changed).set_index("ocid")

    history_columns = [
        "supplier_prior_contract_count",
        "supplier_prior_amendment_rate",
        "supplier_agency_prior_contract_count",
        "supplier_has_agency_history",
    ]
    pd.testing.assert_series_equal(
        baseline.loc["c3", history_columns],
        rebuilt.loc["c3", history_columns],
    )
    pd.testing.assert_frame_equal(
        baseline.loc[["c1", "c2", "c3", "c4"], history_columns],
        rebuilt.loc[["c1", "c2", "c3", "c4"], history_columns],
    )


def test_contract_features_are_derived_at_award_time():
    result = build_amendment_features(_contracts()).set_index("ocid")
    assert result.loc["c1", "value_band"] == "10k_to_80k"
    assert result.loc["c3", "value_band"] == "1m_to_10m"
    assert result.loc["c3", "unspsc_category"] == "81"
    assert result.loc["c3", "is_eofy_award"] == 1
    assert result.loc["c1", "contract_duration_days"] == pytest.approx(366)


def test_amendments_published_after_current_award_are_not_in_history():
    contracts = _contracts()
    contracts.loc[contracts["ocid"].eq("c2"), "first_upward_amendment_date"] = (
        "2024-01-01T00:00:00Z"
    )
    result = build_amendment_features(contracts).set_index("ocid")
    assert result.loc["c3", "supplier_prior_contract_count"] == 2
    assert result.loc["c3", "supplier_prior_amendment_rate"] == 0


def test_missing_required_columns_are_reported():
    with pytest.raises(ValueError, match="unspsc_code"):
        build_amendment_features(_contracts().drop(columns="unspsc_code"))
