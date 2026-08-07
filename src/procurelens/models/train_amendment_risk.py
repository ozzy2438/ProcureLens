"""Train the contract Amendment Risk model.

Pipeline: features -> XGBoost -> isotonic calibration -> SHAP artefacts ->
MLflow logging -> (optional) registry promotion when beating champion on
time-based holdout AUC + Brier score.
"""
from __future__ import annotations

import argparse
import logging

logger = logging.getLogger(__name__)

EXPERIMENT = "amendment_risk"
REGISTERED_MODEL = "procurelens-amendment-risk"


def train(promote_if_better: bool = False) -> None:
    # TODO(week-2/3):
    # 1. load features (time-based split: train <= 2023, test 2024+)
    # 2. xgboost.XGBClassifier + CalibratedClassifierCV(method="isotonic")
    # 3. metrics: AUC, PR-AUC, Brier, calibration curve
    # 4. shap.TreeExplainer summary -> log artefact
    # 5. mlflow.log_* + register; promote alias "champion" if better
    raise NotImplementedError


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--promote-if-better", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    train(promote_if_better=args.promote_if_better)
