# ProcureLens v1.0.0 Production Release Checklist

This checklist records the v1.0.0 release and its ephemeral Azure acceptance deployment.

## Scope and integrity

- [x] Release version is `1.0.0` in package metadata, API and UI.
- [x] Snapshot manifest declares 445,029 contracts and 151 agencies.
- [x] Snapshot archive checksum is verified before every restore.
- [x] Supplier identifiers/names are pseudonymised and raw releases are excluded.
- [x] Curated opportunities are labelled as demo scenarios, not live tenders.
- [x] The release tag remains immutable; post-release deployment evidence is recorded separately.

## Product flows

- [x] Opportunity feed supports filter, sort and visible fit/risk scores.
- [x] Decision workspace shows risk bands, reasons, SHAP drivers and model versions.
- [x] Agent chat routes SQL, RAG, ML and brief requests.
- [x] Bid/no-bid brief is visibly marked `DRAFT — analyst review required`.
- [x] Markdown brief and JSON evidence pack downloads are available.
- [x] Sources and official URLs are shown beside grounded answers.

## Data, ML and agent controls

- [x] API readiness requires both ML models, agent and 445K data snapshot.
- [x] Amendment champion: AUC 0.8664, PR-AUC 0.6568, Brier 0.1042, ECE 0.0316.
- [x] Challenger promotion cannot worsen AUC or Brier and requires ECE ≤ 0.05.
- [x] Fit scorer is represented as deterministic fit ranking, never win probability.
- [x] SQL tool is SELECT-only, allowlisted, read-only, timed and row-limited.
- [x] RAG responses include document/page/URL citations.
- [x] PII redaction, prompt-injection blocking and digest-only audit logging are active.

## Verification evidence

- [x] `ruff` passes.
- [x] `mypy` passes.
- [x] pytest passes with branch coverage ≥80%.
- [x] dbt build passes 23/23.
- [x] 45-case eval gate passes all four required thresholds.
- [x] Docker quality profile passes eval and monitoring smoke.
- [x] Bicep compiles and Docker Compose config validates.
- [x] Clean-package `make demo` restores data and passes final smoke.
- [x] UI screenshots have been captured from the release candidate.
- [x] Secret/PII/local-path audit passes.

Command outputs and exact metrics supporting these checks are recorded in
`docs/portfolio/release_evidence.md`.

## Deployment acceptance

- [x] Immutable image tags, probes, managed identities and multiple revisions are configured.
- [x] Secrets and rollback procedures are documented.
- [x] Human release owner approved the target subscription and a USD 2–3 maximum spend.
- [x] The distributed snapshot remained pseudonymised; external LLM and Langfuse export were disabled.
- [x] Azure deployment, managed-data restore, API/UI smoke and failure-path checks passed.
- [x] Paid Azure resources were confirmed removed after visual acceptance; group metadata deletion
  was still completing asynchronously.

Detailed operational evidence is in
[`docs/portfolio/azure_deployment_record.md`](portfolio/azure_deployment_record.md).
