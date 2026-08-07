# Observability and evaluation operations

## CI quality contract

`evals/golden_set.jsonl` contains 45 versioned scenarios across SQL, RAG, routing, bid briefs and
guardrails. The evaluator executes production code, not pre-filled scores or an external judge:

- SQL accuracy checks the selected reviewed template, bind parameters, agency filter, requested
  limit and allowlisted query fragments.
- RAG groundedness requires the expected corpus chunk, expected answer facts and extractive claims.
- Citation accuracy verifies document, printed page and official Finance/ANAO URL metadata.
- Routing compares the deterministic production router with the expected governed tool.
- Brief quality checks the mandatory DRAFT banner, recommendation policy, model/market/governance
  sections, citations and one-page word budget.
- Guardrail cases exercise real Presidio/regex redaction and prompt-injection blocking.

Required merge gates are groundedness ≥0.80, SQL accuracy ≥0.85, routing ≥0.90 and guardrail pass
rate 1.00. `python evals/run_evals.py --gate` returns exit code 1 when any observed rate misses its
threshold. JSON and Markdown outputs are retained by GitHub Actions for 90 days.

## Langfuse privacy contract

Set `LANGFUSE_TRACING_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and
`LANGFUSE_HOST` to export traces. Disabled or unavailable tracing is non-blocking.

Allowed telemetry:

- agent, tool, retriever, guardrail and generation observation types;
- SHA-256 input/output fingerprints and byte counts;
- hashed session identifier;
- status, latency, source count, model/release/environment;
- input/output/total tokens and configured input/output/total cost.

Raw prompts, answers, tool rows, tender context and PII are prohibited. The observer constructs
only fingerprints, and the Langfuse SDK mask hashes any unexpected object. The Docker monitoring
smoke uses the real SDK and an isolated OpenTelemetry exporter, then scans every completed span for
the known raw prompt and email before reporting success.

## Evidently drift

`python -m procurelens.monitoring.drift` accepts matching CSV, Parquet, JSON or JSONL reference and
current batches. Both must contain `prediction` unless another column is selected. The report uses
PSI, a 0.2 per-column threshold and a 0.5 dataset drift-share threshold. Large datasets are sampled
deterministically at up to 100,000 rows.

Outputs:

- interactive Evidently HTML;
- full Evidently JSON;
- compact `.summary.json` containing drifted column count/share and prediction drift.

Run all local checks with `make test`, `make evals` and `make monitoring-smoke`. Run the isolated
container equivalents with `make docker-quality`.
