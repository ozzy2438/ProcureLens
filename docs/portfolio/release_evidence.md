# ProcureLens v1.0.0 Release Evidence

Validated locally on 7 August 2026. The immutable release was subsequently deployed and smoke-tested
on Azure on 8 August 2026; see [Azure deployment record](azure_deployment_record.md).

## Quality gates

| Gate | Result |
|---|---|
| Ruff | PASS |
| mypy | PASS — 31 source files |
| pytest | PASS — 123 tests |
| Branch coverage | PASS — 81.42% (threshold 80%) |
| dbt build | PASS — 23/23; `fct_contracts` rebuilt with 445,029 rows |
| Golden eval | PASS — 45 cases |
| Groundedness | 1.0000 (threshold 0.80) |
| SQL accuracy | 1.0000 (threshold 0.85) |
| Tool routing | 1.0000 (threshold 0.90) |
| Guardrail pass | 1.0000 (required 1.00) |
| Citation accuracy / brief quality | 1.0000 / 1.0000 informational |
| Docker observability smoke | PASS — 3 safe Langfuse spans; raw prompt/PII absent |
| Evidently drift smoke | PASS — HTML and JSON generated; intentional shifted batch detected |
| Docker Compose config | PASS |
| Azure Bicep compile | PASS — Bicep 0.46.1 via official Azure CLI container |

The pytest run emitted only upstream deprecation/pending-deprecation notices from
Starlette/httpx, Evidently/Litestar and SHAP/Matplotlib. No XGBoost serialization compatibility
warning was emitted; training and serving use XGBoost 3.4.0.

## Snapshot and release identity

- Raw source metrics: 619,032 immutable releases and 445,029 unique OCIDs.
- Bundled mart: 445,029 contracts and 151 agencies.
- PostgreSQL custom archive: 43,516,988 bytes.
- Snapshot SHA-256: `07546116dc514c12ef63cc3bbd35e30c1d30a9464f8c71431c56ebbfb3dd7f40`.
- Supplier fields: deterministic pseudonyms and stable synthetic names.
- Raw OCDS payloads: excluded.
- Amendment champion: version 3; AUC 0.8664, PR-AUC 0.6568, Brier 0.1042, ECE 0.0316.
- Fit scorer: policy/scorer version 1.0.0.

## Final runtime smoke

The release smoke executed inside the API container against the restored snapshot:

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

API `/health/ready` returned model versions risk `3`, fit `1.0.0`, agent `1.1.0`, snapshot
`1.0.0`, 445,029 contracts and 151 agencies. The UI `/_stcore/health` returned `ok`.

## Clean-package proof

The tarball was extracted into a new temporary directory with no `.env`. An isolated Compose
project, new PostgreSQL volume and alternate host ports ran:

```bash
COMPOSE_PROJECT_NAME=procurelens_clean_test \
POSTGRES_PORT=15433 MLFLOW_PORT=15050 API_PORT=18000 UI_PORT=18501 \
make demo
```

The command verified the archive checksum, restored exactly 445,029 contracts and 151 agencies,
loaded `procurelens-amendment-risk@champion`, started API/UI and passed the JSON smoke above. The
temporary containers, network and volume were removed after validation.

The first clean extraction exposed two portability defects that same-repository testing had masked:
an over-broad package exclude removed MLflow artefacts, and legacy MLflow metadata retained absolute
debug source paths. Both were fixed with root-anchored exclusions, a portable registry sanitation
step and clean-load validation. The fit pyfunc still predicts the logged example (`fit_score=90`)
after metadata sanitation.

## Visual acceptance

Real release screenshots were captured after live API scoring:

- `docs/screenshots/opportunity_feed.png`
- `docs/screenshots/decision_workspace.png`
- `docs/screenshots/agent_copilot.png`
- `docs/screenshots/bid_brief.png`

The same manual acceptance found and fixed a guardrail false positive where a nine-digit contract
amount was mistaken for a TFN. AU TFN/ABN redaction now requires identifier context; monetary-value,
ABN/TFN and full eval regressions pass.

## Approval boundary and known risks

- The v1.0.0 artefact was deployed to an ephemeral, VNet-connected Azure Container Apps environment,
  verified against managed PostgreSQL and removed after acceptance testing to bound pay-as-you-go
  cost. The temporary URL is intentionally no longer a persistent service.
- The feed uses curated and visibly labelled demo scenarios, not current live opportunities.
- The deterministic corpus is deliberately narrow; source currency requires operational ownership.
- Recent amendment outcomes remain right-censored, as documented in the model card.
- Human review remains mandatory. No bid, supplier or procurement decision is automated.
