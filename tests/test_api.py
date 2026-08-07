from fastapi.testclient import TestClient

from procurelens.api.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_amendment_risk_stub_contract():
    payload = {
        "agency": "Department of Finance",
        "unspsc_category": "81110000",
        "procurement_method": "open",
        "contract_value_aud": 250000,
        "contract_duration_days": 365,
    }
    resp = client.post("/predict/amendment-risk", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert 0 <= body["probability"] <= 1
    assert body["risk_band"] in {"low", "medium", "high"}


def test_amendment_risk_rejects_bad_method():
    resp = client.post(
        "/predict/amendment-risk",
        json={
            "agency": "x",
            "unspsc_category": "1",
            "procurement_method": "sole-mate",
            "contract_value_aud": 1,
            "contract_duration_days": 1,
        },
    )
    assert resp.status_code == 422
