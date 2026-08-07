# ProcureLens Job Application Pack

## CV / application description (56 words)

Built ProcureLens, a production-grade federal procurement intelligence platform over 619K AusTender
releases and 445K contracts. Delivered leakage-safe calibrated XGBoost, MLflow promotion governance,
an explainable fit ranking, a guarded LangGraph SQL/RAG/ML agent, privacy-safe observability and a
45-case CI eval gate. Packaged a one-command pseudonymised Docker demo with Azure Container Apps
deployment and rollback configuration.

## LinkedIn / portfolio description

ProcureLens converts Australian Government procurement data into an analyst-supervised opportunity
feed, amendment-risk signal and cited bid/no-bid brief. The interesting part is the assurance layer:
temporal validation and calibration, point-in-time features, safe MLflow champion promotion,
SELECT-only SQL, page-level CPR/ANAO citations, prompt/PII controls, digest-only traces, drift reports
and CI gates. It ships as a repeatable 445K-row Docker demo with no live-data claim or automated bid
decision.

## 90-second interview narrative

> “I wanted a portfolio project that looked like a real AI consultancy engagement rather than a
> notebook. The client problem was a boutique advisory firm trying to triage federal opportunities
> and produce defensible bid decisions. I ingested 619,032 AusTender OCDS releases and modelled
> 445,029 contract processes with dbt. The amendment target depended on preserving multiple releases
> per OCID, and I built supplier features point-in-time before using a 2024-plus temporal holdout.
>
> The calibrated XGBoost champion achieved 0.8664 AUC and 0.1042 Brier. Registry promotion is stricter
> than AUC: a challenger was rejected because Brier worsened. Since the firm had no real win labels,
> I made opportunity fit an explainable weighted ranking rather than mislabelling it as win
> probability.
>
> I then built one LangGraph agent with governed SQL, cited CPR/ANAO retrieval, model tools and a
> mandatory draft brief. Every LLM boundary has PII and injection controls; audit and Langfuse store
> hashes rather than raw prompts. Forty-five production-path golden cases gate CI. Finally I packaged
> a pseudonymised 445K-row snapshot, one-command Docker demo and revision-based Azure rollback.
> The project shows how I balance useful GenAI with data lineage, evaluation and accountability.”

## STAR prompts and evidence

### “Tell me about a difficult data-quality decision.”

- **Situation:** OCDS has many releases per contracting process.
- **Task:** build an amendment target without deleting or leaking its evidence.
- **Action:** made immutable release ID the raw idempotency key, retained repeated OCIDs, validated
  explicit amendment tags in dbt and enforced history strictly before scoring time.
- **Result:** 619,032 releases became 445,029 contract-grain rows with 23/23 data tests and a 20.19%
  overall target rate.

### “How did you prevent a model metric from driving the wrong decision?”

- **Situation:** a challenger slightly improved AUC and ECE but degraded Brier.
- **Task:** protect the meaning of a probability served to analysts.
- **Action:** encoded non-regression on both AUC and Brier plus an ECE ceiling before any champion
  alias mutation; logged the comparison and decision.
- **Result:** the existing champion remained active, demonstrating a safe failure rather than a
  vanity-metric promotion.

### “How do you make an agent safe?”

- **Situation:** an agent can be induced to query too broadly, repeat PII or invent rules.
- **Task:** preserve useful SQL/RAG/ML workflows with bounded authority.
- **Action:** deterministic routing, parsed SELECT-only SQL, database read-only role, schema/row/time
  limits, extractive cited RAG, input/output redaction and injection checks, digest-only audit and
  45 golden cases.
- **Result:** SQL, grounding, routing and guardrail gates all reached 1.00 in the release baseline.

## Questions to invite

- Why temporal validation and calibration changed the model design.
- Why the fit scorer is not a supervised probability.
- How champion rollback differs from Container Apps revision rollback.
- What would change for a real agency: identity resolution, approved corpus, privacy/security impact
  assessments, managed services, private networking and analyst feedback loops.

## Candid limitations to volunteer

- The opportunity feed contains curated scenarios for repeatability; production would add a current
  OCDS/open-tender ingestion contract.
- The RAG corpus is intentionally small and approved, not a general web knowledge base.
- 2025 amendment labels are right-censored.
- Azure configuration is compile-validated, not deployed in this local task.
- The bundled supplier fields are pseudonymised; production identity access would require separate
  governance and access controls.
