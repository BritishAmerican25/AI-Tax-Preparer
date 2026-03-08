"""Phase 1 – Tax Calculation Engine.

Implements 2024 US federal income tax rules:
  - Tax brackets (IRC § 1)
  - Standard deductions (IRC § 63)
  - Self-employment tax (IRC § 1401)
  - Child Tax Credit (IRC § 24)
  - Earned Income Credit (IRC § 32)
"""

from __future__ import annotations

from app.models.tax_return import (
    Credits,
    Deductions,
    FilingStatus,
    TaxCalculationResult,
    TaxReturnInput,
)

# ---------------------------------------------------------------------------
# 2024 federal income-tax parameters
# ---------------------------------------------------------------------------

# (rate, upper_bound_inclusive) – last bracket has no upper bound
BRACKETS_2024: dict[FilingStatus, list[tuple[float, float]]] = {
    FilingStatus.SINGLE: [
        (0.10, 11_600),
        (0.12, 47_150),
        (0.22, 100_525),
        (0.24, 191_950),
        (0.32, 243_725),
        (0.35, 609_350),
        (0.37, float("inf")),
    ],
    FilingStatus.MARRIED_JOINTLY: [
        (0.10, 23_200),
        (0.12, 94_300),
        (0.22, 201_050),
        (0.24, 383_900),
        (0.32, 487_450),
        (0.35, 731_200),
        (0.37, float("inf")),
    ],
    FilingStatus.MARRIED_SEPARATELY: [
        (0.10, 11_600),
        (0.12, 47_150),
        (0.22, 100_525),
        (0.24, 191_950),
        (0.32, 243_725),
        (0.35, 365_600),
        (0.37, float("inf")),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (0.10, 16_550),
        (0.12, 63_100),
        (0.22, 100_500),
        (0.24, 191_950),
        (0.32, 243_700),
        (0.35, 609_350),
        (0.37, float("inf")),
    ],
    FilingStatus.QUALIFYING_SURVIVING_SPOUSE: [
        # Same as married filing jointly
        (0.10, 23_200),
        (0.12, 94_300),
        (0.22, 201_050),
        (0.24, 383_900),
        (0.32, 487_450),
        (0.35, 731_200),
        (0.37, float("inf")),
    ],
}

STANDARD_DEDUCTIONS_2024: dict[FilingStatus, float] = {
    FilingStatus.SINGLE: 14_600,
    FilingStatus.MARRIED_JOINTLY: 29_200,
    FilingStatus.MARRIED_SEPARATELY: 14_600,
    FilingStatus.HEAD_OF_HOUSEHOLD: 21_900,
    FilingStatus.QUALIFYING_SURVIVING_SPOUSE: 29_200,
}

# Additional standard deduction for age 65+ / blind (per person)
ADDITIONAL_STANDARD_DEDUCTION_65 = 1_950  # single / HOH
ADDITIONAL_STANDARD_DEDUCTION_65_MFJ = 1_550  # married filers

# Child tax credit 2024 (up to $2,000 per qualifying child, $500 for other deps)
CHILD_TAX_CREDIT_PER_CHILD = 2_000.0
CHILD_TAX_CREDIT_PHASEOUT_SINGLE = 200_000.0
CHILD_TAX_CREDIT_PHASEOUT_MFJ = 400_000.0
CHILD_TAX_CREDIT_PHASEOUT_RATE = 50.0  # $50 reduction per $1,000 over threshold

# Self-employment tax rates (IRC § 1401)
SE_TAX_RATE_SOCIAL_SECURITY = 0.124  # on net SE income up to SS wage base
SE_TAX_RATE_MEDICARE = 0.029  # on all net SE income
SE_WAGE_BASE_2024 = 168_600.0
SE_DEDUCTION_FACTOR = 0.9235  # net SE income = gross × 0.9235


def _compute_se_tax(se_income: float) -> tuple[float, float]:
    """Return (se_tax, deductible_half) for self-employment income."""
    if se_income <= 0:
        return 0.0, 0.0
    net_se = se_income * SE_DEDUCTION_FACTOR
    ss_tax = min(net_se, SE_WAGE_BASE_2024) * SE_TAX_RATE_SOCIAL_SECURITY
    medicare_tax = net_se * SE_TAX_RATE_MEDICARE
    se_tax = round(ss_tax + medicare_tax, 2)
    deductible_half = round(se_tax / 2, 2)
    return se_tax, deductible_half


def _standard_deduction(filing_status: FilingStatus, taxpayer_age: int, spouse_age: int | None) -> float:
    base = STANDARD_DEDUCTIONS_2024[filing_status]
    if filing_status in (
        FilingStatus.MARRIED_JOINTLY,
        FilingStatus.MARRIED_SEPARATELY,
        FilingStatus.QUALIFYING_SURVIVING_SPOUSE,
    ):
        if taxpayer_age >= 65:
            base += ADDITIONAL_STANDARD_DEDUCTION_65_MFJ
        if spouse_age is not None and spouse_age >= 65:
            base += ADDITIONAL_STANDARD_DEDUCTION_65_MFJ
    else:
        if taxpayer_age >= 65:
            base += ADDITIONAL_STANDARD_DEDUCTION_65
    return base


def _apply_brackets(taxable_income: float, brackets: list[tuple[float, float]]) -> tuple[float, float, list[dict]]:
    """Apply progressive tax brackets.

    Returns (tax, marginal_rate, breakdown).
    """
    tax = 0.0
    marginal_rate = 0.0
    breakdown: list[dict] = []
    prev_limit = 0.0

    for rate, upper in brackets:
        if taxable_income <= prev_limit:
            break
        income_in_bracket = min(taxable_income, upper) - prev_limit
        tax_in_bracket = income_in_bracket * rate
        tax += tax_in_bracket
        marginal_rate = rate
        breakdown.append(
            {
                "rate": f"{rate:.0%}",
                "income_in_bracket": round(income_in_bracket, 2),
                "tax_in_bracket": round(tax_in_bracket, 2),
            }
        )
        prev_limit = upper

    return round(tax, 2), marginal_rate, breakdown


def _child_tax_credit(
    credits: Credits,
    agi: float,
    filing_status: FilingStatus,
) -> float:
    """Compute Child Tax Credit with phase-out (IRC § 24)."""
    if credits.child_tax_credit_dependents == 0:
        return 0.0

    raw_credit = credits.child_tax_credit_dependents * CHILD_TAX_CREDIT_PER_CHILD

    # Phase-out threshold
    threshold = (
        CHILD_TAX_CREDIT_PHASEOUT_MFJ
        if filing_status in (FilingStatus.MARRIED_JOINTLY, FilingStatus.QUALIFYING_SURVIVING_SPOUSE)
        else CHILD_TAX_CREDIT_PHASEOUT_SINGLE
    )
    excess = max(0, agi - threshold)
    # $50 reduction per $1,000 (or fraction thereof) over threshold
    reduction_units = -(-int(excess) // 1000)  # ceiling division
    reduction = reduction_units * CHILD_TAX_CREDIT_PHASEOUT_RATE
    return max(0.0, raw_credit - reduction)


def _total_credits(credits: Credits, agi: float, filing_status: FilingStatus) -> float:
    ctc = _child_tax_credit(credits, agi, filing_status)
    total = (
        ctc
        + credits.earned_income_credit
        + credits.child_and_dependent_care
        + credits.education_credits
        + credits.retirement_savings_credit
        + credits.other_credits
    )
    return round(total, 2)


def calculate_tax(data: TaxReturnInput) -> TaxCalculationResult:
    """Phase 1 – Calculate federal income tax for the given return input."""
    # 1. Gross income
    gross_income = sum(s.gross_amount for s in data.income_sources) + data.self_employment_income

    # 2. Self-employment tax deduction (above-the-line)
    se_tax, se_deductible_half = _compute_se_tax(data.self_employment_income)

    # 3. Above-the-line deductions → AGI
    above_the_line = (
        se_deductible_half
        + data.retirement_contributions_traditional
        + data.health_savings_account_contribution
        + min(data.deductions.student_loan_interest, 2_500)  # IRC § 221 cap
    )
    agi = max(0.0, gross_income - above_the_line)

    # 4. Standard vs itemized deduction
    std_deduction = _standard_deduction(data.filing_status, data.taxpayer_age, data.spouse_age)
    itemized_total = data.deductions.total    # Medical expense threshold: only amounts > 7.5% of AGI are deductible
    medical_deductible = max(0.0, data.deductions.medical_expenses_total - agi * 0.075)
    itemized_total = (
        data.deductions.mortgage_interest
        + min(data.deductions.state_local_taxes, 10_000)  # SALT cap (IRC § 164(b)(6))
        + data.deductions.charitable_contributions
        + medical_deductible
        + data.deductions.other_deductions
        # student_loan_interest already captured above-the-line
    )

    if data.use_itemized_deductions and itemized_total > std_deduction:
        deduction_used = "itemized"
        final_deduction = itemized_total
    else:
        deduction_used = "standard"
        final_deduction = std_deduction

    # 5. Taxable income
    taxable_income = max(0.0, agi - final_deduction)

    # 6. Tax on ordinary income
    brackets = BRACKETS_2024.get(data.filing_status, BRACKETS_2024[FilingStatus.SINGLE])
    federal_tax_before_credits, marginal_rate, breakdown = _apply_brackets(taxable_income, brackets)

    # 7. Credits
    total_credits = _total_credits(data.credits, agi, data.filing_status)
    federal_tax_owed = max(0.0, federal_tax_before_credits - total_credits)

    # 8. Total federal tax (income + SE)
    total_federal_tax = round(federal_tax_owed + se_tax, 2)

    # 9. Withholding
    total_withheld = sum(s.federal_tax_withheld for s in data.income_sources)

    # 10. Refund / owed
    refund_or_owed = round(total_withheld - total_federal_tax, 2)

    # 11. Effective rate
    effective_rate = round(total_federal_tax / gross_income, 4) if gross_income > 0 else 0.0

    return TaxCalculationResult(
        tax_year=data.tax_year,
        filing_status=data.filing_status,
        gross_income=round(gross_income, 2),
        adjusted_gross_income=round(agi, 2),
        taxable_income=round(taxable_income, 2),
        standard_deduction=round(std_deduction, 2),
        itemized_deduction_total=round(itemized_total, 2),
        deduction_used=deduction_used,
        federal_tax_before_credits=round(federal_tax_before_credits, 2),
        total_credits=total_credits,
        federal_tax_owed=round(federal_tax_owed, 2),
        self_employment_tax=round(se_tax, 2),
        effective_tax_rate=effective_rate,
        marginal_tax_rate=marginal_rate,
        total_federal_tax_withheld=round(total_withheld, 2),
        refund_or_owed=refund_or_owed,
        breakdown_by_bracket=breakdown,
    )
