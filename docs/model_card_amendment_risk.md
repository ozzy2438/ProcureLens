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
MLflow registry as `procurelens-amendment-risk`, version 1, alias `champion`.

## Metrics

Evaluated once on the untouched 2024–2025 holdout (n=120,500).

| Metric | Champion v1 |
|---|---:|
| AUC-ROC | 0.8664 |
| PR-AUC | 0.6568 |
| Brier score | 0.1042 |
| Expected calibration error (10 bins) | 0.0316 |
| Holdout positive rate | 0.1865 |

MLflow run: `0f65abcdfb60408ba60524fd73f1bc15`. Logged evaluation
artefacts include `calibration_curve.png`, `shap_summary.png`, and
`split_summary.json`.

## Fairness & limitations
- Public procurement data only; no personal data enters features.
- Supplier-level features may encode incumbency effects — outputs are review flags, not judgements.
- Not valid for state/territory procurement or contracts below AUD 10K reporting threshold.
- The 2025 cohort is right-censored because it has had less time to receive amendment releases.
- Machinery-of-government changes create agency-name variants that require a governed mapping table.
- Extreme contract values and durations exist; the pipeline log-transforms value and imputes invalid durations.

## Governance
MLflow registry, alias-based promotion, monthly retraining with challenger/champion comparison, drift monitoring (Evidently). Full lineage: data snapshot hash logged per training run. The champion was reloaded from the registry and produced a calibrated probability in a post-registration smoke test.
