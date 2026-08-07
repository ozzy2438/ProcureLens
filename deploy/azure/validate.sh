#!/usr/bin/env bash
set -euo pipefail

template="deploy/azure/main.bicep"
required=(
  "activeRevisionsMode: 'Multiple'"
  "path: '/health/live'"
  "path: '/health/ready'"
  "secretRef: 'database-url'"
  "secretRef: 'agent-database-url'"
  "latestRevision: true"
)

for marker in "${required[@]}"; do
  grep -Fq "${marker}" "${template}"
done

if command -v az >/dev/null; then
  az bicep build --file "${template}" --stdout >/dev/null
  echo "Azure Bicep compile: PASS"
else
  echo "Azure CLI is not installed; structural validation passed, Bicep compile skipped." >&2
fi
