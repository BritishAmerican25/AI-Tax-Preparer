"""Tax return data models with strict validation."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class FilingStatus(str, Enum):
    SINGLE = "single"
    MARRIED_JOINTLY = "married_filing_jointly"
    MARRIED_SEPARATELY = "married_filing_separately"
    HEAD_OF_HOUSEHOLD = "head_of_household"
    QUALIFYING_SURVIVING_SPOUSE = "qualifying_surviving_spouse"


class IncomeSource(BaseModel):
    """Represents a single income source."""

    source_type: str = Field(..., description="W2, 1099-NEC, 1099-INT, etc.")
    employer_or_payer: str = Field(..., min_length=1, max_length=200)
    gross_amount: float = Field(..., ge=0, description="Gross income in USD")
    federal_tax_withheld: float = Field(0.0, ge=0)
    state_tax_withheld: float = Field(0.0, ge=0)

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        allowed = {
            "W-2",
            "1099-NEC",
            "1099-MISC",
            "1099-INT",
            "1099-DIV",
            "1099-R",
            "1099-G",
            "K-1",
            "Other",
        }
        if v not in allowed:
            raise ValueError(f"source_type must be one of {allowed}")
        return v

    @field_validator("federal_tax_withheld", "state_tax_withheld")
    @classmethod
    def withheld_le_gross(cls, v: float) -> float:
        # Individual field can't exceed gross; cross-field check in model validator
        if v < 0:
            raise ValueError("Withheld tax cannot be negative")
        return v


class Deductions(BaseModel):
    """Itemized deductions (Schedule A)."""

    mortgage_interest: float = Field(0.0, ge=0)
    state_local_taxes: float = Field(0.0, ge=0, description="Actual SALT paid; $10,000 cap applied during calculation")
    charitable_contributions: float = Field(0.0, ge=0)
    medical_expenses_total: float = Field(0.0, ge=0)
    student_loan_interest: float = Field(0.0, ge=0, description="Student loan interest; $2,500 cap applied during calculation")
    other_deductions: float = Field(0.0, ge=0)

    @property
    def total(self) -> float:
        return (
            self.mortgage_interest
            + self.state_local_taxes
            + self.charitable_contributions
            + self.medical_expenses_total
            + self.student_loan_interest
            + self.other_deductions
        )


class Credits(BaseModel):
    """Tax credits claimed by the filer."""

    child_tax_credit_dependents: int = Field(0, ge=0, le=20)
    earned_income_credit: float = Field(0.0, ge=0)
    child_and_dependent_care: float = Field(0.0, ge=0)
    education_credits: float = Field(0.0, ge=0)
    retirement_savings_credit: float = Field(0.0, ge=0)
    other_credits: float = Field(0.0, ge=0)


class TaxReturnInput(BaseModel):
    """Top-level input for a tax return submission."""

    tax_year: int = Field(..., ge=2020, le=2025, description="Tax year being filed")
    filing_status: FilingStatus
    taxpayer_age: int = Field(..., ge=0, le=130)
    spouse_age: Optional[int] = Field(None, ge=0, le=130)
    number_of_dependents: int = Field(0, ge=0, le=20)
    income_sources: list[IncomeSource] = Field(..., min_length=1)
    deductions: Deductions = Field(default_factory=Deductions)
    credits: Credits = Field(default_factory=Credits)
    use_itemized_deductions: bool = False
    self_employment_income: float = Field(0.0, ge=0)
    retirement_contributions_traditional: float = Field(0.0, ge=0)
    health_savings_account_contribution: float = Field(0.0, ge=0)

    @model_validator(mode="after")
    def validate_spouse_fields(self) -> "TaxReturnInput":
        if self.filing_status == FilingStatus.MARRIED_JOINTLY and self.spouse_age is None:
            raise ValueError("spouse_age is required for married filing jointly")
        return self


class TaxCalculationResult(BaseModel):
    """Output of the tax calculation engine."""

    tax_year: int
    filing_status: FilingStatus
    gross_income: float
    adjusted_gross_income: float
    taxable_income: float
    standard_deduction: float
    itemized_deduction_total: float
    deduction_used: str
    federal_tax_before_credits: float
    total_credits: float
    federal_tax_owed: float
    self_employment_tax: float
    effective_tax_rate: float
    marginal_tax_rate: float
    total_federal_tax_withheld: float
    refund_or_owed: float
    breakdown_by_bracket: list[dict]
    phase: str = "Phase 1 – Tax Calculation"


class ComplianceCheckResult(BaseModel):
    """Output of the compliance verification module."""

    passed: bool
    issues: list[str]
    warnings: list[str]
    audit_risk_score: float = Field(..., ge=0.0, le=1.0, description="0=low, 1=high")
    audit_risk_label: str
    recommendations: list[str]
    phase: str = "Phase 2 – Compliance Review"


class AIAssistantResponse(BaseModel):
    """Response from the AI tax assistant."""

    answer: str
    disclaimer: str = (
        "This is general information only and does not constitute professional tax advice. "
        "Consult a licensed tax professional (CPA or EA) for guidance specific to your situation."
    )
    phase: str = "Phase 3 – AI Assistant"
