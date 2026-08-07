# AI Use Case Impact Assessment — ProcureLens

Aligned to the Australian Government **Policy for the responsible use of AI in government** (v2.0, effective 15 Dec 2025) and the **National framework for the assurance of AI in government** (June 2024). Prepared in the format an agency assessment contact officer would expect.

## 1. Use case description
Decision-support platform over public AusTender data: ML risk/fit scoring and an LLM agent that answers procurement questions and drafts bid briefs. No automated decisions; all outputs reviewed by an analyst.

## 2. Threshold assessment
| Question | Answer |
|---|---|
| Does the use case affect individuals directly? | No — entity-level public procurement data |
| Personal information processed? | None by design; PII redaction guardrail enforced on all LLM I/O |
| Automated decision-making? | No — human-in-the-loop mandatory (draft banner) |
| Non-AI alternative considered? | Yes — manual analyst monitoring (baseline: ~6 hrs/week, misses closings) |
| Initial risk rating | **Low–Medium** → proceed with full assessment (below) |

## 3. Assessment against Australia's AI Ethics Principles
- **Human, societal & environmental wellbeing** — improves transparency of public spending analysis.
- **Fairness** — supplier features audited for incumbency bias; outputs framed as review flags.
- **Privacy protection & security** — public data only; Presidio redaction; least-privilege DB roles; secrets via environment, never in code.
- **Reliability & safety** — calibrated models, golden-set evals as CI gate, drift monitoring, rollback via registry aliases.
- **Transparency & explainability** — SHAP drivers surfaced with each prediction; RAG answers carry citations; model card published.
- **Contestability** — audit trail enables any output to be traced to sources and model version.
- **Accountability** — named model owner; every release signed off against eval thresholds.

## 4. Residual risks & mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| Hallucinated procurement rules in RAG answers | Medium | groundedness eval gate ≥ 0.80; citations required |
| Prompt injection via corpus documents | Low | sanitisation + injection flags + tool allowlist |
| Model drift after machinery-of-government changes | Medium | monthly drift report; retraining workflow |
| Amendment score mistaken for certainty | Medium | isotonic calibration, risk bands, Brier/ECE gates and model version shown |
| Fit rank mistaken for win probability | Medium | UI/API/model card explicitly describe a weighted ranking policy |
| Incumbency features reproduce supplier concentration | Medium | HHI/familiarity are explained, sensitivity-reviewed and never used autonomously |
| Personal information entered in chat | Low | Presidio plus deterministic AU patterns redact before any LLM boundary |
| Sensitive prompts exported to observability | Low | Langfuse receives hashes and approved metadata only; privacy smoke blocks release |
| SQL data exfiltration or mutation | Low | read-only role, SELECT-only AST, schema allowlist, timeout and row cap |
| Right-censored recent amendment outcomes | Medium | time split disclosed; monitor cohorts and avoid unsupported causal interpretation |

## 5. Data and privacy assessment

- **Primary source:** publicly reported AusTender OCDS releases and public government guidance.
- **Bundled release data:** dbt analytical marts only. Supplier identifiers are deterministically
  pseudonymised, supplier names are stable synthetic labels, descriptions are generic category
  labels and raw OCDS JSON is excluded.
- **Necessity:** no personal information is necessary for contract-level amendment risk, fit ranking
  or procurement-rule retrieval.
- **User input:** chat input can contain PII accidentally. It is redacted before optional LLM use;
  rejected injection attempts and audit events store digests rather than prompt text.
- **Observability:** raw prompts and outputs are prohibited. Trace metadata is allowlisted and
  subject to a dedicated leakage test.
- **Retention:** local audit JSONL and generated artefacts are operational records. Production
  retention and access must be set by the adopting organisation before deployment.

This reflects OAIC guidance that privacy obligations cover both AI inputs and outputs and that
personal information should not be entered into public generative-AI tools. ProcureLens still
requires an organisation-specific Privacy Impact Assessment if its scope changes to non-public or
person-level data.

## 6. Human oversight and contestability

The product supports triage; it cannot approve a bid, assess a supplier, modify a contract or take
administrative action. Every brief begins and ends with **DRAFT — analyst review required**. The
analyst must check tender currency, citations, assumptions, risk/fit reasons and commercial context.

Every material response exposes enough evidence to challenge it:

- model/scorer version, calibrated probability, band and SHAP/weighted drivers;
- document, printed page, section and official URL for RAG evidence;
- tool route and digest-only audit trail; and
- release/snapshot version in readiness output.

An analyst can reject the recommendation without changing data, and can escalate an incorrect
source, feature or routing decision to the corresponding owner.

## 7. Technical assurance controls and evidence

| Control objective | Implementation | Release evidence |
|---|---|---|
| Model validity | temporal holdout, calibration, PR-AUC and Brier/ECE | amendment model card + MLflow artefacts |
| Safe promotion | champion/challenger aliases with non-regression gates | registry tests + retraining workflow |
| Agent quality | 45 versioned production-path golden cases | deterministic eval JSON/Markdown |
| Grounded legal guidance | extractive response from retrieved chunks with citations | groundedness/citation gate |
| Data integrity | 23 dbt models/tests; versioned snapshot hash | dbt build + snapshot manifest |
| Privacy | PII redaction, no raw traces, pseudonymised snapshot | guardrail/privacy smoke tests |
| Security | read-only SQL, allowlists, secrets by reference | SQL tests + Bicep template |
| Monitoring | Langfuse metadata traces and Evidently PSI reports | monitoring smoke artefacts |
| Recoverability | MLflow alias and Container Apps revision rollback | operations runbook |

Current release thresholds are groundedness ≥0.80, SQL accuracy ≥0.85, tool routing ≥0.90,
guardrail pass rate 1.00 and branch coverage ≥80%. A failed threshold blocks release.

## 8. Accountability and lifecycle

| Role | Responsibility |
|---|---|
| Product owner | intended use, business acceptance and `DRAFT` review process |
| Model owner | data/feature approval, calibration, promotion and drift response |
| Agent owner | corpus currency, routing, guardrails and golden-set coverage |
| Platform owner | secrets, access, backups, health and rollback |
| Analyst | verifies each source and accepts/rejects the recommendation |

Reassessment is required after a material change to purpose, user group, data classification,
model family, LLM/provider, autonomy, decision impact, jurisdiction, corpus or deployment region.
Monthly monitoring reviews drift and retraining results; citation sources are reviewed when
Commonwealth Procurement Rules change. An AI/privacy/security incident triggers traffic rollback
and suspension of optional LLM/observability integrations until cleared.

## 9. Release decision

**Conditional approval for portfolio demonstration and analyst-supervised evaluation.** Residual
risk is low–medium because the system uses public/pseudonymised entity-level data, cannot take an
administrative action, fails closed on missing model/data dependencies, and requires human review.

This is not approval for production use by an Australian Government entity. Before operational
adoption, that entity must assign accountable officials, record the use case, confirm policy scope,
complete its own impact/privacy/security assessments, approve sources and capability weights, set
retention and incident processes, and perform an authorised deployment review.

## 10. Authoritative references

- [Policy for the responsible use of AI in government v2.0](https://www.digital.gov.au/ai/ai-in-government-policy)
  (effective 15 December 2025)
- [DTA AI use case impact assessment](https://www.digital.gov.au/ai/ai-in-government-policy/ai-use-case-impact-assessment)
- [National framework for assurance of AI in government](https://www.finance.gov.au/sites/default/files/2024-06/National-framework-for-the-assurance-of-AI-in-government.pdf)
- [OAIC privacy guidance for commercially available AI](https://www.oaic.gov.au/privacy/privacy-guidance-for-organisations-and-government-agencies/guidance-on-privacy-and-the-use-of-commercially-available-ai-products)
