.PHONY: ingest-sample dbt-build train api ui test lint evals

ingest-sample:
	python -m procurelens.ingestion.ocds_client --start 2025-01-01 --end 2025-01-31

dbt-build:
	cd dbt && dbt build --profiles-dir .

train:
	python -m procurelens.models.train_amendment_risk
	python -m procurelens.models.train_fit_scorer

api:
	uvicorn procurelens.api.main:app --reload --port 8000

ui:
	streamlit run ui/app.py

test:
	pytest --cov=procurelens

lint:
	ruff check src tests && mypy src

evals:
	python evals/run_evals.py
