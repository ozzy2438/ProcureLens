# Model Card — Opportunity Fit Scorer v1

## Purpose

Rank a new Commonwealth tender from 0 to 100 against an illustrative boutique AI
advisory capability profile. The score supports analyst triage and bid/no-bid
review; it is **not** a supervised win probability.

## Method

Version 1.0.0 is a deterministic weighted ranking policy configured in
[`config/capability_profile.yml`](../config/capability_profile.yml).

| Component | Weight |
|---|---:|
| UNSPSC segment match | 0.22 |
| Capability keyword match | 0.20 |
| Agency recent target-category spend | 0.12 |
| Estimated contract value fit | 0.15 |
| Prior agency familiarity | 0.12 |
| Supplier diversity (1 − HHI) | 0.08 |
| Procurement accessibility | 0.06 |
| Bid lead time | 0.05 |

Scores of 70–100 are `strong_fit`, 40–69 are `review`, and 0–39 are
`low_fit`. Each response carries the scorer version plus the three largest
positive and negative weighted signals.

## Point-in-time data

When contract history is available, agency spend, familiarity, and supplier HHI
use only awards strictly earlier than the tender's `as_of_date`. API callers may
instead supply already-snapshotted aggregates; they are responsible for preserving
the same point-in-time contract.

## Registry

- Registered model: `procurelens-fit-scorer`
- Registry version: 1 (`champion` and `challenger` aliases)
- Policy version: 1.0.0
- MLflow run: `b96f375a3eb844a38e2142e372ba8844`

## Limitations and governance

- There is no historical firm bid/outcome label, so the score must never be
  presented as likelihood of winning.
- Keyword matching is lexical, not semantic; synonyms outside the profile can be
  missed and tender boilerplate can inflate matches.
- The bundled profile is illustrative and must be approved and versioned for a
  real firm before operational use.
- Agency naming changes and incomplete supplier identity resolution can understate
  familiarity or distort HHI.
- Weights are judgement-based and require sensitivity analysis plus analyst
  feedback before any decision threshold is automated.

## Release v1.0.0 verification

- All API/UI outputs are clamped to 0–100 and carry policy/scorer version `1.0.0`.
- Equal inputs produce reasons in the same deterministic weight/name order.
- Historical agency spend, familiarity and HHI builders reject future awards through strict
  `award_date < as_of_date` point-in-time filtering.
- Feed opportunities use a versioned illustrative profile and are labelled `DEMO-`; no claim is
  made that they are current AusTender notices.
- Analysts must inspect each positive/negative reason and source tender before acting. No score
  threshold is approved for automatic bid/no-bid decisions.
