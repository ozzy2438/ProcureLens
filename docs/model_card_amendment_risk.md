# Model Card — Amendment Risk Model

## Purpose
Predict the probability that an awarded Commonwealth contract will later be amended upward in value. Used to (a) flag procurement-integrity review candidates and (b) enrich bid/no-bid briefs.

## Intended use & users
Advisory analysts. Decision-support only — never an automated decision about any supplier or agency.

## Data
AusTender OCDS contract notices. Training grain: one contracting process (`ocid`) in
`analytics_marts.fct_contracts`, using initial award attributes and later explicit
`contractAmendment` releases to construct the target.

- Snapshot: 619,032 immutable releases; 445,029 contracts awarded in 2019–2025.
- Train: 324,529 awards through 2023; 67,369 positives (20.76%).
- Holdout: 120,500 awards in 2024–2025; 22,478 positives (18.65%).
- Data snapshot SHA-256: `17b2cfb6de00a595ce2c5ee09e864753c3163a4be13e2ebf181c5d9489a3e609`.

The split is time-based; no random split is used. Supplier histories include only
awards strictly before the scored contract, and amendment-rate numerators include
only outcomes already published by that time.

## Model

XGBoost classifier with class weighting, categorical one-hot encoding, numeric
median imputation, and three-fold isotonic calibration. Registered in the local
MLflow registry as `procurelens-amendment-risk`. Champion version 3 is a
proxy-backed, Docker-portable repackage of the validated v1 estimator; weights,
metrics, calibration, and evaluation artefacts are unchanged.

Training and serving both pin `xgboost==3.4.0`. New MLflow versions record that exact package
requirement and `xgboost_version` metadata so a serialized estimator is never loaded by a different
XGBoost runtime.

## Metrics

Evaluated once on the untouched 2024–2025 holdout (n=120,500).

| Metric | Champion v3 |
|---|---:|
| AUC-ROC | 0.8664 |
| PR-AUC | 0.6568 |
| Brier score | 0.1042 |
| Expected calibration error (10 bins) | 0.0316 |
| Holdout positive rate | 0.1865 |

MLflow run: `0e84c99faf6e4bc9a2d79e33bd3e1af1`. Logged evaluation
artefacts include `calibration_curve.png`, `shap_summary.png`, and
`split_summary.json`.

A full retrain candidate (v2) was intentionally rejected: AUC and ECE improved
slightly, but Brier worsened from 0.10419 to 0.10429. This is the expected safe
promotion behaviour, not a failed training run.

## Serving contract

- The champion and its SHAP explainers load once during FastAPI startup.
- Risk bands are `low` below 0.15, `medium` from 0.15 to below 0.35, and `high`
  from 0.35.
- SHAP values are averaged across calibration folds and aggregated back from
  one-hot columns to human-readable input features. They explain the underlying
  XGBoost margins; isotonic calibration is a later nonlinear mapping.
- Registry or inference failure returns HTTP 503 and marks the model unready in
  `/health`; no stub or fallback probability is emitted.

## Fairness & limitations
- Public procurement data only; no personal data enters features.
- Supplier-level features may encode incumbency effects — outputs are review flags, not judgements.
- Not valid for state/territory procurement or contracts below AUD 10K reporting threshold.
- The 2025 cohort is right-censored because it has had less time to receive amendment releases.
- Machinery-of-government changes create agency-name variants that require a governed mapping table.
- Extreme contract values and durations exist; the pipeline log-transforms value and imputes invalid durations.

## Governance
MLflow registry, alias-based promotion, monthly retraining with challenger/champion comparison and
Evidently 0.7.21 drift monitoring. Feature and calibrated-prediction PSI use a 0.2 alert threshold.
A challenger is promoted only when AUC is not lower, Brier is not worse, and ECE is at most 0.05.
The metrics, package version, decision reason, data snapshot hash, and alias change are logged.

## Release v1.0.0 verification

- Registry alias resolved at startup: `procurelens-amendment-risk@champion` → version 3.
- The model is loaded once per API process; a missing registry/model produces HTTP 503, never a
  placeholder score.
- Batch and single inference share the same Pydantic contract and calibrated estimator.
- `/health/ready` also verifies the bundled mart contains at least 445,000 contracts.
- The demo snapshot is for serving/SQL demonstration; model metrics remain those of the immutable
  2024–2025 holdout identified above.
- Human review remains mandatory. The output is associational risk triage and must not be used to
  infer supplier quality, agency conduct, causality or future contract value.
