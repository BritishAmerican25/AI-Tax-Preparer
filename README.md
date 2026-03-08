# AI-Tax-Preparer

An automated AI-powered US federal income tax preparation system built with a **phased approach** that balances technical development with strict regulatory compliance.

---

## Architecture Overview

The system is implemented in four progressive phases, each building on the previous:

| Phase | Module | Description |
|-------|--------|-------------|
| **1** | `app/services/tax_calculator.py` | Core tax calculation engine (2024 federal brackets, deductions, credits) |
| **2** | `app/services/compliance.py` | Regulatory compliance checks, audit-risk scoring, and IRS-rule validation |
| **3** | `app/services/ai_assistant.py` | AI assistant (OpenAI GPT-4o) for tax Q&A and optimization advice |
| **4** | `app/routes/tax.py` | REST API layer exposing all three phases as JSON endpoints |

---

## Regulatory Compliance

The system is designed to comply with key US tax regulations:

- **IRC § 1** – Progressive income tax brackets (2024 rates)
- **IRC § 63** – Standard deduction (filing-status-specific, age-adjusted)
- **IRC § 164(b)(6)** – $10,000 SALT cap
- **IRC § 170** – Charitable contribution limits (flagged when > 20% of AGI)
- **IRC § 221** – Student loan interest deduction cap ($2,500)
- **IRC § 24** – Child Tax Credit with AGI phase-out
- **IRC § 32** – Earned Income Credit eligibility rules
- **IRC § 1401** – Self-employment tax (Social Security + Medicare)
- **IRC § 6654** – Underpayment penalty warnings for estimated taxes
- **IRC § 6695** – Preparer disclosure requirements (disclaimer on all AI responses)

All AI responses include a mandatory legal disclaimer directing users to consult a licensed CPA, Enrolled Agent (EA), or tax attorney.

---

## Project Structure

```
AI-Tax-Preparer/
├── app/
│   ├── __init__.py          # Flask application factory
│   ├── main.py              # Entry point
│   ├── models/
│   │   └── tax_return.py    # Pydantic data models with validation
│   ├── routes/
│   │   └── tax.py           # REST API endpoints (Phase 4)
│   └── services/
│       ├── ai_assistant.py  # OpenAI integration (Phase 3)
│       ├── compliance.py    # IRS compliance checks (Phase 2)
│       └── tax_calculator.py# Tax calculation engine (Phase 1)
├── tests/
│   ├── test_api.py          # API endpoint tests
│   ├── test_compliance.py   # Compliance module tests
│   └── test_tax_calculator.py # Calculator unit tests
├── config.py                # Environment-based configuration
└── requirements.txt
```

---

## Setup

### Prerequisites

- Python 3.12+
- An OpenAI API key (for Phase 3 AI assistant; Phases 1 & 2 work without it)

### Installation

```bash
# Clone the repository
git clone https://github.com/BritishAmerican25/AI-Tax-Preparer.git
cd AI-Tax-Preparer

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key for Phase 3 AI assistant |
| `OPENAI_MODEL` | `gpt-4o` | OpenAI model to use |
| `SECRET_KEY` | `change-me-in-production` | Flask secret key |
| `FLASK_ENV` | `development` | `development`, `testing`, or `production` |

### Running the Server

```bash
python app/main.py
# Server starts at http://localhost:5000
```

---

## API Reference

### Health Check

```
GET /health
```

### Phase 1 – Tax Calculation

```
POST /api/v1/calculate
Content-Type: application/json
```

**Example request:**

```json
{
  "tax_year": 2024,
  "filing_status": "single",
  "taxpayer_age": 35,
  "number_of_dependents": 0,
  "income_sources": [
    {
      "source_type": "W-2",
      "employer_or_payer": "ACME Corp",
      "gross_amount": 75000.00,
      "federal_tax_withheld": 12000.00
    }
  ],
  "deductions": {
    "mortgage_interest": 8000,
    "charitable_contributions": 2000
  },
  "use_itemized_deductions": false,
  "retirement_contributions_traditional": 6000
}
```

**Example response:**

```json
{
  "phase": "Phase 1 – Tax Calculation",
  "tax_year": 2024,
  "filing_status": "single",
  "gross_income": 75000.0,
  "adjusted_gross_income": 69000.0,
  "taxable_income": 54400.0,
  "standard_deduction": 14600.0,
  "deduction_used": "standard",
  "federal_tax_before_credits": 7756.0,
  "total_credits": 0.0,
  "federal_tax_owed": 7756.0,
  "self_employment_tax": 0.0,
  "effective_tax_rate": 0.1034,
  "marginal_tax_rate": 0.22,
  "total_federal_tax_withheld": 12000.0,
  "refund_or_owed": 4244.0,
  "breakdown_by_bracket": [...]
}
```

### Phase 2 – Compliance Review

```
POST /api/v1/compliance
Content-Type: application/json
```

Same request body as `/calculate`. Returns:

```json
{
  "phase": "Phase 2 – Compliance Review",
  "passed": true,
  "issues": [],
  "warnings": ["Self-employment income detected. Ensure Schedule SE is filed..."],
  "audit_risk_score": 0.05,
  "audit_risk_label": "Low",
  "recommendations": [
    "Consider contributing to a Traditional IRA...",
    "Your withholding results in a large refund..."
  ]
}
```

### Phase 3 – AI Assistant

```
POST /api/v1/ask
Content-Type: application/json
```

```json
{
  "question": "What is my marginal tax rate and how can I reduce it?",
  "return_data": { /* optional: same as /calculate body */ }
}
```

Returns:

```json
{
  "phase": "Phase 3 – AI Assistant",
  "answer": "Based on your return, your marginal tax rate is 22%...",
  "disclaimer": "This is general information only and does not constitute professional tax advice..."
}
```

### All Phases Combined

```
POST /api/v1/full
Content-Type: application/json
```

Accepts the same body as `/calculate`, plus an optional `"question"` field. Returns all three phase results in a single response.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

The test suite covers 47 test cases across:
- Tax bracket calculations (including edge cases and all filing statuses)
- Standard vs itemized deduction selection
- Self-employment tax computation
- Child Tax Credit with phase-out
- All compliance checks (SALT cap, EITC rules, charitable thresholds, etc.)
- Audit-risk scoring
- REST API endpoint validation

---

## Security Considerations

- **Input validation**: All inputs are validated via Pydantic models with type checking and range constraints. Invalid inputs return HTTP 422 with details.
- **Rate limiting**: API endpoints are rate-limited (60 requests/minute per IP by default) via `flask-limiter` to prevent abuse.
- **No PII storage**: The application processes tax data in-memory only; no taxpayer personally identifiable information (PII) is persisted.
- **Secret key**: Set a strong `SECRET_KEY` in production via environment variable.
- **OpenAI API key**: Store your `OPENAI_API_KEY` in a `.env` file (never commit it to version control).

---

## Disclaimer

This software is provided for informational purposes only and does not constitute professional tax, legal, or financial advice. Always consult a licensed Certified Public Accountant (CPA), Enrolled Agent (EA), or tax attorney before filing your tax return.
