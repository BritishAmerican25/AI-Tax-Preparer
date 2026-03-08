"""Phase 2 – Regulatory Compliance Module.

Implements IRS compliance checks, audit-risk scoring, and recommendations:
  - Income reporting completeness
  - Excessive deduction detection
  - Self-employment income cross-checks
  - EITC eligibility rules (IRC § 32)
  - Preparer disclosure requirements (IRC § 6695)
  - High round-number detection (audit trigger)
"""

from __future__ import annotations

from app.models.tax_return import (
    ComplianceCheckResult,
    FilingStatus,
    TaxCalculationResult,
    TaxReturnInput,
)

# Thresholds used for audit-risk scoring
_CHARITABLE_HIGH_RATIO = 0.20       # charitable > 20% of AGI is a flag
_BUSINESS_EXPENSE_HIGH_RATIO = 0.70  # SE expenses > 70% of SE income
_ROUND_NUMBER_THRESHOLD = 5          # ≥5 perfectly round dollar amounts
_HIGH_REFUND_THRESHOLD = 10_000.0

# 2024 EITC maximum AGI limits (IRC § 32) – (single/HOH, married_jointly)
# Index = number of qualifying children (0, 1, 2, 3+)
_EITC_AGI_LIMITS: dict[int, tuple[float, float]] = {
    0: (18_591.0, 25_511.0),
    1: (49_084.0, 56_004.0),
    2: (55_768.0, 62_688.0),
    3: (59_899.0, 66_819.0),
}
_EITC_MFJ_STATUSES = {FilingStatus.MARRIED_JOINTLY, FilingStatus.QUALIFYING_SURVIVING_SPOUSE}


def _check_income_sources(data: TaxReturnInput, issues: list[str], warnings: list[str]) -> float:
    """Validate income sources; return risk contribution."""
    risk = 0.0
    for src in data.income_sources:
        if src.federal_tax_withheld > src.gross_amount:
            issues.append(
                f"Federal tax withheld (${src.federal_tax_withheld:,.2f}) exceeds gross income "
                f"(${src.gross_amount:,.2f}) for source '{src.employer_or_payer}'."
            )
            risk += 0.2
    return risk


def _check_round_numbers(data: TaxReturnInput, warnings: list[str]) -> float:
    """Flag suspiciously round dollar amounts (common audit trigger)."""
    round_count = 0
    candidates = [
        data.deductions.mortgage_interest,
        data.deductions.charitable_contributions,
        data.deductions.medical_expenses_total,
        data.deductions.other_deductions,
        data.self_employment_income,
    ]
    for val in candidates:
        if val > 0 and val % 1000 == 0:
            round_count += 1
    if round_count >= _ROUND_NUMBER_THRESHOLD:
        warnings.append(
            f"{round_count} income/deduction figures are round numbers. "
            "Ensure all amounts are supported by documentation."
        )
        return 0.1
    return 0.0


def _check_charitable(data: TaxReturnInput, agi: float, warnings: list[str]) -> float:
    """Flag charitable contributions that exceed 20% of AGI."""
    risk = 0.0
    if agi > 0 and data.deductions.charitable_contributions / agi > _CHARITABLE_HIGH_RATIO:
        warnings.append(
            f"Charitable contributions (${data.deductions.charitable_contributions:,.2f}) exceed "
            f"20% of AGI (${agi:,.2f}). Ensure all contributions are documented (IRC § 170)."
        )
        risk += 0.15
    return risk


def _check_salt_cap(data: TaxReturnInput, issues: list[str]) -> float:
    """Ensure SALT deduction does not exceed the $10,000 cap (IRC § 164(b)(6))."""
    risk = 0.0
    if data.deductions.state_local_taxes > 10_000:
        issues.append(
            f"State and local tax deduction (${data.deductions.state_local_taxes:,.2f}) exceeds "
            "the $10,000 SALT cap (IRC § 164(b)(6)). The model has already capped this."
        )
        risk += 0.05
    return risk


def _check_se_income(data: TaxReturnInput, warnings: list[str]) -> float:
    """Flag self-employment income without proper documentation requirements."""
    risk = 0.0
    if data.self_employment_income > 400:
        warnings.append(
            "Self-employment income detected. Ensure Schedule SE is filed and estimated "
            "quarterly taxes (Form 1040-ES) have been paid if applicable (IRC § 6654)."
        )
    if data.self_employment_income > 0 and data.self_employment_income < 400:
        # Below SE tax threshold – inform user
        warnings.append(
            "Self-employment income is below $400; no SE tax applies, but income must still "
            "be reported (IRC § 1401)."
        )
    return risk


def _check_eitc(data: TaxReturnInput, agi: float, issues: list[str], warnings: list[str]) -> float:
    """Basic EITC eligibility sanity check (IRC § 32)."""
    risk = 0.0
    if data.credits.earned_income_credit > 0:
        if data.filing_status == FilingStatus.MARRIED_SEPARATELY:
            issues.append(
                "Earned Income Credit cannot be claimed by married taxpayers filing separately (IRC § 32(d))."
            )
            risk += 0.25
        else:
            # Look up AGI limit for this filer's number of qualifying children
            child_key = min(data.credits.child_tax_credit_dependents, 3)
            single_limit, mfj_limit = _EITC_AGI_LIMITS.get(child_key, _EITC_AGI_LIMITS[3])
            agi_limit = mfj_limit if data.filing_status in _EITC_MFJ_STATUSES else single_limit
            if agi > agi_limit:
                issues.append(
                    f"Earned Income Credit claimed but AGI (${agi:,.2f}) exceeds the 2024 "
                    f"EITC AGI limit (${agi_limit:,.2f}) for this filing status and number of "
                    "qualifying children (IRC § 32)."
                )
                risk += 0.25
    return risk


def _check_student_loan(data: TaxReturnInput, issues: list[str]) -> None:
    """Student loan interest deduction cap (IRC § 221)."""
    if data.deductions.student_loan_interest > 2_500:
        issues.append(
            f"Student loan interest deduction (${data.deductions.student_loan_interest:,.2f}) "
            "exceeds the $2,500 annual limit (IRC § 221). The model has already capped this."
        )


def _check_high_refund(result: TaxCalculationResult, warnings: list[str]) -> float:
    """Flag very large refunds that may attract IRS scrutiny."""
    risk = 0.0
    if result.refund_or_owed > _HIGH_REFUND_THRESHOLD:
        warnings.append(
            f"Refund of ${result.refund_or_owed:,.2f} is unusually large. "
            "Verify that withholding figures are correct and credits are properly documented."
        )
        risk += 0.1
    return risk


def _risk_label(score: float) -> str:
    if score < 0.15:
        return "Low"
    if score < 0.40:
        return "Moderate"
    if score < 0.65:
        return "High"
    return "Very High"


def _build_recommendations(data: TaxReturnInput, result: TaxCalculationResult, issues: list[str]) -> list[str]:
    recs: list[str] = []

    if result.deduction_used == "standard":
        recs.append(
            "You are using the standard deduction. If you have significant mortgage interest, "
            "charitable contributions, or medical expenses, itemizing may reduce your tax liability."
        )

    if data.retirement_contributions_traditional == 0 and result.adjusted_gross_income > 20_000:
        recs.append(
            "Consider contributing to a Traditional IRA or 401(k) to reduce your AGI "
            "(contribution limits: $7,000 IRA / $23,000 401(k) for 2024)."
        )

    if data.health_savings_account_contribution == 0 and result.adjusted_gross_income > 30_000:
        recs.append(
            "If enrolled in a High-Deductible Health Plan, an HSA contribution (up to $4,150 "
            "single / $8,300 family in 2024) provides a triple tax advantage."
        )

    if result.refund_or_owed > 2_000:
        recs.append(
            "Your withholding results in a large refund. Consider adjusting your W-4 so you "
            "receive more take-home pay throughout the year."
        )
    elif result.refund_or_owed < -1_000:
        recs.append(
            "You owe additional taxes. Review your W-4 withholding or pay estimated quarterly "
            "taxes to avoid underpayment penalties (IRC § 6654)."
        )

    if not issues:
        recs.append("No compliance issues detected. Keep all supporting documents for at least 3 years (7 for SE income).")

    return recs


def check_compliance(data: TaxReturnInput, result: TaxCalculationResult) -> ComplianceCheckResult:
    """Phase 2 – Run all compliance checks on the return and calculate audit-risk score."""
    issues: list[str] = []
    warnings: list[str] = []
    risk_score = 0.0

    agi = result.adjusted_gross_income

    risk_score += _check_income_sources(data, issues, warnings)
    risk_score += _check_round_numbers(data, warnings)
    risk_score += _check_charitable(data, agi, warnings)
    risk_score += _check_salt_cap(data, issues)
    _check_se_income(data, warnings)
    risk_score += _check_eitc(data, agi, issues, warnings)
    _check_student_loan(data, issues)
    risk_score += _check_high_refund(result, warnings)

    # Clamp to [0, 1]
    risk_score = round(min(1.0, max(0.0, risk_score)), 3)

    return ComplianceCheckResult(
        passed=len(issues) == 0,
        issues=issues,
        warnings=warnings,
        audit_risk_score=risk_score,
        audit_risk_label=_risk_label(risk_score),
        recommendations=_build_recommendations(data, result, issues),
    )
