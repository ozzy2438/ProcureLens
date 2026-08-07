# ADR-0001: Stack choices

Date: 2026-08-07 · Status: accepted

## Context
Six-week, single-developer, contract-style build that must read as production-grade to a government-focused AI consultancy.

## Decisions
1. **Postgres + dbt** over a cloud warehouse — zero-cost local dev, dbt tests give data quality evidence; swap to Snowflake is a profile change.
2. **XGBoost + calibration** over deep learning — tabular data, explainability required (SHAP), calibration matters more than raw AUC for risk bands.
3. **Single LangGraph agent + 4 tools** over multi-agent — smaller attack surface, easier evals, honest scope.
4. **RAG + tool-use, no fine-tuning** — corpus changes (CPR updates) must propagate immediately; fine-tuning adds cost and governance burden without accuracy need.
5. **Docker Compose** over Kubernetes — right-sized ops for a sub-10-person consultancy demo.

## Consequences
Clear upgrade paths documented per component; complexity deliberately deferred.
