"""Phase 1 – Tax Calculation Engine.

Implements 2024 US federal income tax rules:
  - Tax brackets (IRC § 1)
  - Standard deductions (IRC § 63)
  - Self-employment tax (IRC § 1401)
  - Child Tax Credit (IRC § 24)
  - Earned Income Credit (IRC § 32)

Implements 2026 OBBBA (One Big Beautiful Bill Act) rules:
  - No-tax overtime deductions
  - No-tax tips deductions
  - U.S.-assembled car interest deductions
  - Trump Account eligibility
"""

from __future__ import annotations

from app.models.tax_return import (
    Credits,
    Deductions,
    FilingStatus,
    TaxCalculationResult,
    TaxReturnInput,
)

try:
    from app.services.obbba_engine import OBBBAEngine
    OBBBA_AVAILABLE = True
except ImportError:
    OBBBA_AVAILABLE = False

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

# 2026 federal income-tax parameters (projected with inflation adjustment)
BRACKETS_2026: dict[FilingStatus, list[tuple[float, float]]] = {
    FilingStatus.SINGLE: [
        (0.10, 11_925),
        (0.12, 48_475),
        (0.22, 103_350),
        (0.24, 197_300),
        (0.32, 250_525),
        (0.35, 626_350),
        (0.37, float("inf")),
    ],
    FilingStatus.MARRIED_JOINTLY: [
        (0.10, 23_850),
        (0.12, 96_950),
        (0.22, 206_700),
        (0.24, 394_600),
        (0.32, 501_050),
        (0.35, 751_600),
        (0.37, float("inf")),
    ],
    FilingStatus.MARRIED_SEPARATELY: [
        (0.10, 11_925),
        (0.12, 48_475),
        (0.22, 103_350),
        (0.24, 197_300),
        (0.32, 250_525),
        (0.35, 375_800),
        (0.37, float("inf")),
    ],
    FilingStatus.HEAD_OF_HOUSEHOLD: [
        (0.10, 17_000),
        (0.12, 64_850),
        (0.22, 103_350),
        (0.24, 197_300),
        (0.32, 250_500),
        (0.35, 626_350),
        (0.37, float("inf")),
    ],
    FilingStatus.QUALIFYING_SURVIVING_SPOUSE: [
        (0.10, 23_850),
        (0.12, 96_950),
        (0.22, 206_700),
        (0.24, 394_600),
        (0.32, 501_050),
        (0.35, 751_600),
        (0.37, float("inf")),
    ],
}

STANDARD_DEDUCTIONS_2026: dict[FilingStatus, float] = {
    FilingStatus.SINGLE: 15_000,
    FilingStatus.MARRIED_JOINTLY: 30_000,
    FilingStatus.MARRIED_SEPARATELY: 15_000,
    FilingStatus.HEAD_OF_HOUSEHOLD: 22_500,
    FilingStatus.QUALIFYING_SURVIVING_SPOUSE: 30_000,
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


def _standard_deduction(filing_status: FilingStatus, taxpayer_age: int, spouse_age: int | None, tax_year: int) -> float:
    """Get standard deduction based on filing status, age, and tax year."""
    if tax_year >= 2026:
        base = STANDARD_DEDUCTIONS_2026[filing_status]
    else:
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
    # Initialize OBBBA engine if available and tax year is 2026
    obbba_engine = None
    obbba_no_tax_overtime = 0.0
    obbba_no_tax_tips = 0.0
    obbba_car_interest_deduction = 0.0
    obbba_car_eligibility_message = None
    obbba_trump_account_info = None

    if data.tax_year >= 2026 and OBBBA_AVAILABLE:
        obbba_engine = OBBBAEngine()

    # 1. Gross income
    gross_income = sum(s.gross_amount for s in data.income_sources) + data.self_employment_income

    # 2. Self-employment tax deduction (above-the-line)
    se_tax, se_deductible_half = _compute_se_tax(data.self_employment_income)

    # 3. OBBBA 2026-specific deductions (above-the-line)
    if obbba_engine and data.tax_year >= 2026:
        # Convert filing status to OBBBA format
        filing_status_map = {
            FilingStatus.MARRIED_JOINTLY: "JOINT",
            FilingStatus.QUALIFYING_SURVIVING_SPOUSE: "JOINT",
        }
        obbba_filing_status = filing_status_map.get(data.filing_status, "SINGLE")

        # Calculate no-tax overtime deduction
        if data.obbba_overtime_premium > 0:
            obbba_no_tax_overtime = obbba_engine.calculate_no_tax_overtime(
                data.obbba_overtime_premium, obbba_filing_status
            )

        # Calculate no-tax tips deduction
        if data.obbba_tips > 0:
            obbba_no_tax_tips = min(data.obbba_tips, obbba_engine.TIP_DEDUCTION_CAP)

        # Verify car interest eligibility
        if data.obbba_car_vin and data.obbba_car_interest_paid > 0:
            car_eligible, car_msg = obbba_engine.verify_car_interest_eligibility(data.obbba_car_vin)
            obbba_car_eligibility_message = car_msg
            if car_eligible:
                obbba_car_interest_deduction = min(data.obbba_car_interest_paid, obbba_engine.CAR_INTEREST_CAP)

        # Process Trump Account election
        if data.obbba_child_dob:
            obbba_trump_account_info = obbba_engine.process_trump_account_election(
                data.obbba_child_dob, data.obbba_child_has_ssn
            )

    # 4. Above-the-line deductions → AGI
    above_the_line = (
        se_deductible_half
        + data.retirement_contributions_traditional
        + data.health_savings_account_contribution
        + min(data.deductions.student_loan_interest, 2_500)  # IRC § 221 cap
        + obbba_no_tax_overtime  # OBBBA: no-tax overtime
        + obbba_no_tax_tips  # OBBBA: no-tax tips
    )
    agi = max(0.0, gross_income - above_the_line)

    # 5. Standard vs itemized deduction
    std_deduction = _standard_deduction(data.filing_status, data.taxpayer_age, data.spouse_age, data.tax_year)
    # Medical expense threshold: only amounts > 7.5% of AGI are deductible
    medical_deductible = max(0.0, data.deductions.medical_expenses_total - agi * 0.075)

    # SALT cap: $10,000 for 2024, $40,000 for 2026 OBBBA
    salt_cap = 40_000 if data.tax_year >= 2026 else 10_000

    itemized_total = (
        data.deductions.mortgage_interest
        + min(data.deductions.state_local_taxes, salt_cap)
        + data.deductions.charitable_contributions
        + medical_deductible
        + data.deductions.other_deductions
        + obbba_car_interest_deduction  # OBBBA: car interest
        # student_loan_interest already captured above-the-line
    )

    if data.use_itemized_deductions and itemized_total > std_deduction:
        deduction_used = "itemized"
        final_deduction = itemized_total
    else:
        deduction_used = "standard"
        final_deduction = std_deduction

    # 6. Taxable income
    taxable_income = max(0.0, agi - final_deduction)

    # 7. Tax on ordinary income (use appropriate year brackets)
    if data.tax_year >= 2026:
        brackets = BRACKETS_2026.get(data.filing_status, BRACKETS_2026[FilingStatus.SINGLE])
    else:
        brackets = BRACKETS_2024.get(data.filing_status, BRACKETS_2024[FilingStatus.SINGLE])
    federal_tax_before_credits, marginal_rate, breakdown = _apply_brackets(taxable_income, brackets)

    # 8. Credits
    total_credits = _total_credits(data.credits, agi, data.filing_status)
    federal_tax_owed = max(0.0, federal_tax_before_credits - total_credits)

    # 9. Total federal tax (income + SE)
    total_federal_tax = round(federal_tax_owed + se_tax, 2)

    # 10. Withholding
    total_withheld = sum(s.federal_tax_withheld for s in data.income_sources)

    # 11. Refund / owed
    refund_or_owed = round(total_withheld - total_federal_tax, 2)

    # 12. Effective rate
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
        obbba_no_tax_overtime=round(obbba_no_tax_overtime, 2),
        obbba_no_tax_tips=round(obbba_no_tax_tips, 2),
        obbba_car_interest_deduction=round(obbba_car_interest_deduction, 2),
        obbba_car_eligibility_message=obbba_car_eligibility_message,
        obbba_trump_account_info=obbba_trump_account_info,
    )
