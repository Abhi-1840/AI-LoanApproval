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


if __name__ == "__main__":
    unittest.main()
