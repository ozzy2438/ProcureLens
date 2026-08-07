"""Train, calibrate and register the contract Amendment Risk model."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from procurelens.config import get_settings
from procurelens.features.build_features import build_amendment_features

logger = logging.getLogger(__name__)

EXPERIMENT = "amendment_risk"
REGISTERED_MODEL = "procurelens-amendment-risk"
TRAIN_END_YEAR = 2023
HOLDOUT_START_YEAR = 2024
RANDOM_STATE = 42

CATEGORICAL_FEATURES = [
    "agency",
    "unspsc_category",
    "procurement_method",
    "value_band",
]
NUMERIC_FEATURES = [
    "award_value_aud",
    "log_award_value",
    "contract_duration_days",
    "is_eofy_award",
    "has_confidentiality",
    "supplier_prior_contract_count",
    "supplier_prior_amendment_rate",
    "supplier_agency_prior_contract_count",
    "supplier_has_agency_history",
]
MODEL_FEATURES = [*CATEGORICAL_FEATURES, *NUMERIC_FEATURES]


def _load_contracts(table_name: str) -> pd.DataFrame:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", table_name):
        raise ValueError("feature table must be a schema-qualified SQL identifier")
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        return pd.read_sql_query(text(f"select * from {table_name}"), engine)
    finally:
        engine.dispose()


def _data_snapshot_hash(features: pd.DataFrame) -> str:
    columns = ["ocid", "award_date", "was_amended_up", *MODEL_FEATURES]
    row_hashes = pd.util.hash_pandas_object(features[columns], index=False).values
    return hashlib.sha256(row_hashes.tobytes()).hexdigest()


def _expected_calibration_error(y_true: np.ndarray, probabilities: np.ndarray) -> float:
    edges = np.linspace(0.0, 1.0, 11)
    bin_ids = np.clip(np.digitize(probabilities, edges[1:-1]), 0, 9)
    error = 0.0
    for bin_id in range(10):
        mask = bin_ids == bin_id
        if mask.any():
            error += float(mask.mean()) * abs(
                float(y_true[mask].mean()) - float(probabilities[mask].mean())
            )
    return error


def _log_calibration_plot(
    y_true: np.ndarray, probabilities: np.ndarray, artifact_dir: Path
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.calibration import calibration_curve

    observed, predicted = calibration_curve(y_true, probabilities, n_bins=10, strategy="quantile")
    figure, axis = plt.subplots(figsize=(6.5, 5.5))
    axis.plot([0, 1], [0, 1], linestyle="--", color="grey", label="perfect calibration")
    axis.plot(predicted, observed, marker="o", label="isotonic XGBoost")
    axis.set(xlabel="Mean predicted probability", ylabel="Observed amendment rate")
    axis.set_title("Amendment-risk calibration — 2024+ holdout")
    axis.legend()
    axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(artifact_dir / "calibration_curve.png", dpi=160)
    plt.close(figure)


def _log_shap_plot(calibrated_model: Any, holdout: pd.DataFrame, artifact_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import shap

    fitted_pipeline = calibrated_model.calibrated_classifiers_[0].estimator
    preprocessor = fitted_pipeline.named_steps["preprocessor"]
    classifier = fitted_pipeline.named_steps["classifier"]
    sample = holdout.sample(min(1_000, len(holdout)), random_state=RANDOM_STATE)
    transformed = preprocessor.transform(sample)
    if hasattr(transformed, "toarray"):
        transformed = transformed.toarray()
    feature_names = preprocessor.get_feature_names_out()
    explanation = shap.TreeExplainer(classifier)(transformed)
    shap.summary_plot(
        explanation.values,
        transformed,
        feature_names=feature_names,
        max_display=20,
        show=False,
    )
    plt.gcf().set_size_inches(9, 7)
    plt.tight_layout()
    plt.savefig(artifact_dir / "shap_summary.png", dpi=160, bbox_inches="tight")
    plt.close()


def _promote_when_better(client: Any, version: str, run_id: str, metrics: dict[str, float]) -> None:
    """Assign the champion alias only when both ranking and calibration improve."""
    try:
        champion = client.get_model_version_by_alias(REGISTERED_MODEL, "champion")
    except Exception:  # MLflow raises when the alias has not been created yet.
        client.set_registered_model_alias(REGISTERED_MODEL, "champion", version)
        return

    champion_run = client.get_run(champion.run_id)
    champion_metrics = champion_run.data.metrics
    if metrics["holdout_auc_roc"] > champion_metrics.get("holdout_auc_roc", -np.inf) and metrics[
        "holdout_brier_score"
    ] < champion_metrics.get("holdout_brier_score", np.inf):
        client.set_registered_model_alias(REGISTERED_MODEL, "champion", version)
        logger.info("promoted run %s (version %s) to champion", run_id, version)


def train(
    promote_if_better: bool = False,
    contracts: pd.DataFrame | None = None,
    tracking_uri: str | None = None,
    table_name: str | None = None,
) -> dict[str, float]:
    """Train on awards through 2023 and evaluate once on the 2024+ holdout."""
    import mlflow
    import mlflow.sklearn
    from mlflow.models import infer_signature
    from mlflow.tracking import MlflowClient
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder
    from xgboost import XGBClassifier

    settings = get_settings()
    source_table = table_name or settings.amendment_feature_table
    contracts = _load_contracts(source_table) if contracts is None else contracts.copy()
    features = build_amendment_features(contracts)
    if features.empty:
        raise ValueError("no contracts available for amendment-risk training")

    award_year = features["award_date"].dt.year
    train_mask = award_year.le(TRAIN_END_YEAR)
    holdout_mask = award_year.ge(HOLDOUT_START_YEAR)
    if not train_mask.any() or not holdout_mask.any():
        raise ValueError("time split requires awards in both <=2023 and 2024+ periods")

    x_train = features.loc[train_mask, MODEL_FEATURES]
    y_train = features.loc[train_mask, "was_amended_up"].astype(int)
    x_holdout = features.loc[holdout_mask, MODEL_FEATURES]
    y_holdout = features.loc[holdout_mask, "was_amended_up"].astype(int)
    if y_train.nunique() < 2 or y_holdout.nunique() < 2:
        raise ValueError("both time periods must contain amended and non-amended contracts")

    minority_count = int(y_train.value_counts().min())
    calibration_cv = min(3, minority_count)
    if calibration_cv < 2:
        raise ValueError("at least two training examples are required in each target class")
    positive_count = int(y_train.sum())
    negative_count = int(len(y_train) - positive_count)
    scale_pos_weight = negative_count / positive_count

    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "one_hot",
                OneHotEncoder(handle_unknown="ignore", min_frequency=10, sparse_output=True),
            ),
        ]
    )
    numeric_pipeline = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])
    preprocessor = ColumnTransformer(
        transformers=[
            ("categorical", categorical_pipeline, CATEGORICAL_FEATURES),
            ("numeric", numeric_pipeline, NUMERIC_FEATURES),
        ]
    )
    base_pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "classifier",
                XGBClassifier(
                    n_estimators=300,
                    max_depth=5,
                    learning_rate=0.05,
                    subsample=0.8,
                    colsample_bytree=0.8,
                    reg_lambda=1.0,
                    scale_pos_weight=scale_pos_weight,
                    eval_metric="logloss",
                    random_state=RANDOM_STATE,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    calibrated_model = CalibratedClassifierCV(
        estimator=base_pipeline,
        method="isotonic",
        cv=calibration_cv,
    )
    calibrated_model.fit(x_train, y_train)
    probabilities = calibrated_model.predict_proba(x_holdout)[:, 1]
    y_holdout_array = y_holdout.to_numpy()
    metrics = {
        "holdout_auc_roc": float(roc_auc_score(y_holdout, probabilities)),
        "holdout_pr_auc": float(average_precision_score(y_holdout, probabilities)),
        "holdout_brier_score": float(brier_score_loss(y_holdout, probabilities)),
        "holdout_ece": _expected_calibration_error(y_holdout_array, probabilities),
        "holdout_positive_rate": float(y_holdout.mean()),
    }

    mlflow.set_tracking_uri(tracking_uri or settings.mlflow_tracking_uri)
    mlflow.set_experiment(EXPERIMENT)
    with tempfile.TemporaryDirectory(prefix="procurelens-amendment-") as temp_dir:
        artifact_dir = Path(temp_dir)
        _log_calibration_plot(y_holdout_array, probabilities, artifact_dir)
        _log_shap_plot(calibrated_model, x_holdout, artifact_dir)
        split_summary = {
            "train_end_year": TRAIN_END_YEAR,
            "holdout_start_year": HOLDOUT_START_YEAR,
            "train_rows": len(x_train),
            "holdout_rows": len(x_holdout),
            "train_positive_rate": float(y_train.mean()),
            "holdout_positive_rate": float(y_holdout.mean()),
            "source_table": source_table,
            "data_snapshot_sha256": _data_snapshot_hash(features),
        }
        (artifact_dir / "split_summary.json").write_text(
            json.dumps(split_summary, indent=2), encoding="utf-8"
        )

        with mlflow.start_run() as run:
            mlflow.log_params(
                {
                    "estimator": "xgboost.XGBClassifier",
                    "calibration": "isotonic",
                    "calibration_cv": calibration_cv,
                    "train_end_year": TRAIN_END_YEAR,
                    "holdout_start_year": HOLDOUT_START_YEAR,
                    "n_estimators": 300,
                    "max_depth": 5,
                    "learning_rate": 0.05,
                    "scale_pos_weight": scale_pos_weight,
                    "data_snapshot_sha256": split_summary["data_snapshot_sha256"],
                }
            )
            mlflow.log_metrics(metrics)
            mlflow.log_artifacts(str(artifact_dir), artifact_path="evaluation")
            signature = infer_signature(x_holdout.head(20), probabilities[:20])
            model_info = mlflow.sklearn.log_model(
                sk_model=calibrated_model,
                artifact_path="model",
                serialization_format="cloudpickle",
                registered_model_name=REGISTERED_MODEL,
                signature=signature,
                input_example=x_holdout.head(5),
            )
            run_id = run.info.run_id

    logger.info("holdout metrics: %s", metrics)
    if promote_if_better:
        version = getattr(model_info, "registered_model_version", None)
        if version is None:
            raise RuntimeError("MLflow did not return a registered model version")
        _promote_when_better(MlflowClient(), str(version), run_id, metrics)
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--promote-if-better", action="store_true")
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--table", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    train(
        promote_if_better=args.promote_if_better,
        tracking_uri=args.tracking_uri,
        table_name=args.table,
    )
