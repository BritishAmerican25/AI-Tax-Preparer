import uuid
from datetime import datetime
import json

class OBBBAEngine:
    """
    Core Tax Logic Engine for the 2026 One Big Beautiful Bill Act.
    Handles 'No Tax' deductions and OBBBA-specific credits.
    """
    
    def __init__(self):
        # 2026 Thresholds & Caps
        self.OT_DEDUCTION_CAP_SINGLE = 12500
        self.OT_DEDUCTION_CAP_JOINT = 25000
        self.TIP_DEDUCTION_CAP = 25000
        self.CAR_INTEREST_CAP = 10000
        self.REMOTE_WORK_CREDIT_CAP = 2500
        self.TRUMP_ACCOUNT_ANNUAL_CAP = 5000
        self.SALT_CAP_OBBBA = 40000 # Increased from $10k under OBBBA
        
    def calculate_no_tax_overtime(self, raw_ot_premium, filing_status):
        """Logic for Box 12, Code TT (Qualified Overtime)"""
        cap = self.OT_DEDUCTION_CAP_JOINT if filing_status == "JOINT" else self.OT_DEDUCTION_CAP_SINGLE
        deduction = min(raw_ot_premium, cap)
        return deduction

    def verify_car_interest_eligibility(self, vin):
        """
        OBBBA Rule: Interest is only deductible for U.S.-assembled cars.
        VINs starting with 1, 4, or 5 are USA.
        """
        if not vin or len(vin) < 1:
            return False, "Invalid VIN"
        
        origin_code = vin[0]
        is_eligible = origin_code in ['1', '4', '5']
        
        msg = "Qualified (USA)" if is_eligible else "Ineligible (Foreign Assembly)"
        return is_eligible, msg

    def process_trump_account_election(self, child_dob, has_ssn):
        """
        Form 4547 Logic: Child must be born between Jan 1, 2025 and Dec 31, 2028
        to receive the $1,000 Federal Pilot Program Seed.
        """
        # Ensure child_dob is a datetime object
        if isinstance(child_dob, str):
            child_dob = datetime.strptime(child_dob, "%Y-%m-%d")
            
        is_seed_eligible = datetime(2025, 1, 1) <= child_dob <= datetime(2028, 12, 31)
        
        return {
            "form_4547_required": True,
            "federal_seed_eligible": is_seed_eligible and has_ssn,
            "contribution_window_opens": "2026-07-04",
            "annual_limit": self.TRUMP_ACCOUNT_ANNUAL_CAP
        }

class TaxVault:
    """
    Section 7216 Compliance Layer.
    Ensures PII is tokenized before hitting the AI Reasoning Layer.
    """
    def __init__(self):
        self._secure_storage = {}

    def tokenize_user_data(self, pii_data):
        user_id = str(uuid.uuid4())
        # Store sensitive data locally; only return the tokenized profile
        self._secure_storage[user_id] = pii_data 
        
        return {
            "token_id": user_id,
            "filing_status": pii_data.get("filing_status"),
            "income_summary": {
                "w2_wages": pii_data.get("wages"),
                "obbba_overtime_code_tt": pii_data.get("ot_premium"),
                "obbba_tips_code_tp": pii_data.get("tips")
            }
        }

# --- EXAMPLE MVP EXECUTION ---

if __name__ == "__main__":
    engine = OBBBAEngine()
    vault = TaxVault()

    # 1. Incoming Raw User Data (Simulated OCR Output)
    raw_data = {
        "name": "Chuks Eze", # PII
        "ssn": "000-00-0000", # PII
        "filing_status": "SINGLE",
        "wages": 85000,
        "ot_premium": 6500, # From Box 12, Code TT
        "tips": 12000,      # From Box 12, Code TP
        "car_vin": "1FM5K8...", # Starts with '1' (USA)
        "car_interest_paid": 4200,
        "child_dob": "2025-06-15",
        "has_child_ssn": True
    }

    # 2. Tokenize for Privacy
    tokenized_profile = vault.tokenize_user_data(raw_data)
    print(f"--- [7216 COMPLIANCE] DATA TOKENIZED: {tokenized_profile['token_id']} ---")

    # 3. Calculate OBBBA Alpha
    ot_deduction = engine.calculate_no_tax_overtime(raw_data['ot_premium'], raw_data['filing_status'])
    car_eligibility, car_msg = engine.verify_car_interest_eligibility(raw_data['car_vin'])
    trump_election = engine.process_trump_account_election(raw_data['child_dob'], raw_data['has_child_ssn'])

    # 4. Generate Final Report
    report = {
        "user_id": tokenized_profile['token_id'],
        "obbba_summary": {
            "tax_free_overtime": ot_deduction,
            "tax_free_tips": raw_data['tips'], # Fully deductible up to cap
            "car_interest_deduction": raw_data['car_interest_paid'] if car_eligibility else 0,
            "trump_account_federal_seed": "$1,000" if trump_election['federal_seed_eligible'] else "$0"
        }
    }

    print("\n--- 2026 OBBBA IMPACT REPORT ---")
    print(json.dumps(report, indent=4))
