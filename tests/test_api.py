"""Tests for the Phase 4 REST API routes."""

import json
import pytest

from app import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "OPENAI_API_KEY": "test-key"})
    with app.test_client() as c:
        yield c


VALID_PAYLOAD = {
    "tax_year": 2024,
    "filing_status": "single",
    "taxpayer_age": 35,
    "number_of_dependents": 0,
    "income_sources": [
        {
            "source_type": "W-2",
            "employer_or_payer": "ACME Corp",
            "gross_amount": 75000.0,
            "federal_tax_withheld": 12000.0,
        }
    ],
}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/v1/calculate
# ---------------------------------------------------------------------------


def test_calculate_returns_200(client):
    resp = client.post(
        "/api/v1/calculate",
        data=json.dumps(VALID_PAYLOAD),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "federal_tax_owed" in body
    assert "taxable_income" in body
    assert body["phase"] == "Phase 1 – Tax Calculation"


def test_calculate_invalid_payload_returns_422(client):
    resp = client.post(
        "/api/v1/calculate",
        data=json.dumps({"tax_year": 2024}),
        content_type="application/json",
    )
    assert resp.status_code == 422


def test_calculate_empty_body_returns_422(client):
    resp = client.post("/api/v1/calculate", content_type="application/json")
    assert resp.status_code == 422


def test_calculate_negative_income_returns_422(client):
    bad = dict(VALID_PAYLOAD)
    bad["income_sources"] = [
        {
            "source_type": "W-2",
            "employer_or_payer": "X",
            "gross_amount": -100,
            "federal_tax_withheld": 0,
        }
    ]
    resp = client.post(
        "/api/v1/calculate",
        data=json.dumps(bad),
        content_type="application/json",
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/compliance
# ---------------------------------------------------------------------------


def test_compliance_returns_200(client):
    resp = client.post(
        "/api/v1/compliance",
        data=json.dumps(VALID_PAYLOAD),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "passed" in body
    assert "audit_risk_score" in body
    assert body["phase"] == "Phase 2 – Compliance Review"


def test_compliance_invalid_payload_returns_422(client):
    resp = client.post(
        "/api/v1/compliance",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/ask
# ---------------------------------------------------------------------------


def test_ask_missing_question_returns_400(client):
    resp = client.post(
        "/api/v1/ask",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_ask_no_api_key_returns_unconfigured_message(client):
    app = create_app({"TESTING": True, "OPENAI_API_KEY": ""})
    with app.test_client() as c:
        resp = c.post(
            "/api/v1/ask",
            data=json.dumps({"question": "What is my marginal tax rate?"}),
            content_type="application/json",
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "not configured" in body["answer"].lower()
    assert "disclaimer" in body
    assert body["phase"] == "Phase 3 – AI Assistant"


# ---------------------------------------------------------------------------
# POST /api/v1/full
# ---------------------------------------------------------------------------


def test_full_no_api_key_returns_all_phases(client):
    app = create_app({"TESTING": True, "OPENAI_API_KEY": ""})
    with app.test_client() as c:
        resp = c.post(
            "/api/v1/full",
            data=json.dumps(VALID_PAYLOAD),
            content_type="application/json",
        )
    assert resp.status_code == 200
    body = resp.get_json()
    assert "tax_calculation" in body
    assert "compliance_review" in body
    assert "ai_assistant" in body


def test_full_invalid_payload_returns_422(client):
    app = create_app({"TESTING": True, "OPENAI_API_KEY": ""})
    with app.test_client() as c:
        resp = c.post(
            "/api/v1/full",
            data=json.dumps({"bad": "data"}),
            content_type="application/json",
        )
    assert resp.status_code == 422
