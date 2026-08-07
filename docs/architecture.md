# Architecture

## Design goals

1. **Production over prototype** — every component has tests, versioning, monitoring and a rollback path.
2. **Government-grade trust** — PII redaction, auditability, explainability, human-in-the-loop.
3. **Deliberately small** — one agent with good tools; Docker Compose, not Kubernetes; RAG + tool-use, not fine-tuning.

## Components

### 1. Data platform
- `ingestion/ocds_client.py` pulls OCDS releases from the AusTender API into `raw.contract_notices` (JSONB, idempotent on immutable release `id`; `ocid` is intentionally non-unique so amendments are retained).
- `ingestion/load_historical.py` backfills 1999+ CSV dumps from data.gov.au.
- dbt: `staging` flattens OCDS into typed views; `marts` builds `fct_contracts` (model training grain, amendment outcomes) and `dim_agencies` (spend aggregates). Data tests enforce uniqueness, nullability and value ranges.
- Weekly GitHub Actions ingest keeps data fresh.

### 2. ML layer
- **Amendment Risk Model** — XGBoost + isotonic calibration; time-based split; metrics AUC / PR-AUC / Brier; SHAP artefacts logged to MLflow. Registry alias `champion` drives serving; monthly retraining promotes only on improvement.
- **Opportunity Fit Scorer** — winnability score for open tenders vs the firm's capability profile.
- Served by FastAPI (`api/main.py`) with Pydantic validation; responses always include `model_version`.
- Drift: Evidently reports monthly; PSI > 0.2 on key features raises an alert.

### 3. Agent layer
- LangGraph single-agent graph with four tools (SQL / RAG / ML / brief).
- SQL tool runs against a **read-only role** scoped to `marts.*`, SELECT-only, row-limited.
- RAG corpus: Commonwealth Procurement Rules + ANAO procurement audits; all answers carry citations.
- Briefs are always marked **DRAFT — analyst review required**.

### 4. Trust layer
- Presidio-based PII redaction wraps every LLM input/output (regex fallback for AU identifiers).
- Append-only JSONL audit trail per agent step: timestamp, tool, input digest, sources.
- Prompt-injection heuristics on user input and tool outputs.
- Eval harness (golden set, ragas groundedness + SQL accuracy) runs as a **CI merge gate**.

## Environments

| Env | Runtime | Notes |
|---|---|---|
| dev | Docker Compose | Postgres + MLflow + API + UI |
| prod | Azure Container Apps (or Fly.io) | single region, managed Postgres |

## Threat model highlights

- Injection via tender documents (RAG corpus) → tool-output sanitisation + injection flags.
- Data exfiltration via SQL tool → read-only role, schema allowlist, row caps, audit log.
- Model misuse → calibrated probabilities with bands, never raw scores presented as certainty.
