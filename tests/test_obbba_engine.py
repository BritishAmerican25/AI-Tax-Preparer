import pytest
from datetime import datetime
from obbba_engine import OBBBAEngine, TaxVault


class TestOBBBAEngineInit:
    def test_default_caps(self):
        engine = OBBBAEngine()
        assert engine.OT_DEDUCTION_CAP_SINGLE == 12500
        assert engine.OT_DEDUCTION_CAP_JOINT == 25000
        assert engine.TIP_DEDUCTION_CAP == 25000
        assert engine.CAR_INTEREST_CAP == 10000
        assert engine.REMOTE_WORK_CREDIT_CAP == 2500
        assert engine.TRUMP_ACCOUNT_ANNUAL_CAP == 5000
        assert engine.SALT_CAP_OBBBA == 40000


class TestCalculateNoTaxOvertime:
    def setup_method(self):
        self.engine = OBBBAEngine()

    def test_single_below_cap(self):
        assert self.engine.calculate_no_tax_overtime(6500, "SINGLE") == 6500

    def test_single_at_cap(self):
        assert self.engine.calculate_no_tax_overtime(12500, "SINGLE") == 12500

    def test_single_above_cap(self):
        assert self.engine.calculate_no_tax_overtime(20000, "SINGLE") == 12500

    def test_joint_below_cap(self):
        assert self.engine.calculate_no_tax_overtime(15000, "JOINT") == 15000

    def test_joint_at_cap(self):
        assert self.engine.calculate_no_tax_overtime(25000, "JOINT") == 25000

    def test_joint_above_cap(self):
        assert self.engine.calculate_no_tax_overtime(30000, "JOINT") == 25000

    def test_zero_overtime(self):
        assert self.engine.calculate_no_tax_overtime(0, "SINGLE") == 0

    def test_non_joint_uses_single_cap(self):
        # Any status that is not "JOINT" should use the single cap
        assert self.engine.calculate_no_tax_overtime(20000, "HEAD_OF_HOUSEHOLD") == 12500


class TestVerifyCarInterestEligibility:
    def setup_method(self):
        self.engine = OBBBAEngine()

    def test_usa_vin_starting_with_1(self):
        eligible, msg = self.engine.verify_car_interest_eligibility("1FM5K8...")
        assert eligible is True
        assert msg == "Qualified (USA)"

    def test_usa_vin_starting_with_4(self):
        eligible, msg = self.engine.verify_car_interest_eligibility("4T1BF1FK...")
        assert eligible is True
        assert msg == "Qualified (USA)"

    def test_usa_vin_starting_with_5(self):
        eligible, msg = self.engine.verify_car_interest_eligibility("5YJ3E1EA...")
        assert eligible is True
        assert msg == "Qualified (USA)"

    def test_foreign_vin(self):
        eligible, msg = self.engine.verify_car_interest_eligibility("WVWZZZ...")
        assert eligible is False
        assert msg == "Ineligible (Foreign Assembly)"

    def test_empty_vin(self):
        eligible, msg = self.engine.verify_car_interest_eligibility("")
        assert eligible is False
        assert msg == "Invalid VIN"

    def test_none_vin(self):
        eligible, msg = self.engine.verify_car_interest_eligibility(None)
        assert eligible is False
        assert msg == "Invalid VIN"


class TestProcessTrumpAccountElection:
    def setup_method(self):
        self.engine = OBBBAEngine()

    def test_eligible_child_with_ssn_string_date(self):
        result = self.engine.process_trump_account_election("2025-06-15", True)
        assert result["form_4547_required"] is True
        assert result["federal_seed_eligible"] is True
        assert result["contribution_window_opens"] == "2026-07-04"
        assert result["annual_limit"] == 5000

    def test_eligible_child_with_ssn_datetime(self):
        result = self.engine.process_trump_account_election(datetime(2026, 3, 1), True)
        assert result["federal_seed_eligible"] is True

    def test_eligible_child_without_ssn(self):
        result = self.engine.process_trump_account_election("2025-06-15", False)
        assert result["federal_seed_eligible"] is False

    def test_child_born_before_window(self):
        result = self.engine.process_trump_account_election("2024-12-31", True)
        assert result["federal_seed_eligible"] is False

    def test_child_born_after_window(self):
        result = self.engine.process_trump_account_election("2029-01-01", True)
        assert result["federal_seed_eligible"] is False

    def test_child_born_at_window_start(self):
        result = self.engine.process_trump_account_election("2025-01-01", True)
        assert result["federal_seed_eligible"] is True

    def test_child_born_at_window_end(self):
        result = self.engine.process_trump_account_election("2028-12-31", True)
        assert result["federal_seed_eligible"] is True


class TestTaxVault:
    def setup_method(self):
        self.vault = TaxVault()

    def test_tokenize_returns_token_id(self):
        pii = {"filing_status": "SINGLE", "wages": 85000, "ot_premium": 6500, "tips": 12000}
        result = self.vault.tokenize_user_data(pii)
        assert "token_id" in result
        assert len(result["token_id"]) > 0

    def test_tokenize_returns_filing_status(self):
        pii = {"filing_status": "JOINT", "wages": 100000}
        result = self.vault.tokenize_user_data(pii)
        assert result["filing_status"] == "JOINT"

    def test_tokenize_returns_income_summary(self):
        pii = {"filing_status": "SINGLE", "wages": 85000, "ot_premium": 6500, "tips": 12000}
        result = self.vault.tokenize_user_data(pii)
        assert result["income_summary"]["w2_wages"] == 85000
        assert result["income_summary"]["obbba_overtime_code_tt"] == 6500
        assert result["income_summary"]["obbba_tips_code_tp"] == 12000

    def test_tokenize_does_not_leak_pii(self):
        pii = {"name": "John Doe", "ssn": "123-45-6789", "filing_status": "SINGLE", "wages": 50000}
        result = self.vault.tokenize_user_data(pii)
        result_str = str(result)
        assert "John Doe" not in result_str
        assert "123-45-6789" not in result_str

    def test_tokenize_stores_data_internally(self):
        pii = {"name": "Test User", "ssn": "000-00-0000", "filing_status": "SINGLE", "wages": 50000}
        result = self.vault.tokenize_user_data(pii)
        token_id = result["token_id"]
        assert token_id in self.vault._secure_storage
        assert self.vault._secure_storage[token_id] == pii

    def test_unique_tokens_per_call(self):
        pii = {"filing_status": "SINGLE", "wages": 50000}
        result1 = self.vault.tokenize_user_data(pii)
        result2 = self.vault.tokenize_user_data(pii)
        assert result1["token_id"] != result2["token_id"]
