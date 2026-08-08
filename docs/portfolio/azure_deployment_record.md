# Azure Deployment Record — ProcureLens v1.0.0

ProcureLens v1.0.0 was deployed to an ephemeral Azure environment in Australia East on 8 August
2026. The deployment was used for production-path verification and portfolio evidence, then removed
after acceptance testing to keep the pay-as-you-go spend inside the project owner's USD 2–3 limit.
The release artefact and public GitHub release remain available; the temporary application URLs are
not expected to remain live.

## Deployed topology

- Azure Container Apps hosted the public FastAPI and Streamlit services with scale-to-zero and the
  internal-only MLflow tracking service.
- Azure Database for PostgreSQL Flexible Server used a burstable `Standard_B1ms` SKU, 32 GiB
  storage, no high availability and no geo-redundant backup.
- Azure Container Registry used the Basic tier. Runtime image pulls used a user-assigned managed
  identity with only `AcrPull`; registry admin credentials remained disabled.
- The Container Apps environment used a delegated VNet subnet and NAT Gateway. PostgreSQL accepted
  only the exact deployment egress address and the temporary restore workstation address; no broad
  `0.0.0.0` Azure-services firewall rule was used.
- Langfuse export and external LLM calls were disabled. The deterministic agent, local RAG corpus
  and registered models supplied the demo responses.

## Immutable images

| Service | OCI digest |
|---|---|
| API | `sha256:22cfba3885b216cfac18af0f6df2340db6494e1695bb8be96e666b43d6643b54` |
| Streamlit UI | `sha256:a741d9bf95d31b851daa5ae9093535a0764feaebfd91c8a93885d3ec9be35582` |
| MLflow | `sha256:503b5fdca486425174dab91b8b890f1f21af12029c60d282f9c54893fd5dea34` |

The MLflow service required one CPU and 2 GiB with a single worker. The initial 1 GiB revision was
replaced after an out-of-memory restart; the accepted revision reported ready with zero restarts.

## Readiness and release smoke

`/health/ready` verified the complete production dependency chain:

```json
{
  "status": "ok",
  "release_version": "1.0.0",
  "models": {
    "amendment_risk": {"ready": true, "version": "3"},
    "fit_scorer": {"ready": true, "version": "1.0.0"},
    "bid_agent": {"ready": true, "version": "1.1.0"}
  },
  "observability": {
    "provider": "langfuse",
    "enabled": false,
    "privacy": "sha256-only"
  },
  "data": {
    "ready": true,
    "snapshot_version": "1.0.0",
    "contract_count": 445029,
    "agency_count": 151,
    "last_award_date": "2025-12-30T22:56:09+00:00",
    "supplier_identifiers": "pseudonymised"
  }
}
```

The release smoke ran against the deployed API and restored PostgreSQL snapshot:

```json
{
  "release_version": "1.0.0",
  "contract_count": 445029,
  "fit_score": 94,
  "sql_route": "sql",
  "rag_sources": 4,
  "status": "pass"
}
```

The Streamlit health endpoint returned `ok`. Visual acceptance confirmed the opportunity feed,
model versions, agent-assisted analysis, evidence-linked brief generation and both brief download
controls.

## Security and failure-path checks

- The SQL agent role selected all 445,029 mart rows but a `CREATE TABLE` attempt failed because the
  role enforces read-only transactions.
- The amendment endpoint returned calibrated probability, risk band, model version `3` and SHAP
  drivers. A two-row batch succeeded; an empty batch returned HTTP 422.
- A prompt-injection attempt returned HTTP 400 with `prompt_injection_detected`.
- A request containing an email address did not echo that address in the response or JSONL audit
  log. Audit records contained input/output digests rather than raw prompts.
- The bid brief included `DRAFT — analyst review required`, model/scorer versions, pseudonymised SQL
  evidence and four CPR/ANAO citations with page numbers and official URLs.

## Cost and teardown

A USD 2 monthly resource-group budget with 50% and 90% notifications was installed before the
workload. Paid services were kept alive only for build, restore and acceptance testing. Azure Cost
Management had not yet posted the short-lived usage when teardown began, so this record does not
claim a final billed amount. Deletion of the entire `rg-procurelens-demo` resource group was then
started. PostgreSQL, registry, NAT Gateway and public IP were individually confirmed absent; the
empty resource-group control-plane record was still reporting `Deleting` when this evidence was
captured.
