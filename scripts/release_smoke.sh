#!/usr/bin/env bash
set -euo pipefail

api_service_url="${SMOKE_API_URL:-http://127.0.0.1:8000}"

docker compose exec -T api python - "${api_service_url}" <<'PY'
import json
import sys
import urllib.request

base_url = sys.argv[1]


def request(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    with urllib.request.urlopen(
        urllib.request.Request(base_url + path, data=data, headers=headers), timeout=120
    ) as response:
        return response.status, json.loads(response.read())


status, ready = request("/health/ready")
assert status == 200 and ready["data"]["contract_count"] == 445029

status, fit = request(
    "/predict/fit-score",
    {
        "tender_id": "RELEASE-SMOKE",
        "unspsc_category": "81111500",
        "agency": "Department of Finance",
        "estimated_value_aud": 750000,
        "procurement_method": "open",
        "tender_title": "Responsible AI data platform advisory",
        "tender_description": "Generative AI, machine learning and data governance",
        "as_of_date": "2026-08-07",
        "close_date": "2026-09-15",
        "agency_recent_tech_spend_aud": 80000000,
        "agency_familiarity_count": 2,
        "supplier_hhi": 0.2,
    },
)
assert status == 200 and 0 <= fit["score"] <= 100

status, sql = request(
    "/agent/query",
    {
        "question": "Show the top 3 incumbent suppliers for this agency",
        "session_id": "release-sql-smoke",
        "context": {"agency": "Department of Finance", "limit": 3},
    },
)
assert status == 200 and sql["route"] == "sql" and "Supplier " in sql["answer"]

status, rag = request(
    "/agent/query",
    {
        "question": "What do the CPRs say about value for money?",
        "session_id": "release-rag-smoke",
    },
)
assert status == 200 and rag["route"] == "rag" and rag["sources"]

print(
    json.dumps(
        {
            "release_version": ready["release_version"],
            "contract_count": ready["data"]["contract_count"],
            "fit_score": fit["score"],
            "sql_route": sql["route"],
            "rag_sources": len(rag["sources"]),
            "status": "pass",
        },
        indent=2,
    )
)
PY
