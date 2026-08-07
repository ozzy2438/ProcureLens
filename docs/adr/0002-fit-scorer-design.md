# ADR 0002 — Explainable Weighted Opportunity Fit Ranking

**Status:** Accepted
**Date:** 2026-08-07

## Context

ProcureLens needs to rank new tenders for a boutique AI advisory firm, but the
available AusTender corpus does not identify which opportunities the firm bid for
or won. Training a classifier and labelling its output “win probability” would
therefore create a false supervised target and misleading calibration claims.

## Decision

Use a deterministic 0–100 weighted ranking model, versioned through a YAML
capability profile and MLflow. The eight component weights are:

- category match 0.22;
- capability keywords 0.20;
- estimated value fit 0.15;
- recent agency technology/data spend 0.12;
- agency familiarity 0.12;
- supplier diversity 0.08;
- procurement accessibility 0.06; and
- bid lead time 0.05.

The weights sum to one and are validated at runtime. Inputs derived from contract
history must be calculated strictly before the tender `as_of_date`. Scores map to
`strong_fit` (≥70), `review` (≥40), and `low_fit` (<40). Explanations rank weighted
component contributions and deficits with deterministic tie-breaking.

## Consequences

### Positive

- The output is transparent, testable, and defensible without inventing labels.
- A profile change is reviewable as configuration and produces a new scorer
  version.
- Point-in-time feature logic and deterministic reasons are unit-testable.

### Negative

- Weights encode advisory judgement and are not statistically estimated.
- Lexical keyword matching misses semantic equivalents and can match boilerplate.
- API-supplied aggregate history must be governed upstream when the service does
  not calculate it directly from the mart.

## Revisit trigger

Replace or augment the ranking policy only after collecting a governed dataset of
opportunities seen, bid/no-bid decisions, submitted bids, and outcomes. At that
point a supervised ranking or calibrated win model can be evaluated without
reusing post-decision information.
