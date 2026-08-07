"""Feature engineering for both models, reading from dbt marts.

Amendment risk features (per contract at award time):
- agency, UNSPSC category, procurement method, confidentiality flags
- contract duration, initial value band, end-of-financial-year award flag
- supplier history: prior contract count, prior amendment rate, agency familiarity

Fit scorer features (per open tender):
- category match vs firm capability profile, agency spend momentum,
  typical award size, incumbent concentration (HHI), panel vs open approach
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TARGET = "was_amended_up"
FEATURE_COLUMNS = [
    "ocid",
    "award_date",
    "agency",
    "supplier_name",
    "unspsc_category",
    "procurement_method",
    "value_band",
    "award_value_aud",
    "log_award_value",
    "contract_duration_days",
    "is_eofy_award",
    "has_confidentiality",
    "supplier_prior_contract_count",
    "supplier_prior_amendment_rate",
    "supplier_agency_prior_contract_count",
    "supplier_has_agency_history",
    TARGET,
]


def _normalise_text(series: pd.Series, *, case: str, missing: str = "unknown") -> pd.Series:
    values = series.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    values = values.mask(values.eq("") | values.isna(), missing)
    return values.str.upper() if case == "upper" else values.str.lower()


def _as_boolean(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series.dtype):
        return series.fillna(False).astype(bool)
    truthy = {"1", "true", "t", "yes", "y", "confidential"}
    return series.astype("string").str.strip().str.lower().isin(truthy)


def _valid_history_groups(frame: pd.DataFrame, group_columns: list[str]) -> pd.Series:
    valid = pd.Series(True, index=frame.index)
    for column in group_columns:
        valid &= frame[column].ne("UNKNOWN") & frame[column].ne("unknown")
    return valid


def _strict_prior_event_count(
    frame: pd.DataFrame,
    group_columns: list[str],
    event_timestamp_column: str,
) -> pd.Series:
    """Count group events strictly before each row's award timestamp."""

    def canonical_key(key: object) -> tuple[object, ...]:
        return key if isinstance(key, tuple) else (key,)

    group_is_valid = _valid_history_groups(frame, group_columns)
    event_rows = frame.loc[
        group_is_valid & frame[event_timestamp_column].notna(),
        [*group_columns, event_timestamp_column],
    ]
    event_times_by_group = {
        canonical_key(key): np.sort(group[event_timestamp_column].array.asi8)
        for key, group in event_rows.groupby(group_columns, sort=False, dropna=False)
    }

    result = pd.Series(0, index=frame.index, dtype="int64")
    query_rows = frame.loc[
        group_is_valid & frame["_award_timestamp"].notna(),
        [*group_columns, "_award_timestamp"],
    ]
    for key, group in query_rows.groupby(group_columns, sort=False, dropna=False):
        event_times = event_times_by_group.get(canonical_key(key))
        if event_times is not None:
            result.loc[group.index] = np.searchsorted(
                event_times,
                group["_award_timestamp"].array.asi8,
                side="left",
            )
    return result


def build_amendment_features(contracts: pd.DataFrame) -> pd.DataFrame:
    """Return one model-ready row per contract with strictly prior histories.

    Contract counts only include awards strictly earlier than the current row.
    Amendment-rate numerators additionally require the earlier contract's first
    upward-amendment release to have occurred before the current award.
    """
    if contracts.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    required = {
        "ocid",
        "agency",
        "supplier_name",
        "unspsc_code",
        "procurement_method",
        "award_date",
        "award_value_aud",
        TARGET,
    }
    missing = sorted(required.difference(contracts.columns))
    if missing:
        raise ValueError(f"contracts is missing required columns: {', '.join(missing)}")

    frame = contracts.copy().reset_index(drop=True)
    frame["_input_order"] = np.arange(len(frame))
    frame["_award_timestamp"] = pd.to_datetime(frame["award_date"], errors="coerce", utc=True)
    frame["award_date"] = frame["_award_timestamp"]
    frame[TARGET] = _as_boolean(frame[TARGET])

    frame["agency"] = _normalise_text(frame["agency"], case="upper")
    frame["supplier_name"] = _normalise_text(frame["supplier_name"], case="upper")
    frame["procurement_method"] = _normalise_text(frame["procurement_method"], case="lower")
    frame["unspsc_category"] = (
        frame["unspsc_code"].astype("string").str.extract(r"^(\d{2})", expand=False)
    ).fillna("unknown")

    frame["award_value_aud"] = pd.to_numeric(frame["award_value_aud"], errors="coerce")
    non_negative_value = frame["award_value_aud"].clip(lower=0)
    frame["log_award_value"] = np.log1p(non_negative_value)
    frame["value_band"] = (
        pd.cut(
            frame["award_value_aud"],
            bins=[-np.inf, 10_000, 80_000, 1_000_000, 10_000_000, np.inf],
            labels=["under_10k", "10k_to_80k", "80k_to_1m", "1m_to_10m", "10m_plus"],
            right=False,
        )
        .astype("string")
        .fillna("unknown")
    )

    start_source = frame.get("contract_start_date", frame["award_date"])
    end_source = frame.get("contract_end_date", pd.Series(pd.NaT, index=frame.index))
    contract_start = pd.to_datetime(start_source, errors="coerce", utc=True)
    contract_end = pd.to_datetime(end_source, errors="coerce", utc=True)
    frame["contract_duration_days"] = (contract_end - contract_start).dt.total_seconds() / 86_400
    frame.loc[frame["contract_duration_days"] < 0, "contract_duration_days"] = np.nan
    frame["is_eofy_award"] = frame["award_date"].dt.month.eq(6).astype("int8")

    value_confidential = _as_boolean(
        frame.get("value_confidentiality", pd.Series(False, index=frame.index))
    )
    description_confidential = _as_boolean(
        frame.get("description_confidentiality", pd.Series(False, index=frame.index))
    )
    frame["has_confidentiality"] = (value_confidential | description_confidential).astype("int8")

    upward_timestamp_source = frame.get(
        "first_upward_amendment_date",
        frame.get("last_amendment_date", pd.Series(pd.NaT, index=frame.index)),
    )
    frame["_known_upward_timestamp"] = pd.to_datetime(
        upward_timestamp_source, errors="coerce", utc=True
    ).where(frame[TARGET])
    frame["supplier_prior_contract_count"] = _strict_prior_event_count(
        frame, ["supplier_name"], "_award_timestamp"
    )
    prior_known_amendments = _strict_prior_event_count(
        frame, ["supplier_name"], "_known_upward_timestamp"
    )
    frame["supplier_prior_amendment_rate"] = np.where(
        frame["supplier_prior_contract_count"] > 0,
        prior_known_amendments / frame["supplier_prior_contract_count"],
        0.0,
    )

    frame["supplier_agency_prior_contract_count"] = _strict_prior_event_count(
        frame,
        ["supplier_name", "agency"],
        "_award_timestamp",
    )
    frame["supplier_has_agency_history"] = (
        frame["supplier_agency_prior_contract_count"].gt(0).astype("int8")
    )

    return frame.sort_values("_input_order", kind="mergesort")[FEATURE_COLUMNS].reset_index(
        drop=True
    )


def build_fit_features(tenders: pd.DataFrame, capability_profile: dict) -> pd.DataFrame:
    # TODO(week-3)
    raise NotImplementedError
