"""Tests for the Phase 1 tax calculation engine."""

import pytest

from app.models.tax_return import (
    Credits,
    Deductions,
    FilingStatus,
    IncomeSource,
    TaxReturnInput,
)
from app.services.tax_calculator import (
    _apply_brackets,
    _compute_se_tax,
    _standard_deduction,
    BRACKETS_2024,
    calculate_tax,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input(
    gross: float,
    status: FilingStatus = FilingStatus.SINGLE,
    age: int = 35,
    withheld: float = 0.0,
    se_income: float = 0.0,
    deductions: Deductions | None = None,
    credits: Credits | None = None,
    use_itemized: bool = False,
    retirement: float = 0.0,
    hsa: float = 0.0,
) -> TaxReturnInput:
    return TaxReturnInput(
        tax_year=2024,
        filing_status=status,
        taxpayer_age=age,
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
        retirement_contributions_traditional=retirement,
        health_savings_account_contribution=hsa,
    )


# ---------------------------------------------------------------------------
# Standard deduction
# ---------------------------------------------------------------------------


def test_standard_deduction_single_under_65():
    sd = _standard_deduction(FilingStatus.SINGLE, 40, None, 2024)
    assert sd == 14_600


def test_standard_deduction_single_over_65():
    sd = _standard_deduction(FilingStatus.SINGLE, 65, None, 2024)
    assert sd == 14_600 + 1_950


def test_standard_deduction_mfj_both_over_65():
    sd = _standard_deduction(FilingStatus.MARRIED_JOINTLY, 67, 66, 2024)
    assert sd == 29_200 + 1_550 + 1_550


def test_standard_deduction_hoh():
    sd = _standard_deduction(FilingStatus.HEAD_OF_HOUSEHOLD, 40, None, 2024)
    assert sd == 21_900


# ---------------------------------------------------------------------------
# SE tax
# ---------------------------------------------------------------------------


def test_se_tax_zero_income():
    se_tax, deductible = _compute_se_tax(0)
    assert se_tax == 0.0
    assert deductible == 0.0


def test_se_tax_positive():
    se_tax, deductible = _compute_se_tax(50_000)
    assert se_tax > 0
    assert abs(deductible - se_tax / 2) < 0.01


def test_se_tax_ss_cap():
    """SE social security tax should be capped at the wage base."""
    _, _ = _compute_se_tax(200_000)
    # No assertion on exact value – just ensure it doesn't raise
    se_tax_high, _ = _compute_se_tax(200_000)
    se_tax_low, _ = _compute_se_tax(168_600)
    # Medicare still grows, so higher income has higher total
    assert se_tax_high > se_tax_low


# ---------------------------------------------------------------------------
# Bracket calculation
# ---------------------------------------------------------------------------


def test_brackets_zero_income():
    tax, rate, breakdown = _apply_brackets(0, BRACKETS_2024[FilingStatus.SINGLE])
    assert tax == 0.0
    assert rate == 0.0
    assert breakdown == []


def test_brackets_first_bracket_only():
    # $10,000 – fully in the 10% bracket for single filers
    tax, rate, _ = _apply_brackets(10_000, BRACKETS_2024[FilingStatus.SINGLE])
    assert tax == pytest.approx(1_000.0, rel=1e-4)
    assert rate == 0.10


def test_brackets_straddles_two_brackets():
    # $30,000 single: 10% on 11,600 + 12% on 18,400
    expected = 11_600 * 0.10 + (30_000 - 11_600) * 0.12
    tax, _, _ = _apply_brackets(30_000, BRACKETS_2024[FilingStatus.SINGLE])
    assert tax == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# Full calculate_tax integration
# ---------------------------------------------------------------------------


def test_calculate_tax_simple_single():
    data = _make_input(gross=60_000, withheld=10_000)
    result = calculate_tax(data)

    assert result.gross_income == 60_000
    assert result.deduction_used == "standard"
    assert result.standard_deduction == 14_600
    assert result.taxable_income == pytest.approx(60_000 - 14_600, rel=1e-4)
    assert result.federal_tax_owed > 0
    assert result.effective_tax_rate < 0.25


def test_calculate_tax_refund_when_over_withheld():
    data = _make_input(gross=50_000, withheld=20_000)
    result = calculate_tax(data)
    assert result.refund_or_owed > 0


def test_calculate_tax_owed_when_under_withheld():
    data = _make_input(gross=150_000, withheld=10_000)
    result = calculate_tax(data)
    assert result.refund_or_owed < 0


def test_calculate_tax_uses_itemized_when_larger():
    deductions = Deductions(
        mortgage_interest=20_000,
        charitable_contributions=5_000,
        state_local_taxes=10_000,
    )
    data = _make_input(gross=100_000, deductions=deductions, use_itemized=True)
    result = calculate_tax(data)
    assert result.deduction_used == "itemized"
    assert result.itemized_deduction_total > result.standard_deduction


def test_calculate_tax_standard_wins_when_itemized_smaller():
    deductions = Deductions(mortgage_interest=500)
    data = _make_input(gross=80_000, deductions=deductions, use_itemized=True)
    result = calculate_tax(data)
    assert result.deduction_used == "standard"


def test_calculate_tax_married_jointly():
    data = _make_input(gross=120_000, status=FilingStatus.MARRIED_JOINTLY, withheld=15_000)
    result = calculate_tax(data)
    assert result.standard_deduction == 29_200
    assert result.federal_tax_owed >= 0


def test_calculate_tax_child_tax_credit_reduces_tax():
    credits_with = Credits(child_tax_credit_dependents=2)
    data_with = _make_input(gross=80_000, credits=credits_with)
    data_without = _make_input(gross=80_000)

    result_with = calculate_tax(data_with)
    result_without = calculate_tax(data_without)

    assert result_with.federal_tax_owed < result_without.federal_tax_owed
    assert result_with.total_credits == pytest.approx(4_000.0)


def test_calculate_tax_child_tax_credit_phases_out():
    """CTC should be reduced for very high earners."""
    credits = Credits(child_tax_credit_dependents=1)
    data_high = _make_input(gross=250_000, credits=credits)
    data_low = _make_input(gross=80_000, credits=credits)

    result_high = calculate_tax(data_high)
    result_low = calculate_tax(data_low)

    assert result_high.total_credits < result_low.total_credits


def test_calculate_tax_se_income_adds_se_tax():
    data = _make_input(gross=0, se_income=50_000)
    result = calculate_tax(data)
    assert result.self_employment_tax > 0


def test_calculate_tax_retirement_reduces_agi():
    data_with = _make_input(gross=80_000, retirement=7_000)
    data_without = _make_input(gross=80_000)

    result_with = calculate_tax(data_with)
    result_without = calculate_tax(data_without)

    assert result_with.adjusted_gross_income < result_without.adjusted_gross_income


def test_calculate_tax_medical_deduction_threshold():
    """Medical expenses below 7.5% of AGI should not be deductible."""
    agi = 100_000
    deductions = Deductions(medical_expenses_total=5_000)  # < 7.5% of 100k
    data = _make_input(gross=agi, deductions=deductions, use_itemized=True)
    result = calculate_tax(data)
    # Medical is below threshold, so itemized should not exceed standard
    assert result.deduction_used == "standard"


def test_calculate_tax_zero_income():
    data = _make_input(gross=0)
    result = calculate_tax(data)
    assert result.federal_tax_owed == 0.0
    assert result.taxable_income == 0.0


def test_calculate_tax_result_fields():
    """Ensure all required fields are present in the result."""
    data = _make_input(gross=75_000)
    result = calculate_tax(data)

    assert result.phase == "Phase 1 – Tax Calculation"
    assert result.tax_year == 2024
    assert isinstance(result.breakdown_by_bracket, list)
    assert len(result.breakdown_by_bracket) > 0
    assert result.effective_tax_rate >= 0
    assert result.marginal_tax_rate > 0
