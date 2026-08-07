# Amendment Risk EDA Findings

Scope: 445,029 unique AusTender contracting processes with initial award dates from 2019 through 2025. The target is true only when a later release is explicitly tagged `contractAmendment` and reports a value above the initial contract value. Reproducible calculations and charts are in the [executed EDA notebook](../notebooks/eda_amendment_risk.ipynb).

1. **The baseline upward-amendment rate is 20.19%.** There are 89,847 positive outcomes across 445,029 unique `ocid` values. Another 7,342 contracts have an explicit amendment release without an observed value increase, supporting the decision not to equate “multiple releases” with an upward amendment.
2. **The latest cohort is right-censored.** Annual rates are 18.9% (2019), 21.6% (2020), 22.8% (2021), 20.6% (2022), 19.7% (2023), 21.0% (2024), and 16.1% (2025). The low 2025 rate should not be read as a structural improvement because those contracts have had less time to amend.
3. **Procurement method is strongly associated with the outcome.** Open procurements have a 32.0% observed rate (62,652 / 195,489), compared with 20.1% for selective (636 / 3,169) and 10.8% for limited procurements (26,559 / 246,371).
4. **Risk increases monotonically with initial value band.** Rates are 11.1% for AUD 10k–80k, 31.7% for AUD 80k–1m, 38.7% for AUD 1m–10m, and 50.1% for AUD 10m+. The API cohort contains no initial values below AUD 10k, consistent with the reporting threshold represented in this extract.
5. **Service/construction categories have the highest large-sample rates.** UNSPSC segments 72, 81, and 80 show rates of 36.4% (n=13,536), 33.4% (n=47,780), and 30.3% (n=144,497), respectively. Segment 43 is much lower at 12.2% (n=38,312).
6. **Agency rates vary materially but require sample-size discipline.** Among agencies with at least 100 records, examples include the Australian War Memorial at 63.0% (n=100), the Department of Health, Disability and Ageing at 55.6% (n=2,532), and Services Australia at 34.5% (n=13,883). These are descriptive associations, not agency performance judgements.
7. **Contract values are extremely right-skewed.** Median initial value is AUD 57,571.80, the 99th percentile is AUD 7.80m, and the maximum is AUD 38.816bn. Log value and broad value bands are therefore preferable to raw value alone.
8. **Duration also has extreme outliers.** Median duration is 217 days and the 99th percentile is 2,028 days, while the maximum parsed duration is 66,633 days. The production feature builder converts negative/invalid durations to missing and the model pipeline median-imputes them.
9. **Six start dates and six end dates are outside pandas' supported timestamp range.** They remain valid source strings in PostgreSQL but are coerced to missing for analysis and modelling; this is explicitly surfaced rather than silently discarded.
10. **Core model fields pass the primary integrity checks.** At final mart grain there are no duplicate `ocid` values, null targets, negative award values, non-AUD values, or positive targets lacking an explicit amendment, positive uplift, and first-upward-amendment timestamp.
11. **Null amendment timestamps are expected outcome structure, not missing predictors.** `first_upward_amendment_date` is null for 79.81% of rows and `last_amendment_date` for 78.16%; neither is used as a contemporaneous model feature.
12. **Agency names still need machinery-of-government resolution.** Exact punctuation/case normalization found no collision groups, but fuzzy review surfaced four high-similarity pairs, including legacy/current Department of Infrastructure names and “Asbestos Safety and Eradication Agency” versus “Asbestos and Silica Safety and Eradication Agency.” Automatic merging would risk false joins, so these remain a manual mapping backlog.
13. **Leakage control must use both award time and outcome time.** Supplier counts include only awards strictly before the current award; prior amendment rates additionally count an amendment only if its first upward-amendment release was known before the current award. Same-timestamp awards are not treated as history.

## Sources and caveats

- [AusTender OCDS API](https://api.tenders.gov.au/ocds) and its [official implementation documentation](https://github.com/austender/austender-ocds-api)
- [dbt contract mart](../dbt/models/marts/fct_contracts.sql) for target construction
- [Feature builder](../src/procurelens/features/build_features.py) for point-in-time histories

The results are observational and should not be interpreted causally. Supplier-history variables may encode incumbency and reporting patterns. Recent cohorts require ongoing backfill and monitoring as additional amendment releases arrive.
