"""Phase 4 – REST API routes for the AI Tax Preparer.

Endpoints:
  POST /api/v1/calculate   – Phase 1: tax calculation
  POST /api/v1/compliance  – Phase 2: compliance review
  POST /api/v1/ask         – Phase 3: AI assistant Q&A
  POST /api/v1/full        – All three phases in a single request
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from pydantic import ValidationError

from app.models.tax_return import TaxReturnInput
from app.services.ai_assistant import ask_assistant
from app.services.compliance import check_compliance
from app.services.tax_calculator import calculate_tax

tax_bp = Blueprint("tax", __name__)


def _parse_body() -> dict:
    """Parse JSON body; raise 400 on missing/invalid JSON."""
    data = request.get_json(silent=True)
    if data is None:
        return {}
    return data


def _validation_error_response(exc: ValidationError):
    return jsonify({"error": "Validation error", "details": exc.errors()}), 422


# ---------------------------------------------------------------------------
# Phase 1 – Tax Calculation
# ---------------------------------------------------------------------------


@tax_bp.post("/calculate")
def calculate():
    """Calculate federal income tax for the submitted return."""
    body = _parse_body()
    try:
        data = TaxReturnInput.model_validate(body)
    except ValidationError as exc:
        return _validation_error_response(exc)

    result = calculate_tax(data)
    return jsonify(result.model_dump()), 200


# ---------------------------------------------------------------------------
# Phase 2 – Compliance Review
# ---------------------------------------------------------------------------


@tax_bp.post("/compliance")
def compliance():
    """Run compliance checks on the submitted return."""
    body = _parse_body()
    try:
        data = TaxReturnInput.model_validate(body)
    except ValidationError as exc:
        return _validation_error_response(exc)

    result = calculate_tax(data)
    compliance_result = check_compliance(data, result)
    return jsonify(compliance_result.model_dump()), 200


# ---------------------------------------------------------------------------
# Phase 3 – AI Assistant
# ---------------------------------------------------------------------------


@tax_bp.post("/ask")
def ask():
    """Ask the AI tax assistant a question (optionally in context of a return)."""
    body = _parse_body()
    question = body.get("question", "").strip()
    if not question:
        return jsonify({"error": "A 'question' field is required."}), 400

    # Optional: include return context
    result = None
    compliance_result = None
    if "return_data" in body:
        try:
            data = TaxReturnInput.model_validate(body["return_data"])
            result = calculate_tax(data)
            compliance_result = check_compliance(data, result)
        except ValidationError as exc:
            return _validation_error_response(exc)

    response = ask_assistant(
        question=question,
        api_key=current_app.config.get("OPENAI_API_KEY", ""),
        model=current_app.config.get("OPENAI_MODEL", "gpt-4o"),
        result=result,
        compliance=compliance_result,
    )
    return jsonify(response.model_dump()), 200


# ---------------------------------------------------------------------------
# All Phases Combined
# ---------------------------------------------------------------------------


@tax_bp.post("/full")
def full():
    """Run all three phases (calculate → compliance → AI summary) in one request."""
    body = _parse_body()
    question = body.pop("question", "Summarize my tax situation and key recommendations.")

    try:
        data = TaxReturnInput.model_validate(body)
    except ValidationError as exc:
        return _validation_error_response(exc)

    result = calculate_tax(data)
    compliance_result = check_compliance(data, result)
    ai_response = ask_assistant(
        question=question,
        api_key=current_app.config.get("OPENAI_API_KEY", ""),
        model=current_app.config.get("OPENAI_MODEL", "gpt-4o"),
        result=result,
        compliance=compliance_result,
    )

    return (
        jsonify(
            {
                "tax_calculation": result.model_dump(),
                "compliance_review": compliance_result.model_dump(),
                "ai_assistant": ai_response.model_dump(),
            }
        ),
        200,
    )
