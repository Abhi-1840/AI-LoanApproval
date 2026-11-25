"""
Comprehensive Test Suite for AI Loan Approval System
Covers all functional, edge-case, and architectural scenarios.
"""
import os
import re
import json
import unittest
from unittest.mock import patch, MagicMock

# Import app components
import app as main_app
from app import (
    app,
    verify_kyc,
    underwrite,
    calculate_emi,
    calculate_preapproved_limit_from_salary,
    determine_tenure_months,
    generate_sanction_letter_pdf,
    send_email_with_attachment,
    local_master_agent,
    DUMMY_CUSTOMERS,
    SANCTIONS_DIR
)
import form_app


class LoanApprovalSystemTestSuite(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.form_client = form_app.app.test_client()
        app.testing = True
        form_app.app.testing = True

    # ────────────────────────────────────────────────────────────────
    # 1. Customer Verification (KYC) Tests
    # ────────────────────────────────────────────────────────────────
    def test_01_successful_customer_verification(self):
        """Test verification of a valid customer ID."""
        result = verify_kyc("cust01")
        self.assertEqual(result.get("status"), "Verification Successful")
        self.assertEqual(result.get("name"), "Ramesh S.")
        self.assertEqual(result.get("credit_score"), 810)

    def test_02_customer_verification_not_found(self):
        """Test verification when customer ID does not exist."""
        result = verify_kyc("cust9999")
        self.assertEqual(result.get("status"), "Verification Failed")
        self.assertIn("not found", result.get("message", "").lower())

    def test_03_customer_verification_case_insensitive(self):
        """Test verification with uppercase / mixed case customer ID."""
        result = verify_kyc("CUST10")
        self.assertEqual(result.get("status"), "Verification Successful")
        self.assertEqual(result.get("name"), "Neha C.")

    # ────────────────────────────────────────────────────────────────
    # 2. Mathematical & Loan Logic Tests
    # ────────────────────────────────────────────────────────────────
    def test_04_emi_calculation_formula(self):
        """Verify EMI calculation matches standard financial banking formula."""
        # Principal = 1,00,000, Rate = 12% p.a. (1% p.m.), Tenure = 12 months
        # Standard formula: 100000 * 0.01 * (1.01)^12 / ((1.01)^12 - 1) = 8884.8788...
        emi = calculate_emi(100000, 12, 12)
        self.assertIsNotNone(emi)
        self.assertAlmostEqual(emi, 8884.88, places=1)

    def test_05_tenure_determination_by_salary(self):
        """Verify salary brackets correctly assign loan tenures."""
        self.assertEqual(determine_tenure_months(30000), 48)  # < 40k -> 48 mo
        self.assertEqual(determine_tenure_months(50000), 60)  # 40k-80k -> 60 mo
        self.assertEqual(determine_tenure_months(80000), 60)  # 40k-80k -> 60 mo
        self.assertEqual(determine_tenure_months(120000), 72) # > 80k -> 72 mo

    def test_06_preapproved_limit_calculation(self):
        """Verify pre-approved limit equals 15x monthly salary."""
        salary = 60000
        expected_limit = 60000 * 15  # 9,00,000
        self.assertEqual(calculate_preapproved_limit_from_salary(salary), expected_limit)

    # ────────────────────────────────────────────────────────────────
    # 3. Underwriting Decision Tests
    # ────────────────────────────────────────────────────────────────
    def test_07_successful_approval(self):
        """Loan amount <= pre-approved limit results in Approved status."""
        cust = DUMMY_CUSTOMERS["cust01"].copy()  # Salary 80,000 -> Limit 12,00,000
        result = underwrite(cust, 500000)
        self.assertEqual(result["status"], "Approved")
        self.assertIn("approved", result["message"].lower())
        self.assertGreater(result["emi"], 0)

    def test_08_loan_exceeding_limit_rejection(self):
        """Loan amount exceeding pre-approved limit results in Rejection."""
        cust = DUMMY_CUSTOMERS["cust01"].copy()  # Salary 80,000, Limit 12,00,000
        # Loan = 15,00,000 > 12,00,000 limit -> Must be rejected
        result = underwrite(cust, 1500000)
        self.assertEqual(result["status"], "Rejection")
        self.assertIn("exceeds", result["message"].lower())

    def test_09_emi_affordability_failure(self):
        """Loan where EMI > 50% salary results in Rejection."""
        cust = {
            "customer_id": "cust_afford",
            "name": "Affordability Test",
            "credit_score": 750,
            "salary": 10000,  # 50% salary = 5,000
            "pre_approved_limit": 300000
        }
        # Loan = 250,000 (within 300k limit); Tenure = 48 mo; EMI @ 12% = ~6,583 > 5,000
        result = underwrite(cust, 250000)
        self.assertEqual(result["status"], "Rejection")
        self.assertIn("50%", result["message"])

    def test_10_loan_amount_exceeding_max_eligibility(self):
        """Loan amount > limit results in Rejection."""
        cust = DUMMY_CUSTOMERS["cust01"].copy()  # Limit 12,00,000
        result = underwrite(cust, 3000000)
        self.assertEqual(result["status"], "Rejection")
        self.assertIn("exceeds", result["message"].lower())

    def test_11_low_credit_score_rejection(self):
        """Customer with credit score < 700 is rejected regardless of loan amount."""
        cust = DUMMY_CUSTOMERS["cust99"].copy()  # Credit score = 580
        result = underwrite(cust, 50000)
        self.assertEqual(result["status"], "Rejection")
        self.assertIn("credit score", result["message"].lower())

    def test_12_formatted_currency_inputs(self):
        """User input with commas (e.g. '5,00,000') should parse cleanly."""
        cust = DUMMY_CUSTOMERS["cust01"].copy()
        result = underwrite(cust, "5,00,000")
        self.assertEqual(result["status"], "Approved")

    def test_13_invalid_non_numeric_loan_input(self):
        """Non-numeric string input should safely return Rejection without crash."""
        cust = DUMMY_CUSTOMERS["cust01"].copy()
        result = underwrite(cust, "five lakhs")
        self.assertEqual(result["status"], "Rejection")
        self.assertIn("valid number", result["message"].lower())

    # ────────────────────────────────────────────────────────────────
    # 4. PDF Generation Tests
    # ────────────────────────────────────────────────────────────────
    def test_14_pdf_generation_creates_valid_file(self):
        """Verify sanction letter PDF is created on disk with valid PDF header."""
        cust = DUMMY_CUSTOMERS["cust01"]
        pdf_path = generate_sanction_letter_pdf(cust, 500000, 60)
        self.assertTrue(os.path.exists(pdf_path), f"File not found: {pdf_path}")
        self.assertGreater(os.path.getsize(pdf_path), 1000, "PDF size is too small")
        with open(pdf_path, "rb") as f:
            header = f.read(4)
        self.assertEqual(header, b"%PDF", "Generated file is not a valid PDF")

    # ────────────────────────────────────────────────────────────────
    # 5. Email Functionality Tests
    # ────────────────────────────────────────────────────────────────
    def test_15_email_handling_without_credentials(self):
        """When email credentials are not configured, function returns graceful failure without crashing."""
        orig_user = main_app.GMAIL_USER
        orig_pass = main_app.GMAIL_APP_PASSWORD
        try:
            main_app.GMAIL_USER = ""
            main_app.GMAIL_APP_PASSWORD = ""
            pdf_path = generate_sanction_letter_pdf(DUMMY_CUSTOMERS["cust01"], 100000, 48)
            success, msg = send_email_with_attachment("test@example.com", "Subject", "Body", pdf_path)
            self.assertFalse(success)
            self.assertIn("Gmail credentials not configured", msg)
        finally:
            main_app.GMAIL_USER = orig_user
            main_app.GMAIL_APP_PASSWORD = orig_pass

    @patch("smtplib.SMTP")
    def test_16_email_sending_with_mocked_smtp(self, mock_smtp_cls):
        """When SMTP credentials are provided, email message is constructed and sent properly."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        # Temporarily inject dummy gmail credentials
        orig_user = main_app.GMAIL_USER
        orig_pass = main_app.GMAIL_APP_PASSWORD
        main_app.GMAIL_USER = "testbank@gmail.com"
        main_app.GMAIL_APP_PASSWORD = "apppassword1234"

        try:
            pdf_path = generate_sanction_letter_pdf(DUMMY_CUSTOMERS["cust01"], 100000, 48)
            success, msg = send_email_with_attachment("customer@example.com", "Test Subject", "Test Body", pdf_path)
            self.assertTrue(success)
            self.assertIsNone(msg)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("testbank@gmail.com", "apppassword1234")
            mock_server.send_message.assert_called_once()
        finally:
            main_app.GMAIL_USER = orig_user
            main_app.GMAIL_APP_PASSWORD = orig_pass

    # ────────────────────────────────────────────────────────────────
    # 6. Flask Routes & API Integration Tests
    # ────────────────────────────────────────────────────────────────
    def test_17_health_endpoint(self):
        """Verify /health returns HTTP 200 and expected status keys."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("dummy_customers", data)

    def test_18_new_chat_session(self):
        """Verify /new_chat generates a new session ID."""
        resp = self.client.get("/new_chat")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("session_id", "").startswith("sess_"))

    def test_19_chat_detects_kyc_token(self):
        """Chat route should detect customer ID and return VERIFY_KYC command."""
        resp = self.client.post("/chat", json={
            "session_id": "test_sess_01",
            "user_input": "My ID is cust01"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("orchestration_command"), "[[FLASK_CALL:VERIFY_KYC]]")

    def test_20_orchestrate_verify_kyc_success(self):
        """Orchestrate route VERIFY_KYC step saves customer in session."""
        session_id = "test_sess_kyc"
        resp = self.client.post("/orchestrate", json={
            "step": "VERIFY_KYC",
            "session_id": session_id,
            "customer_info": {"customer_id": "cust01"}
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "success")
        self.assertEqual(data.get("customer_data", {}).get("name"), "Ramesh S.")
        self.assertIn(session_id, main_app.session_data)

    def test_21_orchestrate_underwrite_complete_flow(self):
        """Complete workflow: KYC verification followed by Underwriting & PDF generation."""
        session_id = "test_sess_full_flow"
        # Step 1: KYC
        self.client.post("/orchestrate", json={
            "step": "VERIFY_KYC",
            "session_id": session_id,
            "customer_info": {"customer_id": "cust01"}
        })
        # Step 2: Underwrite
        resp = self.client.post("/orchestrate", json={
            "step": "UNDERWRITE",
            "session_id": session_id,
            "customer_info": {"loan_amount": "500000"}
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "complete")
        self.assertIn("Approved", data.get("worker_message", ""))
        self.assertIsNotNone(data.get("pdf_file"))
        # Verify PDF exists in sanctions directory
        pdf_path = os.path.join(SANCTIONS_DIR, data["pdf_file"])
        self.assertTrue(os.path.exists(pdf_path))

    def test_22_orchestrate_without_kyc_fails_gracefully(self):
        """Attempting UNDERWRITE without preceding KYC returns descriptive error."""
        resp = self.client.post("/orchestrate", json={
            "step": "UNDERWRITE",
            "session_id": "unverified_session_xyz",
            "customer_info": {"loan_amount": "500000"}
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("status"), "error")
        self.assertIn("Please verify KYC first", data.get("message", ""))

    # ────────────────────────────────────────────────────────────────
    # 7. Admin Panel (form_app.py) Tests
    # ────────────────────────────────────────────────────────────────
    def test_23_admin_form_renders(self):
        """Admin panel root page renders successfully."""
        resp = self.form_client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"ADMIN PANEL", resp.data)

    def test_24_admin_form_validation_and_submission(self):
        """Admin panel /add-customer validates required fields and handles submit."""
        # Missing required field
        resp = self.form_client.post("/add-customer", data={
            "customerName": "",
            "phoneNumber": "123"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Customer name is required", resp.data)

        # Valid submission (Firebase may be offline, should report gracefully)
        resp_valid = self.form_client.post("/add-customer", data={
            "customerName": "Test User",
            "phoneNumber": "9876543210",
            "age": "30",
            "city": "Mumbai",
            "panNumber": "ABCDE1234F",
            "emailAddress": "test@example.com",
            "salary": "75000",
            "currentLoan": "0",
            "creditScore": "780"
        })
        self.assertEqual(resp_valid.status_code, 200)
        self.assertIn(b"Customer Added", resp_valid.data)

    # ────────────────────────────────────────────────────────────────
    # 8. Conversational In-Chat Onboarding & Assistant Feature Tests
    # ────────────────────────────────────────────────────────────────
    def test_25_apply_loan_intent_unverified(self):
        """User asking to apply for a loan without prior KYC gets structured guidance."""
        resp = self.client.post("/chat", json={
            "session_id": "sess_test_apply_unverified",
            "user_input": "I want to apply for a loan"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        text = data.get("response_text", "")
        self.assertIn("Existing Customer", text)
        self.assertIn("New Customer", text)

    def test_26_in_chat_onboarding_full_flow(self):
        """Complete conversational onboarding in chat step-by-step and persists to storage."""
        sess_id = "sess_test_onboarding_user"
        test_phone = "9988776655"
        expected_cid = f"cust{test_phone}"

        # Clean up any existing record for this test phone before running
        if os.path.exists("customers.json"):
            try:
                with open("customers.json", "r") as f:
                    cdata = json.load(f)
                if expected_cid in cdata:
                    del cdata[expected_cid]
                    with open("customers.json", "w") as f:
                        json.dump(cdata, f, indent=2)
            except Exception:
                pass

        # 1. Trigger registration
        r1 = self.client.post("/chat", json={"session_id": sess_id, "user_input": "I am a new customer"}).get_json()
        self.assertIn("Full Name", r1["response_text"])

        # 2. Enter Name
        r2 = self.client.post("/chat", json={"session_id": sess_id, "user_input": "Vikram Malhotra"}).get_json()
        self.assertIn("Mobile Number", r2["response_text"])

        # 3. Enter Phone
        r3 = self.client.post("/chat", json={"session_id": sess_id, "user_input": test_phone}).get_json()
        self.assertIn("Email Address", r3["response_text"])

        # 4. Enter Email
        r4 = self.client.post("/chat", json={"session_id": sess_id, "user_input": "vikram@example.com"}).get_json()
        self.assertIn("Age", r4["response_text"])

        # 5. Enter Age & City
        r5 = self.client.post("/chat", json={"session_id": sess_id, "user_input": "32, Bangalore"}).get_json()
        self.assertIn("PAN", r5["response_text"])

        # 6. Enter PAN
        r6 = self.client.post("/chat", json={"session_id": sess_id, "user_input": "ABCDE1234F"}).get_json()
        self.assertIn("Salary", r6["response_text"])

        # 7. Enter Salary (60,000)
        r7 = self.client.post("/chat", json={"session_id": sess_id, "user_input": "60000"}).get_json()
        self.assertIn("Current Ongoing", r7["response_text"])

        # 8. Enter Ongoing Loans
        r8 = self.client.post("/chat", json={"session_id": sess_id, "user_input": "0"}).get_json()
        self.assertIn("Credit Score", r8["response_text"])

        # 9. Enter Credit Score (760)
        r9 = self.client.post("/chat", json={"session_id": sess_id, "user_input": "760"}).get_json()
        final_text = r9["response_text"]
        self.assertIn("Registration Completed Successfully", final_text)
        self.assertIn("Preliminary Loan Eligibility", final_text)
        self.assertIn("Preliminary Eligible", final_text)
        self.assertIn("This is an initial eligibility estimate based on your monthly net salary", final_text)
        self.assertIn(expected_cid, final_text)
        self.assertIn("900,000", final_text)  # 60,000 * 15 = 900,000 limit

        # Verify customer exists in customers.json
        with open("customers.json", "r") as f:
            saved = json.load(f)
        self.assertIn(expected_cid, saved)
        self.assertEqual(saved[expected_cid]["name"], "Vikram Malhotra")
        self.assertEqual(saved[expected_cid]["salary"], 60000)
        self.assertEqual(saved[expected_cid]["pre_approved_limit"], 900000)

        # Verify session is now verified with this customer
        self.assertIn(sess_id, main_app.session_data)
        self.assertEqual(main_app.session_data[sess_id]["customer_id"], expected_cid)

    def test_27_new_customer_immediate_loan_application(self):
        """Newly registered customer can immediately apply for a loan and receive sanction."""
        sess_id = "sess_test_new_cust_apply"
        test_phone = "9123456789"
        expected_cid = f"cust{test_phone}"

        # Clean up any existing record for this test phone before running
        if os.path.exists("customers.json"):
            try:
                with open("customers.json", "r") as f:
                    cdata = json.load(f)
                if expected_cid in cdata:
                    del cdata[expected_cid]
                    with open("customers.json", "w") as f:
                        json.dump(cdata, f, indent=2)
            except Exception:
                pass

        # Register user quickly
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "I am a new customer"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "Priya Nair"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": test_phone})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "priya@example.com"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "29, Chennai"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "PQRMN5678X"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "70000"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "none"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "780"})

        # Apply for loan of 4,00,000 (well within 10,50,000 limit)
        resp = self.client.post("/chat", json={"session_id": sess_id, "user_input": "400000"})
        data = resp.get_json()
        self.assertEqual(data.get("orchestration_command"), "[[FLASK_CALL:UNDERWRITE]]")

        # Orchestrate underwriting
        orch_resp = self.client.post("/orchestrate", json={
            "step": "UNDERWRITE",
            "session_id": sess_id,
            "customer_info": {"loan_amount": "400000"}
        })
        orch_data = orch_resp.get_json()
        self.assertEqual(orch_data.get("status"), "complete")
        self.assertIn("Approved", orch_data.get("worker_message", ""))
        self.assertIsNotNone(orch_data.get("pdf_file"))

    def test_28_check_my_limit_and_profile(self):
        """Test check my limit query for verified and unverified sessions."""
        # Unverified session
        r1 = self.client.post("/chat", json={"session_id": "sess_unverified_limit", "user_input": "check my limit"}).get_json()
        self.assertIn("haven't verified", r1["response_text"].lower())

        # Verified session (cust01)
        sess_v = "sess_verified_limit"
        self.client.post("/orchestrate", json={
            "step": "VERIFY_KYC",
            "session_id": sess_v,
            "customer_info": {"customer_id": "cust01"}
        })
        r2 = self.client.post("/chat", json={"session_id": sess_v, "user_input": "what is my limit"}).get_json()
        self.assertIn("1,200,000", r2["response_text"])
        self.assertIn("Ramesh S.", r2["response_text"])

    def test_29_emi_calculation_inquiry(self):
        """EMI calculation questions return detailed monthly repayment breakdown."""
        resp = self.client.post("/chat", json={
            "session_id": "sess_emi_test",
            "user_input": "Calculate EMI for ₹5,00,000"
        })
        data = resp.get_json()
        text = data.get("response_text", "")
        self.assertIn("36 Months", text)
        self.assertIn("48 Months", text)
        self.assertIn("60 Months", text)

    def test_30_documents_and_eligibility_inquiries(self):
        """Inquiries about required documents and eligibility criteria return clear rules."""
        r_docs = self.client.post("/chat", json={"session_id": "sess_info", "user_input": "What documents are required?"}).get_json()
        self.assertIn("PAN Card", r_docs["response_text"])
        self.assertIn("Salary Slips", r_docs["response_text"])

        r_rules = self.client.post("/chat", json={"session_id": "sess_info", "user_input": "What are the loan eligibility rules?"}).get_json()
        self.assertIn("700", r_rules["response_text"])
        self.assertIn("15x", r_rules["response_text"])

    def test_31_loan_amount_parser(self):
        """Verify parse_loan_amount_text handles natural language denominations."""
        from app import parse_loan_amount_text
        self.assertEqual(parse_loan_amount_text("5 lakhs"), 500000.0)
        self.assertEqual(parse_loan_amount_text("5.5 lakh"), 550000.0)
        self.assertEqual(parse_loan_amount_text("3 lacs"), 300000.0)
        self.assertEqual(parse_loan_amount_text("50k"), 50000.0)
        self.assertEqual(parse_loan_amount_text("5,00,000"), 500000.0)
        self.assertEqual(parse_loan_amount_text("₹2,50,000"), 250000.0)

    def test_32_logout_and_cancel_onboarding(self):
        """Test logout clears session and cancel terminates active onboarding."""
        sess_id = "sess_test_cancel"
        # Start onboarding
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "I am a new customer"})
        self.assertIsNotNone(main_app.session_data.get(sess_id, {}).get("onboarding_state"))

        # Cancel onboarding
        r_cancel = self.client.post("/chat", json={"session_id": sess_id, "user_input": "cancel"}).get_json()
        self.assertIn("Cancelled", r_cancel["response_text"])
        self.assertIsNone(main_app.session_data.get(sess_id, {}).get("onboarding_state"))

        # Login cust01 then logout
        self.client.post("/orchestrate", json={
            "step": "VERIFY_KYC",
            "session_id": sess_id,
            "customer_info": {"customer_id": "cust01"}
        })
        self.assertEqual(main_app.session_data[sess_id].get("customer_id"), "cust01")
        r_logout = self.client.post("/chat", json={"session_id": sess_id, "user_input": "logout"}).get_json()
        self.assertIn("Logged out", r_logout["response_text"])
        self.assertNotIn("customer_id", main_app.session_data.get(sess_id, {}))

    # ────────────────────────────────────────────────────────────────
    # 9. Strict Loan Eligibility Criteria Tests (Mandatory Specifications)
    # ────────────────────────────────────────────────────────────────
    def test_33_age_19_reject(self):
        """Age 19 -> Reject."""
        cust = {"name": "Young Applicant", "age": 19, "credit_score": 750, "salary": 50000, "current_loan_status": 0}
        res = underwrite(cust, 100000, tenure=60)
        self.assertEqual(res["status"], "Rejection")
        self.assertTrue(any("21 years" in r for r in res["failed_conditions"]))

    def test_34_age_21_pass(self):
        """Age 21 -> Pass age validation."""
        cust = {"name": "Eligible Applicant", "age": 21, "credit_score": 750, "salary": 50000, "current_loan_status": 0}
        res = underwrite(cust, 100000, tenure=60)
        self.assertEqual(res["status"], "Approved")

    def test_35_age_66_reject(self):
        """Age 66 -> Reject."""
        cust = {"name": "Senior Applicant", "age": 66, "credit_score": 750, "salary": 50000, "current_loan_status": 0}
        res = underwrite(cust, 100000, tenure=60)
        self.assertEqual(res["status"], "Rejection")
        self.assertTrue(any("65 years" in r for r in res["failed_conditions"]))

    def test_36_cibil_650_reject(self):
        """CIBIL 650 -> Reject automatic eligibility."""
        cust = {"name": "Low CIBIL", "age": 30, "credit_score": 650, "salary": 50000, "current_loan_status": 0}
        res = underwrite(cust, 100000, tenure=60)
        self.assertEqual(res["status"], "Rejection")
        self.assertTrue(any("700" in r for r in res["failed_conditions"]))

    def test_37_cibil_700_pass(self):
        """CIBIL 700 -> Pass score validation."""
        cust = {"name": "Threshold CIBIL", "age": 30, "credit_score": 700, "salary": 50000, "current_loan_status": 0}
        res = underwrite(cust, 100000, tenure=60)
        self.assertEqual(res["status"], "Approved")

    def test_38_salary_50k_loan_800k_reject(self):
        """Salary ₹50,000 and loan ₹8,00,000 -> Reject (Limit: 15x = ₹7,50,000)."""
        cust = {"name": "High Borrow", "age": 30, "credit_score": 750, "salary": 50000, "current_loan_status": 0}
        res = underwrite(cust, 800000, tenure=60)
        self.assertEqual(res["status"], "Rejection")
        self.assertTrue(any("exceeds the maximum eligible limit" in r for r in res["failed_conditions"]))

    def test_39_salary_50k_loan_700k_pass(self):
        """Salary ₹50,000 and loan ₹7,00,000 -> Pass salary multiple validation (within ₹7,50,000 limit)."""
        cust = {"name": "Valid Multiple", "age": 30, "credit_score": 750, "salary": 50000, "current_loan_status": 0}
        # ₹7,00,000 at 12% for 60 months has EMI = ₹15,571 <= 50% salary (₹25,000)
        res = underwrite(cust, 700000, tenure=60)
        self.assertEqual(res["status"], "Approved")

    def test_40_foir_55_pct_reject(self):
        """FOIR 55% -> Reject (exceeds 50% limit)."""
        # Salary 50,000. Existing EMI = 20,000. Proposed loan 350,000 EMI @ 12% 60mo = ₹7,785.
        # Total EMI = 27,785 -> FOIR = 55.57% > 50%
        cust = {"name": "High FOIR", "age": 30, "credit_score": 750, "salary": 50000, "current_loan_status": 20000}
        res = underwrite(cust, 350000, tenure=60)
        self.assertEqual(res["status"], "Rejection")
        self.assertGreater(res["foir"], 50.0)
        self.assertTrue(any("FOIR" in r for r in res["failed_conditions"]))

    def test_41_foir_45_pct_pass(self):
        """FOIR 45% -> Pass (within 50% limit)."""
        # Salary 50,000. Existing EMI = 10,000. Proposed loan 550,000 EMI @ 12% 60mo = ₹12,234.
        # Total EMI = 22,234 -> FOIR = 44.47% <= 50%
        cust = {"name": "Safe FOIR", "age": 30, "credit_score": 750, "salary": 50000, "current_loan_status": 10000}
        res = underwrite(cust, 550000, tenure=60)
        self.assertEqual(res["status"], "Approved")
        self.assertLessEqual(res["foir"], 50.0)

    def test_42_tenure_36_months_reject(self):
        """Tenure 36 months -> Reject (below 48 months minimum)."""
        cust = {"name": "Short Tenure", "age": 30, "credit_score": 750, "salary": 50000, "current_loan_status": 0}
        res = underwrite(cust, 100000, tenure=36)
        self.assertEqual(res["status"], "Rejection")
        self.assertTrue(any("48 months" in r for r in res["failed_conditions"]))

    def test_43_tenure_60_months_pass(self):
        """Tenure 60 months -> Pass (within 48 to 72 months)."""
        cust = {"name": "Valid Tenure", "age": 30, "credit_score": 750, "salary": 50000, "current_loan_status": 0}
        res = underwrite(cust, 100000, tenure=60)
        self.assertEqual(res["status"], "Approved")
        self.assertEqual(res["tenure_months"], 60)

    def test_44_multiple_failed_conditions_all_displayed(self):
        """Combinations of multiple failed conditions: all failures must be reported simultaneously."""
        # Age 19 (fails), CIBIL 650 (fails), Loan 800k on 50k salary (fails), Tenure 36 (fails), FOIR > 50% (fails)
        cust = {"name": "Multi Fail", "age": 19, "credit_score": 650, "salary": 50000, "current_loan_status": 30000}
        res = underwrite(cust, 800000, tenure=36)
        self.assertEqual(res["status"], "Rejection")
        # Must report all failed conditions
        self.assertGreaterEqual(len(res["failed_conditions"]), 4)
        msg = res["message"]
        self.assertIn("Age Requirement", msg)
        self.assertIn("CIBIL Score", msg)
        self.assertIn("Loan Tenure", msg)
        self.assertIn("Maximum Loan Eligibility", msg)
        self.assertIn("FOIR", msg)

    def test_45_calculate_age_from_dob(self):
        """Verify automatic age calculation from Date of Birth."""
        from app import calculate_age_from_dob
        from datetime import date
        today = date.today()
        # 25 years ago
        dob_25 = f"{today.year - 25}-{today.month:02d}-{today.day:02d}"
        self.assertEqual(calculate_age_from_dob(dob_25), 25)
        # 19 years ago
        dob_19 = f"{today.year - 19}-{today.month:02d}-{today.day:02d}"
        self.assertEqual(calculate_age_from_dob(dob_19), 19)

    def test_46_form_app_backend_rejects_ineligible_customer(self):
        """Admin panel /add-customer strictly rejects customers failing eligibility rules."""
        # Test 1: Age 19 rejected
        r1 = self.form_client.post("/add-customer", data={
            "customerName": "Teen User",
            "phoneNumber": "9000000019",
            "age": "19",
            "city": "Delhi",
            "panNumber": "ABCDE1234F",
            "salary": "50000",
            "creditScore": "750",
            "currentLoan": "0"
        })
        self.assertEqual(r1.status_code, 200)
        self.assertIn(b"below the minimum required age of 21", r1.data)

        # Test 2: CIBIL 650 rejected
        r2 = self.form_client.post("/add-customer", data={
            "customerName": "Low Score",
            "phoneNumber": "9000000650",
            "age": "25",
            "city": "Delhi",
            "panNumber": "ABCDE1234F",
            "salary": "50000",
            "creditScore": "650",
            "currentLoan": "0"
        })
        self.assertEqual(r2.status_code, 200)
        self.assertIn(b"below the minimum required threshold of 700", r2.data)

        # Test 3: Existing EMIs exceeding 50% salary rejected
        r3 = self.form_client.post("/add-customer", data={
            "customerName": "High Debt",
            "phoneNumber": "9000000055",
            "age": "30",
            "city": "Delhi",
            "panNumber": "ABCDE1234F",
            "salary": "50000",
            "creditScore": "750",
            "currentLoan": "30000"  # 60% FOIR
        })
        self.assertEqual(r3.status_code, 200)
        self.assertIn(b"exceeds the maximum allowed 50% FOIR limit", r3.data)


    def test_47_preliminary_eligibility_and_status_distinction(self):
        """Verify registration success uses Preliminary Loan Eligibility and distinct statuses."""
        sess_id = "sess_prelim_test_user"
        test_phone = "9870001122"
        expected_cid = f"cust{test_phone}"

        # Clean up any existing record
        if os.path.exists("customers.json"):
            try:
                with open("customers.json", "r") as f:
                    cdata = json.load(f)
                if expected_cid in cdata:
                    del cdata[expected_cid]
                    with open("customers.json", "w") as f:
                        json.dump(cdata, f, indent=2)
            except Exception:
                pass

        self.client.post("/chat", json={"session_id": sess_id, "user_input": "I am a new customer"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "Kavita Rao"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": test_phone})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "kavita@example.com"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "28, Pune"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "ABCDE1234F"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "40000"})  # 40,000 * 15 = 600,000
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "0"})
        r_final = self.client.post("/chat", json={"session_id": sess_id, "user_input": "780"}).get_json()

        text = r_final["response_text"]
        # Required wording checks
        self.assertIn("Preliminary Loan Eligibility", text)
        self.assertIn("600,000", text)
        self.assertIn("Preliminary Eligible", text)
        self.assertIn("This is an initial eligibility estimate based on your monthly net salary (15x salary). Final loan approval is subject to CIBIL verification, age eligibility, FOIR calculation, document verification and the lender's final assessment.", text)
        self.assertNotIn("Eligible Loan Limit", text)

    # ────────────────────────────────────────────────────────────────
    # 10. AI Engine & Token Monitoring Dashboard Tests
    # ────────────────────────────────────────────────────────────────
    def _create_isolated_store(self, tmp_path, **kwargs):
        from monitoring import AIMonitoringStore
        return AIMonitoringStore(
            local_path=tmp_path,
            configured_model=kwargs.get("configured_model", "gemini-3.5-flash-lite"),
            active_model=kwargs.get("active_model", "gemini-3.5-flash-lite"),
            secondary_model=kwargs.get("secondary_model", "gemini-3.5-flash-lite"),
            llm_available=kwargs.get("llm_available", True),
            firebase_db_url=kwargs.get("firebase_db_url", ""),
            firebase_api_key=kwargs.get("firebase_api_key", ""),
        )

    def test_48_gemini_success_token_usage_and_no_cost_fields(self):
        """Scenario 1 & 5: Primary Gemini success records exact usage_metadata tokens without cost estimates."""
        import tempfile
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = os.path.join(tmpdir, "stats.json")
            orig_store = main_app.monitoring_store
            orig_llm = main_app.llm
            try:
                main_app.monitoring_store = self._create_isolated_store(stats_path, llm_available=True)
                mock_llm = MagicMock()
                mock_llm.model = "models/gemini-3.5-flash-lite"
                mock_llm.invoke.return_value = SimpleNamespace(
                    content="Personal loans carry fixed 12% p.a. interest here.",
                    usage_metadata={"input_tokens": 142, "output_tokens": 28, "total_tokens": 170},
                    response_metadata={},
                )
                main_app.llm = mock_llm

                resp = self.client.post("/chat", json={
                    "session_id": "sess_mon_gemini_ok",
                    "user_input": "How does compounding work on your personal loans?",
                    "request_id": "req_gemini_ok_1",
                })
                self.assertEqual(resp.status_code, 200)
                data = resp.get_json()
                mon = data["monitoring"]

                self.assertEqual(mon["engine_status"]["gemini_status"], "ACTIVE")
                self.assertEqual(mon["engine_status"]["local_fallback_status"], "STANDBY")
                self.assertEqual(mon["engine_status"]["active_model"], "gemini-3.5-flash-lite")
                self.assertIsNotNone(mon["engine_status"]["last_gemini_success_at"])
                self.assertEqual(mon["session"]["tokens"]["input_tokens"], 142)
                self.assertEqual(mon["session"]["tokens"]["output_tokens"], 28)
                self.assertEqual(mon["session"]["tokens"]["total_tokens"], 170)
                self.assertEqual(mon["session"]["requests"]["gemini_api_requests"], 1)
                self.assertEqual(mon["session"]["requests"]["gemini_success_count"], 1)
                self.assertEqual(mon["session"]["requests"]["gemini_failure_count"], 0)
                self.assertEqual(mon["session"]["breakdown"]["gemini_primary"], 1)
                self.assertEqual(mon["session"]["percentages"]["gemini_pct"], 100.0)
                # Ensure no cost/monetary keys exist anywhere in monitoring payload
                mon_serialized = json.dumps(mon).lower()
                self.assertNotIn("estimated_cost", mon_serialized)
                self.assertNotIn("usd", mon_serialized)
            finally:
                main_app.monitoring_store = orig_store
                main_app.llm = orig_llm

    def test_49_gemini_unavailable_routes_to_local_error_fallback(self):
        """Scenario 2: When Gemini llm is None, conversational input uses local_error_fallback with 0 tokens."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = os.path.join(tmpdir, "stats.json")
            orig_store = main_app.monitoring_store
            orig_llm = main_app.llm
            try:
                main_app.monitoring_store = self._create_isolated_store(stats_path, llm_available=False)
                main_app.llm = None

                resp = self.client.post("/chat", json={
                    "session_id": "sess_mon_unavail",
                    "user_input": "Tell me something helpful about loan tenure",
                    "request_id": "req_unavail_1",
                })
                self.assertEqual(resp.status_code, 200)
                mon = resp.get_json()["monitoring"]

                self.assertEqual(mon["engine_status"]["gemini_status"], "INACTIVE")
                self.assertEqual(mon["engine_status"]["local_fallback_status"], "ACTIVE")
                self.assertEqual(mon["session"]["breakdown"]["local_error_fallback"], 1)
                self.assertEqual(mon["session"]["breakdown"]["local_rules"], 0)
                self.assertEqual(mon["session"]["tokens"]["total_tokens"], 0)
                self.assertEqual(mon["session"]["requests"]["gemini_api_requests"], 0)
                self.assertIn("unavailable", (mon["engine_status"]["fallback_reason"] or "").lower())
            finally:
                main_app.monitoring_store = orig_store
                main_app.llm = orig_llm

    def test_50_gemini_quota_rate_limit_error_and_secondary_fallback(self):
        """Scenario 3: Quota 429 triggers secondary model / local fallback and marks Gemini ERROR cleanly."""
        import tempfile
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = os.path.join(tmpdir, "stats.json")
            orig_store = main_app.monitoring_store
            orig_llm = main_app.llm
            try:
                main_app.monitoring_store = self._create_isolated_store(stats_path, llm_available=True)
                mock_llm = MagicMock()
                mock_llm.model = "models/gemini-3.5-flash-lite"
                mock_llm.invoke.side_effect = RuntimeError("429 ResourceExhausted: Quota exceeded for key AIzaSySecretKeyShouldNotLeak12345")
                main_app.llm = mock_llm

                resp = self.client.post("/chat", json={
                    "session_id": "sess_mon_429",
                    "user_input": "Explain prepayment charges in plain language",
                    "request_id": "req_429_1",
                })
                self.assertEqual(resp.status_code, 200)
                mon = resp.get_json()["monitoring"]

                self.assertEqual(mon["engine_status"]["gemini_status"], "ERROR")
                self.assertEqual(mon["engine_status"]["local_fallback_status"], "ACTIVE")
                self.assertEqual(mon["session"]["requests"]["gemini_api_requests"], 1)
                self.assertEqual(mon["session"]["requests"]["gemini_failure_count"], 1)
                self.assertEqual(mon["session"]["breakdown"]["local_error_fallback"], 1)
                self.assertEqual(mon["session"]["tokens"]["total_tokens"], 0)
                reason = mon["engine_status"]["fallback_reason"] or ""
                self.assertIn("quota", reason.lower())
                self.assertNotIn("AIzaSy", json.dumps(mon))

                # Also verify secondary Gemini model path when active model differs from secondary model
                mock_pro = MagicMock()
                mock_pro.model = "models/gemini-2.5-pro"
                mock_pro.invoke.side_effect = RuntimeError("429 ResourceExhausted")
                main_app.llm = mock_pro
                with patch("app.ChatGoogleGenerativeAI") as mock_ctor, patch.object(main_app, "API_KEY", "test_key"):
                    mock_sec = MagicMock()
                    mock_sec.invoke.return_value = SimpleNamespace(
                        content="Prepayment details clarified.",
                        usage_metadata={"input_tokens": 90, "output_tokens": 12, "total_tokens": 102},
                        response_metadata={},
                    )
                    mock_ctor.return_value = mock_sec

                    resp2 = self.client.post("/chat", json={
                        "session_id": "sess_mon_429",
                        "user_input": "Can I close my loan early?",
                        "request_id": "req_sec_2",
                    })
                    mon2 = resp2.get_json()["monitoring"]
                    self.assertEqual(mon2["engine_status"]["gemini_status"], "ACTIVE")
                    self.assertEqual(mon2["session"]["breakdown"]["gemini_secondary"], 1)
                    self.assertEqual(mon2["session"]["requests"]["gemini_api_requests"], 3)
                    self.assertEqual(mon2["session"]["requests"]["gemini_failure_count"], 2)
                    self.assertEqual(mon2["session"]["requests"]["gemini_success_count"], 1)
                    self.assertEqual(mon2["session"]["tokens"]["total_tokens"], 102)
            finally:
                main_app.monitoring_store = orig_store
                main_app.llm = orig_llm

    def test_51_local_rule_engine_distinct_from_fallback_and_zero_tokens(self):
        """Scenario 4: Deterministic rule queries count under local_rules with 0 Gemini tokens/attempts."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = os.path.join(tmpdir, "stats.json")
            orig_store = main_app.monitoring_store
            try:
                main_app.monitoring_store = self._create_isolated_store(stats_path, llm_available=True)

                resp = self.client.post("/chat", json={
                    "session_id": "sess_mon_rules",
                    "user_input": "Calculate EMI for 500000",
                    "request_id": "req_rule_1",
                })
                self.assertEqual(resp.status_code, 200)
                mon = resp.get_json()["monitoring"]

                self.assertEqual(mon["session"]["breakdown"]["local_rules"], 1)
                self.assertEqual(mon["session"]["breakdown"]["local_error_fallback"], 0)
                self.assertEqual(mon["session"]["requests"]["gemini_api_requests"], 0)
                self.assertEqual(mon["session"]["tokens"]["total_tokens"], 0)
                self.assertEqual(mon["session"]["percentages"]["local_pct"], 100.0)
                self.assertEqual(mon["engine_status"]["gemini_status"], "ACTIVE")
                self.assertEqual(mon["engine_status"]["local_fallback_status"], "STANDBY")
            finally:
                main_app.monitoring_store = orig_store

    def test_52_idempotent_request_id_prevents_duplicate_counting(self):
        """Idempotency: Retrying with the same request_id never double-counts tokens or requests."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = os.path.join(tmpdir, "stats.json")
            store = self._create_isolated_store(stats_path, llm_available=True)

            first = store.record_event(
                session_id="sess_dup",
                engine_category="gemini_primary",
                latency_ms=215.4,
                request_id="req_unique_999",
                token_usage={"input_tokens": 50, "output_tokens": 20, "total_tokens": 70},
                gemini_attempts=1,
                gemini_successes=1,
            )
            duplicate = store.record_event(
                session_id="sess_dup",
                engine_category="gemini_primary",
                latency_ms=215.4,
                request_id="req_unique_999",
                token_usage={"input_tokens": 50, "output_tokens": 20, "total_tokens": 70},
                gemini_attempts=1,
                gemini_successes=1,
            )
            self.assertTrue(first)
            self.assertFalse(duplicate)
            snap = store.get_snapshot("sess_dup")
            self.assertEqual(snap["all_time"]["tokens"]["total_tokens"], 70)
            self.assertEqual(snap["all_time"]["requests"]["total_user_messages"], 1)
            self.assertEqual(snap["all_time"]["requests"]["gemini_api_requests"], 1)

    def test_53_persistence_across_flask_restart_and_firebase_sync(self):
        """Scenario 6: Stats persist after simulated Flask restart and sync cleanly to Firebase RTDB."""
        import tempfile
        from monitoring import AIMonitoringStore

        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = os.path.join(tmpdir, "persist.json")

            store1 = self._create_isolated_store(stats_path, llm_available=True)
            store1.record_event(
                session_id="sess_restart_a",
                engine_category="gemini_primary",
                latency_ms=180.0,
                request_id="req_persist_1",
                token_usage={"input_tokens": 110, "output_tokens": 45, "total_tokens": 155},
                gemini_attempts=1,
                gemini_successes=1,
            )
            store1.record_event(
                session_id="sess_restart_a",
                engine_category="local_rules",
                latency_ms=4.2,
                request_id="req_persist_2",
            )

            # Simulate Flask restart by instantiating a brand new store reading the same persisted file
            store2 = AIMonitoringStore(local_path=stats_path, llm_available=True)
            snap2 = store2.get_snapshot("sess_restart_a")
            self.assertEqual(snap2["all_time"]["tokens"]["input_tokens"], 110)
            self.assertEqual(snap2["all_time"]["tokens"]["output_tokens"], 45)
            self.assertEqual(snap2["all_time"]["tokens"]["total_tokens"], 155)
            self.assertEqual(snap2["all_time"]["breakdown"]["gemini_primary"], 1)
            self.assertEqual(snap2["all_time"]["breakdown"]["local_rules"], 1)
            self.assertEqual(snap2["session"]["requests"]["total_user_messages"], 2)
            # Duplicate replay after restart is still prevented
            self.assertFalse(store2.record_event(
                session_id="sess_restart_a",
                engine_category="gemini_primary",
                latency_ms=100.0,
                request_id="req_persist_1",
                token_usage={"input_tokens": 110, "output_tokens": 45, "total_tokens": 155},
                gemini_attempts=1,
                gemini_successes=1,
            ))

            # Verify mocked Firebase RTDB persistence path
            fb_memory = {}

            def fake_get(url, timeout=3):
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = fb_memory.get("monitoring")
                return resp

            def fake_put(url, json=None, timeout=3):
                resp = MagicMock()
                resp.status_code = 200
                if "/monitoring/global.json" in url:
                    fb_memory.setdefault("monitoring", {})["global"] = json
                elif "/monitoring/sessions/" in url:
                    sess_key = url.split("/monitoring/sessions/")[1].split(".json")[0]
                    fb_memory.setdefault("monitoring", {}).setdefault("sessions", {})[sess_key] = json
                elif "/monitoring/processed_request_ids.json" in url:
                    fb_memory.setdefault("monitoring", {})["processed_request_ids"] = json
                return resp

            with patch("monitoring.requests.get", side_effect=fake_get), patch("monitoring.requests.put", side_effect=fake_put):
                fb_store = AIMonitoringStore(
                    local_path="",
                    firebase_db_url="https://demo-project.firebaseio.com",
                    firebase_api_key="dummy_fb_key",
                    llm_available=True,
                )
                fb_store.record_event(
                    session_id="sess_fb",
                    engine_category="gemini_primary",
                    latency_ms=140.0,
                    request_id="req_fb_1",
                    token_usage={"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
                    gemini_attempts=1,
                    gemini_successes=1,
                )
                fb_restarted = AIMonitoringStore(
                    local_path="",
                    firebase_db_url="https://demo-project.firebaseio.com",
                    firebase_api_key="dummy_fb_key",
                    llm_available=True,
                )
                fb_snap = fb_restarted.get_snapshot("sess_fb")
                self.assertEqual(fb_snap["engine_status"]["persistence_mode"], "firebase+local")
                self.assertEqual(fb_snap["all_time"]["tokens"]["total_tokens"], 100)
                self.assertEqual(fb_snap["session"]["requests"]["gemini_api_requests"], 1)

    def test_54_monitoring_endpoint_session_vs_all_time_views(self):
        """Scenario 7: /api/monitoring returns independent session and cumulative all_time views."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            stats_path = os.path.join(tmpdir, "views.json")
            orig_store = main_app.monitoring_store
            try:
                store = self._create_isolated_store(stats_path, llm_available=True)
                main_app.monitoring_store = store

                store.record_event(
                    session_id="sess_view_1",
                    engine_category="gemini_primary",
                    latency_ms=200.0,
                    request_id="req_v1",
                    token_usage={"input_tokens": 100, "output_tokens": 25, "total_tokens": 125},
                    gemini_attempts=1,
                    gemini_successes=1,
                )
                store.record_event(
                    session_id="sess_view_2",
                    engine_category="local_rules",
                    latency_ms=5.0,
                    request_id="req_v2",
                )

                r1 = self.client.get("/api/monitoring?session_id=sess_view_1")
                self.assertEqual(r1.status_code, 200)
                d1 = r1.get_json()
                self.assertEqual(d1["session"]["tokens"]["total_tokens"], 125)
                self.assertEqual(d1["session"]["requests"]["total_user_messages"], 1)
                self.assertEqual(d1["all_time"]["tokens"]["total_tokens"], 125)
                self.assertEqual(d1["all_time"]["requests"]["total_user_messages"], 2)
                self.assertEqual(d1["all_time"]["percentages"]["gemini_pct"], 50.0)
                self.assertEqual(d1["all_time"]["percentages"]["local_pct"], 50.0)

                r2 = self.client.get("/api/monitoring?session_id=sess_view_2")
                d2 = r2.get_json()
                self.assertEqual(d2["session"]["tokens"]["total_tokens"], 0)
                self.assertEqual(d2["session"]["breakdown"]["local_rules"], 1)
                self.assertEqual(d2["all_time"]["tokens"]["total_tokens"], 125)
            finally:
                main_app.monitoring_store = orig_store

    # ────────────────────────────────────────────────────────────────
    # 11. Conversational Routing & Data Integrity Regression Tests
    # ────────────────────────────────────────────────────────────────
    def _advance_onboarding_to_cibil(self, sess_id, phone="9811223344", age_city="23, Delhi", name="Aarav Verma"):
        """Helper to step a fresh session strictly to ASK_CREDIT_SCORE."""
        main_app.session_data.pop(sess_id, None)
        main_app.session_histories.pop(sess_id, None)
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "I am a new customer"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": name})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": phone})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "aarav@example.com"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": age_city})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "ABCDE1234F"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "60000"})
        self.client.post("/chat", json={"session_id": sess_id, "user_input": "0"})

    def test_55_why_more_than_700_during_cibil_onboarding_uses_gemini_and_preserves_state(self):
        """Scenario 1: 'Why do I need more than 700?' during CIBIL onboarding goes to Gemini & does NOT complete registration."""
        import tempfile
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_store = main_app.monitoring_store
            orig_llm = main_app.llm
            try:
                main_app.monitoring_store = self._create_isolated_store(os.path.join(tmpdir, "s.json"), llm_available=True)
                mock_llm = MagicMock()
                mock_llm.model = "models/gemini-3.5-flash-lite"
                mock_llm.invoke.return_value = SimpleNamespace(
                    content="A CIBIL score of 700 or above indicates stronger repayment history and lower credit risk under this demo project's threshold.",
                    usage_metadata={"input_tokens": 180, "output_tokens": 30, "total_tokens": 210},
                    response_metadata={},
                )
                main_app.llm = mock_llm

                sess_id = "sess_bug1_cibil_q"
                self._advance_onboarding_to_cibil(sess_id, phone="9811220001")
                self.assertEqual(main_app.session_data[sess_id]["onboarding_state"], "ASK_CREDIT_SCORE")

                resp = self.client.post("/chat", json={
                    "session_id": sess_id,
                    "user_input": "Why do I need more than 700?",
                })
                data = resp.get_json()
                reply = data["response_text"]

                self.assertIsNone(data.get("orchestration_command"))
                self.assertNotIn("Registration Completed Successfully", reply)
                self.assertIn("repayment history", reply.lower())
                self.assertIn("cibil", reply.lower())
                # Pending onboarding state must remain unchanged
                self.assertEqual(main_app.session_data[sess_id]["onboarding_state"], "ASK_CREDIT_SCORE")
                self.assertNotIn("credit_score", main_app.session_data[sess_id]["onboarding_data"])
                mock_llm.invoke.assert_called_once()
                # Verify SystemMessage only appears at index 0 (langchain-google-genai constraint)
                passed_msgs = mock_llm.invoke.call_args[0][0]
                self.assertIsInstance(passed_msgs[0], main_app.SystemMessage)
                for idx, msg in enumerate(passed_msgs[1:], start=1):
                    self.assertNotIsInstance(msg, main_app.SystemMessage, f"Unexpected SystemMessage at pos {idx}")
                self.assertEqual(data["monitoring"]["session"]["breakdown"]["gemini_primary"], 1)
            finally:
                main_app.monitoring_store = orig_store
                main_app.llm = orig_llm

    def test_56_invalid_cibil_200_then_general_question_never_substitutes_default(self):
        """Scenario 2 & 3: Invalid CIBIL 200 and 400 stay rejected without substituting 700/750; question preserves state."""
        import tempfile
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_store = main_app.monitoring_store
            orig_llm = main_app.llm
            try:
                main_app.monitoring_store = self._create_isolated_store(os.path.join(tmpdir, "s.json"), llm_available=True)
                mock_llm = MagicMock()
                mock_llm.model = "models/gemini-3.5-flash-lite"
                mock_llm.invoke.return_value = SimpleNamespace(
                    content="FOIR stands for Fixed Obligation to Income Ratio, capped at 50% in our demonstration rules.",
                    usage_metadata={"input_tokens": 120, "output_tokens": 22, "total_tokens": 142},
                    response_metadata={},
                )
                main_app.llm = mock_llm

                sess_id = "sess_bug2_cibil_200_400"
                # Verify invalid age 89 is rejected before accepting 23, Delhi
                main_app.session_data.pop(sess_id, None)
                self.client.post("/chat", json={"session_id": sess_id, "user_input": "I am a new customer"})
                self.client.post("/chat", json={"session_id": sess_id, "user_input": "Rohan Kapoor"})
                self.client.post("/chat", json={"session_id": sess_id, "user_input": "9811220002"})
                self.client.post("/chat", json={"session_id": sess_id, "user_input": "rohan@example.com"})
                r_age_bad = self.client.post("/chat", json={"session_id": sess_id, "user_input": "89, Delhi"}).get_json()
                self.assertIn("maximum eligible age", r_age_bad["response_text"].lower())
                self.assertEqual(main_app.session_data[sess_id]["onboarding_state"], "ASK_AGE_CITY")
                r_age_ok = self.client.post("/chat", json={"session_id": sess_id, "user_input": "23, Delhi"}).get_json()
                self.assertIn("PAN", r_age_ok["response_text"])
                self.assertEqual(main_app.session_data[sess_id]["onboarding_data"]["age"], 23)

                self.client.post("/chat", json={"session_id": sess_id, "user_input": "ABCDE1234F"})
                self.client.post("/chat", json={"session_id": sess_id, "user_input": "60000"})
                self.client.post("/chat", json={"session_id": sess_id, "user_input": "0"})

                # Enter 200 -> rejected, onboarding still ASK_CREDIT_SCORE, no score saved
                r_200 = self.client.post("/chat", json={"session_id": sess_id, "user_input": "200"}).get_json()
                self.assertIn("200", r_200["response_text"])
                self.assertNotIn("Registration Completed", r_200["response_text"])
                self.assertEqual(main_app.session_data[sess_id]["onboarding_state"], "ASK_CREDIT_SCORE")
                self.assertNotIn("credit_score", main_app.session_data[sess_id]["onboarding_data"])

                # Ask general question during CIBIL prompt -> Gemini answers, onboarding remains ASK_CREDIT_SCORE
                r_q = self.client.post("/chat", json={"session_id": sess_id, "user_input": "What is FOIR?"}).get_json()
                self.assertIn("Fixed Obligation to Income Ratio", r_q["response_text"])
                self.assertNotIn("Registration Completed", r_q["response_text"])
                self.assertEqual(main_app.session_data[sess_id]["onboarding_state"], "ASK_CREDIT_SCORE")

                # Enter 400 -> rejected, onboarding remains incomplete
                r_400 = self.client.post("/chat", json={"session_id": sess_id, "user_input": "400"}).get_json()
                self.assertIn("400", r_400["response_text"])
                self.assertNotIn("Registration Completed", r_400["response_text"])
                self.assertEqual(main_app.session_data[sess_id]["onboarding_state"], "ASK_CREDIT_SCORE")
                self.assertNotIn("credit_score", main_app.session_data[sess_id]["onboarding_data"])

                # Try 'skip' -> rejected without default 750/700
                r_skip = self.client.post("/chat", json={"session_id": sess_id, "user_input": "skip"}).get_json()
                self.assertNotIn("Registration Completed", r_skip["response_text"])
                self.assertEqual(main_app.session_data[sess_id]["onboarding_state"], "ASK_CREDIT_SCORE")
            finally:
                main_app.monitoring_store = orig_store
                main_app.llm = orig_llm

    def test_57_valid_cibil_completes_with_exact_entered_score(self):
        """Scenario 4: Valid CIBIL completes onboarding recording the exact score (e.g. 785)."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_store = main_app.monitoring_store
            test_phone = "9811220003"
            expected_cid = f"cust{test_phone}"
            try:
                main_app.monitoring_store = self._create_isolated_store(os.path.join(tmpdir, "s.json"), llm_available=True)
                self._advance_onboarding_to_cibil("sess_exact_cibil", phone=test_phone)

                resp = self.client.post("/chat", json={"session_id": "sess_exact_cibil", "user_input": "785"}).get_json()
                reply = resp["response_text"]
                self.assertIn("Registration Completed Successfully", reply)
                self.assertIn("785", reply)
                self.assertEqual(main_app.session_data["sess_exact_cibil"]["credit_score"], 785)
                self.assertIsNone(main_app.session_data["sess_exact_cibil"].get("onboarding_state"))
            finally:
                main_app.monitoring_store = orig_store
                if os.path.exists("customers.json"):
                    try:
                        with open("customers.json", "r") as f:
                            cdata = json.load(f)
                        if expected_cid in cdata:
                            del cdata[expected_cid]
                            with open("customers.json", "w") as f:
                                json.dump(cdata, f, indent=2)
                    except Exception:
                        pass

    def test_58_question_with_number_700_when_verified_never_triggers_underwriting(self):
        """Scenario 5 & 6: Verified customer asking question with 700 or minimum loan amount does NOT trigger underwriting."""
        import tempfile
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_store = main_app.monitoring_store
            orig_llm = main_app.llm
            try:
                main_app.monitoring_store = self._create_isolated_store(os.path.join(tmpdir, "s.json"), llm_available=True)
                mock_llm = MagicMock()
                mock_llm.model = "models/gemini-3.5-flash-lite"
                mock_llm.invoke.return_value = SimpleNamespace(
                    content="A score of 700 helps demonstrate consistent repayment history.",
                    usage_metadata={"input_tokens": 90, "output_tokens": 15, "total_tokens": 105},
                    response_metadata={},
                )
                main_app.llm = mock_llm

                sess_id = "sess_verified_no_false_underwrite"
                self.client.post("/orchestrate", json={
                    "step": "VERIFY_KYC",
                    "session_id": sess_id,
                    "customer_info": {"customer_id": "cust01"},
                })

                # Question containing 700
                r_q700 = self.client.post("/chat", json={
                    "session_id": sess_id,
                    "user_input": "Why do I need more than 700?",
                }).get_json()
                self.assertIsNone(r_q700.get("orchestration_command"))
                self.assertNotIn("Final Approved", r_q700["response_text"])
                self.assertIn("700", r_q700["response_text"])

                # Question asking minimum loan amount
                mock_llm.invoke.return_value = SimpleNamespace(
                    content="There is no rigid minimum floor above ₹0 in the demo engine, subject to 15x salary and 50% FOIR.",
                    usage_metadata={"input_tokens": 95, "output_tokens": 20, "total_tokens": 115},
                    response_metadata={},
                )
                r_min = self.client.post("/chat", json={
                    "session_id": sess_id,
                    "user_input": "What is the minimum loan amount?",
                }).get_json()
                self.assertIsNone(r_min.get("orchestration_command"))
                self.assertNotIn("Final Approved", r_min["response_text"])

                # Bare ambiguous number 700 (like a CIBIL score) asks clarification instead of approving ₹700
                r_bare_700 = self.client.post("/chat", json={
                    "session_id": sess_id,
                    "user_input": "700",
                }).get_json()
                self.assertIsNone(r_bare_700.get("orchestration_command"))
                self.assertIn("ambiguous", r_bare_700["response_text"].lower())
                self.assertIn("specify", r_bare_700["response_text"].lower())

                # Asking about customer ID format does not falsely match 'customer' as a KYC ID
                r_cust_word = self.client.post("/chat", json={
                    "session_id": sess_id,
                    "user_input": "How do I find my customer ID?",
                }).get_json()
                self.assertIsNone(r_cust_word.get("orchestration_command"))
            finally:
                main_app.monitoring_store = orig_store
                main_app.llm = orig_llm

    def test_59_explicit_5_lakh_loan_request_extracts_exact_amount(self):
        """Scenario 7: Explicit request for ₹5,00,000 triggers UNDERWRITE with exact amount 500000."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_store = main_app.monitoring_store
            try:
                main_app.monitoring_store = self._create_isolated_store(os.path.join(tmpdir, "s.json"), llm_available=True)
                sess_id = "sess_explicit_5lakh"
                self.client.post("/orchestrate", json={
                    "step": "VERIFY_KYC",
                    "session_id": sess_id,
                    "customer_info": {"customer_id": "cust01"},
                })

                resp = self.client.post("/chat", json={
                    "session_id": sess_id,
                    "user_input": "I want to apply for a loan of ₹5,00,000",
                }).get_json()
                self.assertEqual(resp.get("orchestration_command"), "[[FLASK_CALL:UNDERWRITE]]")
                self.assertEqual(resp.get("loan_amount"), 500000.0)
            finally:
                main_app.monitoring_store = orig_store

    def test_60_gemini_failure_local_fallback_preserves_onboarding_and_does_not_fabricate(self):
        """Scenario 8 & 9: If Gemini errors mid-onboarding, safe fallback answers without completing onboarding or losing step."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_store = main_app.monitoring_store
            orig_llm = main_app.llm
            try:
                main_app.monitoring_store = self._create_isolated_store(os.path.join(tmpdir, "s.json"), llm_available=True)
                mock_llm = MagicMock()
                mock_llm.model = "models/gemini-3.5-flash-lite"
                mock_llm.invoke.side_effect = RuntimeError("503 Service Unavailable")
                main_app.llm = mock_llm

                sess_id = "sess_gemini_fail_onboarding"
                self._advance_onboarding_to_cibil(sess_id, phone="9811220004")

                r_fail = self.client.post("/chat", json={
                    "session_id": sess_id,
                    "user_input": "Why do I need more than 700?",
                }).get_json()

                reply = r_fail["response_text"]
                self.assertIsNone(r_fail.get("orchestration_command"))
                self.assertNotIn("Registration Completed", reply)
                self.assertIn("repayment history", reply.lower())
                self.assertEqual(main_app.session_data[sess_id]["onboarding_state"], "ASK_CREDIT_SCORE")
                self.assertNotIn("credit_score", main_app.session_data[sess_id]["onboarding_data"])
                self.assertEqual(r_fail["monitoring"]["engine_status"]["local_fallback_status"], "ACTIVE")
                self.assertEqual(r_fail["monitoring"]["session"]["breakdown"]["local_error_fallback"], 1)

                # Test general interruption at ASK_PAN preserves pending step cleanly too
                sess_pan = "sess_pan_interrupt"
                main_app.session_data.pop(sess_pan, None)
                self.client.post("/chat", json={"session_id": sess_pan, "user_input": "I am a new customer"})
                self.client.post("/chat", json={"session_id": sess_pan, "user_input": "Meera Nair"})
                self.client.post("/chat", json={"session_id": sess_pan, "user_input": "9811220005"})
                self.client.post("/chat", json={"session_id": sess_pan, "user_input": "meera@example.com"})
                self.client.post("/chat", json={"session_id": sess_pan, "user_input": "27, Pune"})
                self.assertEqual(main_app.session_data[sess_pan]["onboarding_state"], "ASK_PAN")

                r_pan_q = self.client.post("/chat", json={
                    "session_id": sess_pan,
                    "user_input": "What happens after registration?",
                }).get_json()
                self.assertEqual(main_app.session_data[sess_pan]["onboarding_state"], "ASK_PAN")
                self.assertEqual(main_app.session_data[sess_pan]["onboarding_data"]["age"], 27)
                self.assertEqual(main_app.session_data[sess_pan]["onboarding_data"]["city"], "Pune")
                self.assertIn("PAN", r_pan_q["response_text"])
            finally:
                main_app.monitoring_store = orig_store
                main_app.llm = orig_llm

    def test_61_previous_assistant_numbers_never_trigger_underwriting_or_llm_command_injection(self):
        """Scenario 10: Prior assistant numbers & hallucinated LLM [[FLASK_CALL:...]] never trigger underwriting."""
        import tempfile
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as tmpdir:
            orig_store = main_app.monitoring_store
            orig_llm = main_app.llm
            try:
                main_app.monitoring_store = self._create_isolated_store(os.path.join(tmpdir, "s.json"), llm_available=True)
                sess_id = "sess_prev_nums"
                self.client.post("/orchestrate", json={
                    "step": "VERIFY_KYC",
                    "session_id": sess_id,
                    "customer_info": {"customer_id": "cust01"},
                })
                # Simulate prior assistant message containing lots of numbers in chat history
                hist = main_app.get_session_history(sess_id)
                hist.append(main_app.AIMessage(content="Preliminary Loan Eligibility: Up to ₹12,00,000. Minimum score 700. Sample EMI ₹11,122."))

                # Mock Gemini returning a hallucinated command token from stale context
                mock_llm = MagicMock()
                mock_llm.model = "models/gemini-3.5-flash-lite"
                mock_llm.invoke.return_value = SimpleNamespace(
                    content="FOIR caps monthly EMIs at 50% of salary.\n[[FLASK_CALL:UNDERWRITE]]",
                    usage_metadata={"input_tokens": 110, "output_tokens": 18, "total_tokens": 128},
                    response_metadata={},
                )
                main_app.llm = mock_llm

                r = self.client.post("/chat", json={
                    "session_id": sess_id,
                    "user_input": "Thanks! Can you explain FOIR in short?",
                }).get_json()
                self.assertIsNone(r.get("orchestration_command"))
                self.assertNotIn("FLASK_CALL", r["response_text"])
                self.assertIn("FOIR", r["response_text"])
            finally:
                main_app.monitoring_store = orig_store
                main_app.llm = orig_llm


if __name__ == "__main__":
    unittest.main()
