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
