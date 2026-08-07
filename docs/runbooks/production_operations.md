# Production Operations Runbook

Release: `v1.0.0`
Runtime: Docker Compose (demo) or Azure Container Apps (deployment-ready)
Data classification: public Commonwealth procurement data with pseudonymised supplier fields in
the bundled demo snapshot

## Clean start

Prerequisites are Docker Desktop with Compose v2, 8 GB free memory and approximately 3 GB free
disk. No cloud or paid-LLM account is required for the deterministic demo.

```bash
cp .env.example .env
make demo
```

`make demo` verifies the snapshot SHA-256, restores exactly 445,029 contract rows, starts MLflow,
loads the champion model, starts the API and UI, waits for readiness and executes SQL, RAG and ML
smoke checks. Re-running it is idempotent. Open:

- UI: `http://127.0.0.1:8501`
- API docs: `http://127.0.0.1:8000/docs`
- MLflow: `http://127.0.0.1:5050`

If these ports are occupied, set `POSTGRES_PORT`, `MLFLOW_PORT`, `API_PORT` and `UI_PORT` in `.env`.
Container-to-container addresses do not change.

## Health and readiness

| Probe | Meaning | Expected |
|---|---|---|
| `GET /health/live` | API process is accepting HTTP | HTTP 200, independent of dependencies |
| `GET /health/ready` | champion model, fit scorer, agent and 445K mart are ready | HTTP 200; otherwise 503 |
| `GET /data/summary` | sanitized release snapshot identity | 445,029 contracts, 151 agencies |
| UI `/_stcore/health` | Streamlit process health | HTTP 200 |

Do not route production traffic on liveness alone. Readiness intentionally fails closed when
MLflow or the data snapshot is absent.

## Snapshot restore and recovery

The bundled archive is `data/snapshots/procurelens-marts-v1.0.0.dump`. It contains only dbt marts;
supplier identifiers are deterministically pseudonymised, names are synthetic labels and raw OCDS
payloads are excluded.

```bash
docker compose up -d db
docker compose --profile demo run --rm snapshot-restore
```

The restore job:

1. verifies the checked-in SHA-256;
2. restores into a temporary schema;
3. checks the exact row count;
4. swaps the temporary schema into `analytics_marts` in one transaction; and
5. grants only `SELECT` to `agent_readonly`.

An integrity or row-count failure exits before the schema swap. To recover, correct the archive or
credentials and rerun the same command. Never bypass the checksum or expected-row check.

## Secrets and environment

Copy `.env.example`; never commit `.env`. Replace every demo credential before any shared or cloud
environment.

| Variable | Required | Handling |
|---|---:|---|
| `POSTGRES_PASSWORD` | yes | local `.env`; Azure managed database secret |
| `AGENT_DB_PASSWORD` | yes | separate read-only identity; rotate independently |
| `DATABASE_URL` | yes | Azure Container Apps secret, never plain Bicep parameter files |
| `AGENT_DATABASE_URL` | yes | read-only Azure secret |
| `MLFLOW_TRACKING_URI` | yes | private/restricted endpoint in production |
| `OPENAI_API_KEY` | no | optional synthesis only; secret reference when enabled |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | no | both required to enable tracing |

Langfuse receives hashes, byte counts, route/tool metadata, latency, token count and calculated
cost only. It must not receive raw prompts, model outputs or PII. Leave tracing disabled if a safe
Langfuse destination has not been approved.

## Quality and release gates

```bash
make lint
make test
make dbt-build
make evals
make docker-quality
make azure-validate
make release-smoke
```

Release is blocked if branch coverage is below 80%, any dbt test fails, or groundedness, SQL
accuracy, routing or guardrail thresholds fail. The release smoke must exercise the restored data,
not an empty or fixture database.

## Azure preflight (no deployment)

The templates in `deploy/azure/` provision a Log Analytics workspace and two Container Apps with
startup/liveness/readiness probes, secret references, immutable image tags and multiple revisions.

```bash
az bicep build --file deploy/azure/main.bicep
az deployment group what-if \
  --resource-group <resource-group> \
  --template-file deploy/azure/main.bicep \
  --parameters environmentName=prod \
               imageTag=v1.0.0 \
               apiImageRepository=<registry>/procurelens-api \
               uiImageRepository=<registry>/procurelens-ui
```

Supply secure parameters through an approved secret store or deployment pipeline. Grant each
Container App managed identity `AcrPull` on the registry. Restore the versioned snapshot to managed
PostgreSQL and publish the MLflow champion before shifting traffic.

## Rollout and rollback

Container Apps uses multiple-revision mode. Deploy an immutable candidate tag, leave existing
traffic on the current revision, validate `/health/ready` plus the smoke suite, then shift traffic.

```bash
az containerapp revision list --name procurelens-prod-api --resource-group <resource-group> -o table
az containerapp ingress traffic set --name procurelens-prod-api --resource-group <resource-group> \
  --revision-weight <new-api-revision>=100
az containerapp ingress traffic set --name procurelens-prod-ui --resource-group <resource-group> \
  --revision-weight <new-ui-revision>=100
```

Rollback is a traffic operation, not an image rebuild:

```bash
az containerapp ingress traffic set --name procurelens-prod-api --resource-group <resource-group> \
  --revision-weight <previous-api-revision>=100
az containerapp ingress traffic set --name procurelens-prod-ui --resource-group <resource-group> \
  --revision-weight <previous-ui-revision>=100
```

Model rollback is independent: move the MLflow `champion` alias to the last accepted version, then
restart the API revision so startup loads that version exactly once. Snapshot rollback restores the
prior versioned archive before traffic is returned.

## Incident triage

1. Stop new traffic or shift it to the last healthy revision.
2. Capture release, snapshot and model versions from `/health/ready`; do not copy raw prompts.
3. Inspect Container Apps/system logs, hashed audit records and Langfuse metadata.
4. Classify whether the fault is data, registry/model, API, UI or external dependency.
5. Roll back the smallest affected versioned component.
6. Re-run readiness, release smoke and the relevant quality gate.
7. Record timeline, impact, evidence hashes, decision owner and corrective action.

For a suspected privacy or security incident, disable optional LLM and tracing integrations first,
preserve restricted logs and follow the organisation's incident-notification process.
