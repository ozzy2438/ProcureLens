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

import re

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

FIT_COMPONENTS = [
    "category_match",
    "keyword_match",
    "agency_tech_spend",
    "value_fit",
    "agency_familiarity",
    "supplier_diversity",
    "procurement_access",
    "lead_time",
]
FIT_FEATURE_COLUMNS = [
    "tender_id",
    "unspsc_segment",
    "agency",
    "estimated_value_aud",
    "procurement_method",
    "as_of_date",
    "days_to_close",
    "agency_recent_tech_spend_aud",
    "agency_familiarity_count",
    "supplier_hhi",
    "matched_keywords",
    *FIT_COMPONENTS,
    "fit_score",
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


def _fit_value_score(value: float | None, profile: dict) -> float:
    if value is None or pd.isna(value):
        return 0.5
    limits = profile["target_contract_value_aud"]
    floor = float(limits["floor"])
    preferred_min = float(limits["preferred_min"])
    preferred_max = float(limits["preferred_max"])
    ceiling = float(limits["ceiling"])
    value = float(value)
    if preferred_min <= value <= preferred_max:
        return 1.0
    if floor < value < preferred_min:
        return (value - floor) / (preferred_min - floor)
    if preferred_max < value < ceiling:
        return (ceiling - value) / (ceiling - preferred_max)
    return 0.0


def _fit_keyword_matches(text: str, profile: dict) -> tuple[str, ...]:
    haystack = re.sub(r"\s+", " ", text.lower()).strip()
    keywords = {
        keyword.lower()
        for values in profile["capability_keywords"].values()
        for keyword in values
    }
    return tuple(sorted(keyword for keyword in keywords if keyword in haystack))


def _history_before_tender(
    history: pd.DataFrame,
    *,
    agency: str,
    as_of: pd.Timestamp,
    profile: dict,
) -> tuple[float, int, float | None]:
    if history.empty:
        return 0.0, 0, None
    required = {"agency", "award_date", "award_value_aud", "unspsc_code", "supplier_name"}
    missing = sorted(required.difference(history.columns))
    if missing:
        raise ValueError(f"contract_history is missing required columns: {', '.join(missing)}")

    eligible = history.loc[
        history["_history_award_timestamp"].notna()
        & history["_history_award_timestamp"].lt(as_of)
        & history["_history_agency"].eq(agency)
    ].copy()
    if eligible.empty:
        return 0.0, 0, None
    recent = eligible.loc[
        eligible["_history_award_timestamp"].ge(as_of - pd.Timedelta(days=365))
    ].copy()
    target_segments = {str(code)[:2] for code in profile["target_unspsc_segments"]}
    recent_segments = recent["unspsc_code"].astype("string").str.extract(
        r"^(\d{2})", expand=False
    )
    recent_values = pd.to_numeric(recent["award_value_aud"], errors="coerce").clip(lower=0)
    tech_spend = float(recent_values.loc[recent_segments.isin(target_segments)].sum())

    firm_names = {str(name).strip().upper() for name in profile.get("firm_supplier_names", [])}
    familiarity = int(
        eligible["supplier_name"].astype("string").str.strip().str.upper().isin(firm_names).sum()
    )

    supplier_values = (
        recent.assign(_value=recent_values)
        .groupby("supplier_name", dropna=False)["_value"]
        .sum()
    )
    total_value = float(supplier_values.sum())
    hhi = float(((supplier_values / total_value) ** 2).sum()) if total_value > 0 else None
    return tech_spend, familiarity, hhi


def build_fit_features(
    tenders: pd.DataFrame,
    capability_profile: dict,
    contract_history: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build deterministic point-in-time features for opportunity ranking.

    When contract history is supplied, only awards strictly earlier than each
    tender's ``as_of_date`` contribute to spend, familiarity, and HHI.
    """
    if tenders.empty:
        return pd.DataFrame(columns=FIT_FEATURE_COLUMNS)
    required = {"tender_id", "unspsc_category", "agency"}
    missing = sorted(required.difference(tenders.columns))
    if missing:
        raise ValueError(f"tenders is missing required columns: {', '.join(missing)}")

    weights = capability_profile["weights"]
    missing_weights = sorted(set(FIT_COMPONENTS).difference(weights))
    if missing_weights:
        raise ValueError(f"capability profile is missing weights: {', '.join(missing_weights)}")
    if not np.isclose(sum(float(weights[name]) for name in FIT_COMPONENTS), 1.0):
        raise ValueError("fit scorer weights must sum to 1.0")

    history = contract_history.copy() if contract_history is not None else pd.DataFrame()
    if not history.empty:
        history["_history_award_timestamp"] = pd.to_datetime(
            history["award_date"], errors="coerce", utc=True
        )
        history["_history_agency"] = _normalise_text(history["agency"], case="upper")

    target_segments = {str(code)[:2] for code in capability_profile["target_unspsc_segments"]}
    keyword_target = max(int(capability_profile["normalisation"]["keyword_match_target"]), 1)
    spend_reference = max(
        float(capability_profile["normalisation"]["tech_spend_reference_aud"]), 1.0
    )
    familiarity_reference = max(
        int(capability_profile["normalisation"]["familiarity_contracts"]), 1
    )
    procurement_scores = capability_profile["procurement_method_scores"]
    rows: list[dict] = []
    for _, tender in tenders.reset_index(drop=True).iterrows():
        agency = re.sub(r"\s+", " ", str(tender["agency"]).strip()).upper()
        category_digits = re.sub(r"\D", "", str(tender["unspsc_category"]))
        segment = category_digits[:2] or "unknown"
        as_of = pd.to_datetime(tender.get("as_of_date", pd.Timestamp.now(tz="UTC")), utc=True)
        close_date = pd.to_datetime(tender.get("close_date"), errors="coerce", utc=True)
        days_to_close = (
            float((close_date - as_of).total_seconds() / 86_400)
            if pd.notna(close_date)
            else np.nan
        )

        if contract_history is not None:
            tech_spend, familiarity, hhi = _history_before_tender(
                history,
                agency=agency,
                as_of=as_of,
                profile=capability_profile,
            )
        else:
            tech_spend = float(tender.get("agency_recent_tech_spend_aud", 0) or 0)
            familiarity = int(tender.get("agency_familiarity_count", 0) or 0)
            raw_hhi = tender.get("supplier_hhi")
            hhi = None if raw_hhi is None or pd.isna(raw_hhi) else float(raw_hhi)

        text = f"{tender.get('tender_title', '')} {tender.get('tender_description', '')}"
        matched_keywords = _fit_keyword_matches(text, capability_profile)
        method = str(tender.get("procurement_method", "open")).strip().lower()
        value = tender.get("estimated_value_aud")
        lead_time_score = 0.5
        if pd.notna(days_to_close):
            if days_to_close <= 0:
                lead_time_score = 0.0
            elif days_to_close < 7:
                lead_time_score = 0.2
            elif days_to_close < 14:
                lead_time_score = 0.5
            elif days_to_close < 30:
                lead_time_score = 0.8
            else:
                lead_time_score = 1.0
        components = {
            "category_match": float(segment in target_segments),
            "keyword_match": min(len(matched_keywords) / keyword_target, 1.0),
            "agency_tech_spend": min(np.log1p(tech_spend) / np.log1p(spend_reference), 1.0),
            "value_fit": _fit_value_score(value, capability_profile),
            "agency_familiarity": min(familiarity / familiarity_reference, 1.0),
            "supplier_diversity": 0.5 if hhi is None else float(np.clip(1 - hhi, 0, 1)),
            "procurement_access": float(procurement_scores.get(method, 0.25)),
            "lead_time": lead_time_score,
        }
        weighted_score = sum(float(weights[name]) * components[name] for name in FIT_COMPONENTS)
        rows.append(
            {
                "tender_id": str(tender["tender_id"]),
                "unspsc_segment": segment,
                "agency": agency,
                "estimated_value_aud": None if value is None else float(value),
                "procurement_method": method,
                "as_of_date": as_of,
                "days_to_close": days_to_close,
                "agency_recent_tech_spend_aud": tech_spend,
                "agency_familiarity_count": familiarity,
                "supplier_hhi": hhi,
                "matched_keywords": matched_keywords,
                **components,
                "fit_score": int(np.clip(round(weighted_score * 100), 0, 100)),
            }
        )
    return pd.DataFrame(rows, columns=FIT_FEATURE_COLUMNS)
