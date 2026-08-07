# ProcureLens 3–4 Minute Demo Script

Target duration: 3 minutes 35 seconds. Use the deterministic demo after `make demo`; do not depend
on an external LLM or a live AusTender request.

## Before recording

1. Run `make demo` and confirm the final smoke reports `status: pass`.
2. Open the Streamlit UI at 1440×900, collapse browser bookmarks and set zoom to 90–100%.
3. Select **Responsible AI assurance and governance advisory**.
4. Ensure the UI shows 445,029 contracts, both model versions and a green readiness state.
5. Keep API docs and MLflow open in background tabs only if time permits.

## 0:00–0:25 — Problem and trust promise

**Screen:** Opportunity Feed hero and dataset metrics.

> “ProcureLens is a federal procurement intelligence and bid agent built over AusTender. It helps a
> boutique AI advisory team find plausible work, inspect delivery risk and produce an evidence-backed
> bid/no-bid brief. The key design constraint is government-grade trust: no notebook-only model and
> no ungrounded chatbot.”

Point to **619,032 releases**, **445,029 contracts** and the curated-scenario disclaimer. Say clearly
that the feed is a repeatable demo catalogue, not a claim of live current tenders.

## 0:25–1:05 — Opportunity feed and fit ranking

**Action:** Filter to `strong_fit`, select the Responsible AI opportunity and open Decision Workspace.

> “Each opportunity is ranked 0 to 100 against a versioned capability profile: AI and data category
> fit, keywords, target value, agency history, supplier concentration, procurement accessibility and
> lead time. Because I do not have genuine bid outcomes, this is deliberately a transparent fit
> ranking—not a win probability.”

Point to the score band, top positive and negative reasons, and scorer version.

## 1:05–1:40 — Calibrated amendment risk

**Screen:** Risk panel and SHAP drivers.

> “The second signal is a calibrated XGBoost model for upward amendment risk. It uses a temporal
> holdout—training through 2023 and testing on 2024–2025—and all supplier history is point-in-time.
> The champion reached 0.8664 AUC, 0.6568 PR-AUC, 0.1042 Brier and 0.0316 ECE. The API returns the
> calibrated probability, band, exact registry version and SHAP drivers.”

Mention that an improved AUC candidate was correctly rejected when Brier worsened.

## 1:40–2:25 — Agent SQL and RAG

**Action:** Open Agent Copilot. Run shortcut **Agency incumbents**, then **Value for money rules**.

> “This is one governed LangGraph agent. SQL is parsed, SELECT-only, schema-allowlisted, timed,
> row-limited and executed with a read-only database role. The restored snapshot contains the real
> 445-thousand-row analytical shape but supplier identity is pseudonymised for distribution.”

When the RAG result appears:

> “For procurement guidance, the answer is extractive from a versioned CPR and ANAO corpus. Each
> passage preserves document, printed page, section and official URL, so the analyst can contest it.”

Point to route labels and sources.

## 2:25–3:05 — Brief and human review

**Action:** Open Bid Brief, click **Generate bid/no-bid brief**, scroll once, show download buttons.

> “The brief combines the selected tender, fit and risk signals, SQL evidence and governance
> sources. The DRAFT analyst-review warning is mandatory at both ends. The Markdown brief and JSON
> evidence pack can be downloaded, but the system cannot submit or approve a bid.”

## 3:05–3:35 — Production evidence and close

**Screen:** Assurance tab.

> “Quality is release-gated: 45 golden cases cover SQL, RAG grounding, routing, briefs and attacks;
> all required gates score 1.00. Tests maintain over 80 percent branch coverage, dbt passes 23 of 23,
> Langfuse traces never contain raw prompts, and Evidently produces drift reports. A single Docker
> command restores data and smoke-tests the system; Azure Container Apps configuration adds secrets,
> readiness probes and revision rollback. ProcureLens demonstrates the method I bring to applied AI:
> measurable usefulness, bounded autonomy and evidence for every decision.”

Stop before four minutes. If the agent response is slow, omit the MLflow tab rather than rushing the
human-review explanation.
