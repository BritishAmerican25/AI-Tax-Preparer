"""Tests for the Phase 2 compliance module."""

import pytest

from app.models.tax_return import (
    Credits,
    Deductions,
    FilingStatus,
    IncomeSource,
    TaxReturnInput,
)
from app.services.compliance import check_compliance
from app.services.tax_calculator import calculate_tax


def _make_input(
    gross: float = 60_000,
    status: FilingStatus = FilingStatus.SINGLE,
    withheld: float = 8_000,
    deductions: Deductions | None = None,
    credits: Credits | None = None,
    se_income: float = 0.0,
    use_itemized: bool = False,
) -> TaxReturnInput:
    return TaxReturnInput(
        tax_year=2024,
        filing_status=status,
        taxpayer_age=35,
        spouse_age=40 if status == FilingStatus.MARRIED_JOINTLY else None,
        number_of_dependents=0,
        income_sources=[
            IncomeSource(
                source_type="W-2",
                employer_or_payer="ACME Corp",
                gross_amount=gross,
                federal_tax_withheld=withheld,
            )
        ],
        deductions=deductions or Deductions(),
        credits=credits or Credits(),
        use_itemized_deductions=use_itemized,
        self_employment_income=se_income,
    )


def _run(data: TaxReturnInput):
    result = calculate_tax(data)
    return check_compliance(data, result)


# ---------------------------------------------------------------------------
# Clean return
# ---------------------------------------------------------------------------


def test_compliance_clean_return_passes():
    data = _make_input(gross=60_000, withheld=8_000)
    comp = _run(data)
    assert comp.passed is True
    assert len(comp.issues) == 0


def test_compliance_returns_phase_label():
    data = _make_input()
    comp = _run(data)
    assert comp.phase == "Phase 2 – Compliance Review"


# ---------------------------------------------------------------------------
# Income source checks
# ---------------------------------------------------------------------------


def test_compliance_withheld_exceeds_gross_creates_issue():
    data = TaxReturnInput(
        tax_year=2024,
        filing_status=FilingStatus.SINGLE,
        taxpayer_age=35,
        number_of_dependents=0,
        income_sources=[
            IncomeSource(
                source_type="W-2",
                employer_or_payer="Bad Corp",
                gross_amount=5_000,
                federal_tax_withheld=6_000,  # more than gross
            )
        ],
    )
    comp = _run(data)
    assert comp.passed is False
    assert any("withheld" in issue.lower() for issue in comp.issues)


# ---------------------------------------------------------------------------
# SALT cap
# ---------------------------------------------------------------------------


def test_compliance_salt_cap_issue():
    deductions = Deductions(state_local_taxes=10_001)  # exceeds cap
    data = _make_input(deductions=deductions)
    comp = _run(data)
    assert any("SALT" in issue or "salt" in issue.lower() or "10,000" in issue for issue in comp.issues)


# ---------------------------------------------------------------------------
# EITC
# ---------------------------------------------------------------------------


def test_compliance_eitc_mfs_creates_issue():
    credits = Credits(earned_income_credit=500)
    data = _make_input(
        gross=30_000,
        status=FilingStatus.MARRIED_SEPARATELY,
        credits=credits,
    )
    comp = _run(data)
    assert comp.passed is False
    assert any("Earned Income Credit" in issue or "separately" in issue for issue in comp.issues)


def test_compliance_eitc_high_agi_no_children():
    credits = Credits(earned_income_credit=200, child_tax_credit_dependents=0)
    data = _make_input(gross=25_000, credits=credits)
    comp = _run(data)
    assert comp.passed is False


# ---------------------------------------------------------------------------
# Charitable contributions
# ---------------------------------------------------------------------------


def test_compliance_high_charitable_generates_warning():
    agi = 60_000
    deductions = Deductions(charitable_contributions=13_000)  # > 20% of 60k
    data = _make_input(gross=agi, deductions=deductions, use_itemized=True)
    comp = _run(data)
    assert any("charitable" in w.lower() for w in comp.warnings)


# ---------------------------------------------------------------------------
# Audit risk scoring
# ---------------------------------------------------------------------------


def test_audit_risk_low_for_clean_return():
    data = _make_input(gross=60_000, withheld=8_000)
    comp = _run(data)
    assert comp.audit_risk_score < 0.15
    assert comp.audit_risk_label == "Low"


def test_audit_risk_increases_with_issues():
    # EITC violation + high charitable = elevated risk
    credits = Credits(earned_income_credit=500)
    deductions = Deductions(charitable_contributions=20_000)
    data = _make_input(
        gross=60_000,
        credits=credits,
        deductions=deductions,
        use_itemized=True,
        status=FilingStatus.MARRIED_SEPARATELY,
    )
    comp = _run(data)
    assert comp.audit_risk_score > 0.15


def test_audit_risk_score_in_range():
    data = _make_input()
    comp = _run(data)
    assert 0.0 <= comp.audit_risk_score <= 1.0


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


def test_recommendations_present_for_any_return():
    data = _make_input()
    comp = _run(data)
    assert len(comp.recommendations) > 0


def test_recommendations_suggest_ira_for_high_earner():
    data = _make_input(gross=100_000)
    comp = _run(data)
    assert any("IRA" in r or "retirement" in r.lower() for r in comp.recommendations)


def test_recommendations_suggest_w4_adjustment_for_large_refund():
    data = _make_input(gross=50_000, withheld=20_000)
    comp = _run(data)
    assert any("W-4" in r or "withholding" in r.lower() for r in comp.recommendations)
