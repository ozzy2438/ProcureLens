#!/usr/bin/env bash
set -euo pipefail

release_version="${RELEASE_VERSION:-1.0.0}"
snapshot_path="data/snapshots/procurelens-marts-v${release_version}.dump"
api_port="${API_PORT:-8000}"
ui_port="${UI_PORT:-8501}"
mlflow_port="${MLFLOW_PORT:-5050}"

command -v docker >/dev/null
docker compose version >/dev/null

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

if [[ ! -f "${snapshot_path}" || ! -f "${snapshot_path}.sha256" ]]; then
  echo "The v${release_version} snapshot is not bundled." >&2
  echo "Use the release package or run scripts/export_demo_snapshot.sh first." >&2
  exit 2
fi

docker compose up -d db mlflow
docker compose --profile demo run --rm snapshot-restore
docker compose up -d --build api ui

attempt=0
until docker compose exec -T api python -c \
  'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health/ready")' \
  >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if (( attempt >= 60 )); then
    docker compose logs --no-color --tail=100 api
    echo "ProcureLens API did not become ready." >&2
    exit 3
  fi
  sleep 2
done

scripts/release_smoke.sh

echo "ProcureLens v${release_version} is ready."
echo "UI:     http://127.0.0.1:${ui_port}"
echo "API:    http://127.0.0.1:${api_port}/docs"
echo "MLflow: http://127.0.0.1:${mlflow_port}"
