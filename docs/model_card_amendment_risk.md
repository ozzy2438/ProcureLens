# Model Card — Amendment Risk Model

## Purpose
Predict the probability that an awarded Commonwealth contract will later be amended upward in value. Used to (a) flag procurement-integrity review candidates and (b) enrich bid/no-bid briefs.

## Intended use & users
Advisory analysts. Decision-support only — never an automated decision about any supplier or agency.

## Data
AusTender contract notices (public, CC-BY). Training grain: `marts.fct_contracts`.
Time-based split: train ≤ 2023, holdout 2024+.

## Metrics (updated each release)
| Metric | Champion |
|---|---|
| AUC-ROC | TBD |
| PR-AUC | TBD |
| Brier score | TBD |
| Calibration error (ECE) | TBD |

## Fairness & limitations
- Public procurement data only; no personal data enters features.
- Supplier-level features may encode incumbency effects — outputs are review flags, not judgements.
- Not valid for state/territory procurement or contracts below AUD 10K reporting threshold.

## Governance
MLflow registry, alias-based promotion, monthly retraining with challenger/champion comparison, drift monitoring (Evidently). Full lineage: data snapshot hash logged per training run.
