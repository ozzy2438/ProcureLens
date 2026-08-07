.PHONY: ingest-sample dbt-build train api ui test lint evals monitoring-smoke docker-quality \
	demo release-smoke snapshot-export release-package azure-validate

ingest-sample:
	python -m procurelens.ingestion.ocds_client --start 2025-01-01 --end 2025-01-31

dbt-build:
	cd dbt && dbt build --profiles-dir .

train:
	python -m procurelens.models.train_amendment_risk --promote-if-better
	python -m procurelens.models.train_fit_scorer

api:
	uvicorn procurelens.api.main:app --reload --port 8000

ui:
	PROCURELENS_API_URL=http://127.0.0.1:8000 streamlit run ui/app.py

test:
	pytest --cov=procurelens --cov-branch --cov-report=term-missing --cov-fail-under=80

lint:
	ruff check src tests && mypy src

evals:
	mkdir -p artifacts
	python evals/run_evals.py --gate --output artifacts/agent-eval.json --summary-output artifacts/agent-eval.md

monitoring-smoke:
	python -m procurelens.monitoring.smoke --output-dir artifacts/monitoring-smoke

docker-quality:
	docker compose --profile quality run --rm eval
	docker compose --profile quality run --rm monitoring-smoke

demo:
	./scripts/demo.sh

release-smoke:
	./scripts/release_smoke.sh

snapshot-export:
	./scripts/export_demo_snapshot.sh

release-package:
	./scripts/package_release.sh

azure-validate:
	./deploy/azure/validate.sh
