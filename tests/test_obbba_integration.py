"""Integration tests for OBBBA 2026 tax calculation."""

import pytest

from app.models.tax_return import (
    FilingStatus,
    IncomeSource,
    TaxReturnInput,
    Deductions,
    Credits,
)
from app.services.tax_calculator import calculate_tax


def test_obbba_2026_overtime_deduction_single():
    """Test that OBBBA overtime deduction is applied for 2026 tax year."""
    data = TaxReturnInput(
        tax_year=2026,
        filing_status=FilingStatus.SINGLE,
        taxpayer_age=35,
        number_of_dependents=0,
        income_sources=[
            IncomeSource(
                source_type="W-2",
                employer_or_payer="Test Corp",
                gross_amount=85000,
                federal_tax_withheld=15000,
            )
        ],
        obbba_overtime_premium=6500,  # Under single cap of $12,500
    )

    result = calculate_tax(data)

    # Should apply full overtime deduction
    assert result.obbba_no_tax_overtime == 6500
    # AGI should be reduced by overtime deduction
    expected_agi = 85000 - 6500
    assert result.adjusted_gross_income == expected_agi


def test_obbba_2026_overtime_deduction_capped():
    """Test that OBBBA overtime deduction is capped."""
    data = TaxReturnInput(
        tax_year=2026,
        filing_status=FilingStatus.SINGLE,
        taxpayer_age=35,
        number_of_dependents=0,
        income_sources=[
            IncomeSource(
                source_type="W-2",
                employer_or_payer="Test Corp",
                gross_amount=100000,
                federal_tax_withheld=20000,
            )
        ],
        obbba_overtime_premium=20000,  # Above single cap of $12,500
    )

    result = calculate_tax(data)

    # Should cap at $12,500
    assert result.obbba_no_tax_overtime == 12500
    expected_agi = 100000 - 12500
    assert result.adjusted_gross_income == expected_agi


def test_obbba_2026_tips_deduction():
    """Test that OBBBA tips deduction is applied for 2026 tax year."""
    data = TaxReturnInput(
        tax_year=2026,
        filing_status=FilingStatus.SINGLE,
        taxpayer_age=30,
        number_of_dependents=0,
        income_sources=[
            IncomeSource(
                source_type="W-2",
                employer_or_payer="Restaurant Inc",
                gross_amount=50000,
                federal_tax_withheld=8000,
            )
        ],
        obbba_tips=12000,  # Under cap of $25,000
    )

    result = calculate_tax(data)

    # Should apply full tips deduction
    assert result.obbba_no_tax_tips == 12000
    expected_agi = 50000 - 12000
    assert result.adjusted_gross_income == expected_agi


def test_obbba_2026_car_interest_usa_vin():
    """Test that OBBBA car interest deduction is applied for U.S.-assembled cars."""
    data = TaxReturnInput(
        tax_year=2026,
        filing_status=FilingStatus.SINGLE,
        taxpayer_age=35,
        number_of_dependents=0,
        income_sources=[
            IncomeSource(
                source_type="W-2",
                employer_or_payer="Test Corp",
                gross_amount=85000,
                federal_tax_withheld=15000,
            )
        ],
        deductions=Deductions(),
        use_itemized_deductions=True,
        obbba_car_vin="1FM5K8...",  # Starts with '1' (USA)
        obbba_car_interest_paid=4200,
    )

    result = calculate_tax(data)

    # Should allow car interest deduction
    assert result.obbba_car_interest_deduction == 4200
    assert result.obbba_car_eligibility_message == "Qualified (USA)"
    # Itemized deductions should include car interest
    assert result.itemized_deduction_total == 4200


def test_obbba_2026_car_interest_foreign_vin():
    """Test that OBBBA car interest deduction is denied for foreign cars."""
    data = TaxReturnInput(
        tax_year=2026,
        filing_status=FilingStatus.SINGLE,
        taxpayer_age=35,
        number_of_dependents=0,
        income_sources=[
            IncomeSource(
                source_type="W-2",
                employer_or_payer="Test Corp",
                gross_amount=85000,
                federal_tax_withheld=15000,
            )
        ],
        deductions=Deductions(),
        use_itemized_deductions=True,
        obbba_car_vin="WVWZZZ...",  # Foreign VIN
        obbba_car_interest_paid=4200,
    )

    result = calculate_tax(data)

    # Should deny car interest deduction
    assert result.obbba_car_interest_deduction == 0
    assert result.obbba_car_eligibility_message == "Ineligible (Foreign Assembly)"


def test_obbba_2026_trump_account_eligible():
    """Test that Trump Account eligibility is checked correctly."""
    data = TaxReturnInput(
        tax_year=2026,
        filing_status=FilingStatus.SINGLE,
        taxpayer_age=35,
        number_of_dependents=1,
        income_sources=[
            IncomeSource(
                source_type="W-2",
                employer_or_payer="Test Corp",
                gross_amount=85000,
                federal_tax_withheld=15000,
            )
        ],
        obbba_child_dob="2025-06-15",
        obbba_child_has_ssn=True,
    )

    result = calculate_tax(data)

    # Should be eligible for Trump Account
    assert result.obbba_trump_account_info is not None
    assert result.obbba_trump_account_info["federal_seed_eligible"] is True
    assert result.obbba_trump_account_info["form_4547_required"] is True


def test_obbba_2026_salt_cap_increased():
    """Test that SALT cap is increased to $40,000 for 2026."""
    data = TaxReturnInput(
        tax_year=2026,
        filing_status=FilingStatus.SINGLE,
        taxpayer_age=35,
        number_of_dependents=0,
        income_sources=[
            IncomeSource(
                source_type="W-2",
                employer_or_payer="Test Corp",
                gross_amount=200000,
                federal_tax_withheld=40000,
            )
        ],
        deductions=Deductions(
            state_local_taxes=35000,  # Above old $10k cap, under new $40k cap
        ),
        use_itemized_deductions=True,
    )

    result = calculate_tax(data)

    # Should allow full $35,000 SALT deduction (not capped at $10k)
    assert result.itemized_deduction_total == 35000


def test_obbba_2026_combined_deductions():
    """Test combined OBBBA deductions for a comprehensive scenario."""
    data = TaxReturnInput(
        tax_year=2026,
        filing_status=FilingStatus.MARRIED_JOINTLY,
        taxpayer_age=40,
        spouse_age=38,
        number_of_dependents=2,
        income_sources=[
            IncomeSource(
                source_type="W-2",
                employer_or_payer="Tech Corp",
                gross_amount=150000,
                federal_tax_withheld=30000,
            )
        ],
        deductions=Deductions(
            mortgage_interest=15000,
            state_local_taxes=20000,
        ),
        credits=Credits(
            child_tax_credit_dependents=2,
        ),
        use_itemized_deductions=True,
        obbba_overtime_premium=15000,  # Under joint cap of $25,000
        obbba_tips=5000,
        obbba_car_vin="4T1BF1FK...",  # USA VIN
        obbba_car_interest_paid=3000,
        obbba_child_dob="2026-03-01",
        obbba_child_has_ssn=True,
    )

    result = calculate_tax(data)

    # Check all OBBBA deductions applied
    assert result.obbba_no_tax_overtime == 15000
    assert result.obbba_no_tax_tips == 5000
    assert result.obbba_car_interest_deduction == 3000
    assert result.obbba_car_eligibility_message == "Qualified (USA)"
    assert result.obbba_trump_account_info["federal_seed_eligible"] is True

    # AGI should be reduced by overtime and tips
    expected_agi = 150000 - 15000 - 5000
    assert result.adjusted_gross_income == expected_agi

    # Itemized deductions should include mortgage, SALT, and car interest
    expected_itemized = 15000 + 20000 + 3000
    assert result.itemized_deduction_total == expected_itemized


def test_obbba_not_applied_for_2024():
    """Test that OBBBA deductions are NOT applied for 2024 tax year."""
    data = TaxReturnInput(
        tax_year=2024,
        filing_status=FilingStatus.SINGLE,
        taxpayer_age=35,
        number_of_dependents=0,
        income_sources=[
            IncomeSource(
                source_type="W-2",
                employer_or_payer="Test Corp",
                gross_amount=85000,
                federal_tax_withheld=15000,
            )
        ],
        obbba_overtime_premium=6500,  # Should be ignored for 2024
        obbba_tips=12000,  # Should be ignored for 2024
    )

    result = calculate_tax(data)

    # OBBBA deductions should NOT be applied for 2024
    assert result.obbba_no_tax_overtime == 0
    assert result.obbba_no_tax_tips == 0
    # AGI should not include OBBBA deductions
    assert result.adjusted_gross_income == 85000
