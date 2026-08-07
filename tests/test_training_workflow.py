import pandas as pd

from procurelens.models.train_amendment_risk import _data_snapshot_hash, _xgboost_runtime_version
from procurelens.models.workflow_summary import render_summary


def _snapshot_rows() -> pd.DataFrame:
    rows = []
    for ocid, value, target in [("a", 100_000.0, False), ("b", 900_000.0, True)]:
        rows.append(
            {
                "ocid": ocid,
                "award_date": pd.Timestamp("2023-01-01", tz="UTC"),
                "was_amended_up": target,
                "agency": "AGENCY",
                "unspsc_category": "81",
                "procurement_method": "open",
                "value_band": "80k_to_1m",
                "award_value_aud": value,
                "log_award_value": 11.5,
                "contract_duration_days": 365.0,
                "is_eofy_award": 0,
                "has_confidentiality": 0,
                "supplier_prior_contract_count": 1,
                "supplier_prior_amendment_rate": 0.0,
                "supplier_agency_prior_contract_count": 0,
                "supplier_has_agency_history": 0,
            }
        )
    return pd.DataFrame(rows)


def test_training_snapshot_hash_is_independent_of_database_row_order():
    rows = _snapshot_rows()
    assert _data_snapshot_hash(rows) == _data_snapshot_hash(rows.iloc[::-1])


def test_training_and_serving_use_exact_pinned_xgboost_runtime():
    assert _xgboost_runtime_version() == "3.4.0"
    assert '"xgboost==3.4.0"' in open("pyproject.toml", encoding="utf-8").read()
    assert open("docker/Dockerfile.api", encoding="utf-8").read().startswith(
        "FROM python:3.12-slim"
    )


def test_workflow_summary_includes_metrics_and_promotion_decision():
    summary = render_summary(
        {
            "registered_model_version": "4",
            "run_id": "run-4",
            "data_snapshot_sha256": "abc",
            "train_rows": 10,
            "holdout_rows": 5,
            "promotion_accepted": False,
            "promotion_reason": "rejected: brier_not_worse",
            "holdout_auc_roc": 0.8,
            "holdout_pr_auc": 0.5,
            "holdout_brier_score": 0.2,
            "holdout_ece": 0.03,
        }
    )
    assert "0.8000" in summary
    assert "not promoted" in summary
    assert "brier_not_worse" in summary
