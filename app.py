import os
import re
import json
import time
import smtplib
import requests
import io
import warnings
from datetime import datetime, timedelta, timezone, date
from email.message import EmailMessage

# Suppress cosmetic dependency mismatch warning for clean terminal logs
warnings.filterwarnings("ignore", message=r".*urllib3.*or chardet.*doesn't match a supported version!.*")

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

try:
    from fpdf import FPDF
except ImportError:
    FPDF = None

try:
    from xhtml2pdf import pisa
except ImportError:
    pisa = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:
    ChatGoogleGenerativeAI = None

try:
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
except Exception:
    class SystemMessage:
        def __init__(self, content): self.content = content
    class HumanMessage:
        def __init__(self, content): self.content = content
    class AIMessage:
        def __init__(self, content): self.content = content

# ── Load environment variables from .env if present ──
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ── Config loading (graceful fallback so the app can start without config.json) ──
if os.path.exists("/etc/secrets/config.json"):
    CONFIG_PATH = "/etc/secrets/config.json"
else:
    CONFIG_PATH = "config.json"

config = {}
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
    except Exception as e:
        print(f"[WARNING] Could not read {CONFIG_PATH}: {e}. Using defaults.")
else:
    print(f"[INFO] {CONFIG_PATH} not found. Checking environment variables.")

# Read from environment variables first, falling back to config.json
FIREBASE_DB_URL = os.environ.get("FIREBASE_DATABASE_URL", config.get("firebase_database_url", "")).rstrip("/")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", config.get("firebase_api_key", ""))
API_KEY = os.environ.get("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", config.get("gemini_api_key", "")))
MODEL_NAME = os.environ.get("LLM_MODEL", config.get("llm_model", "gemini-3.5-flash-lite"))
MODEL_TEMP = float(os.environ.get("LLM_TEMPERATURE", config.get("llm_temperature", 0.7)))

GMAIL_USER = os.environ.get("GMAIL_USER", config.get("gmail_user", ""))
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", config.get("gmail_app_password", ""))
GMAIL_FROM = os.environ.get("GMAIL_FROM", config.get("gmail_from", GMAIL_USER))

if API_KEY:
    os.environ["GOOGLE_API_KEY"] = API_KEY
    os.environ["GENAI_API_KEY"] = API_KEY
    os.environ["GOOGLE_GENAI_API_KEY"] = API_KEY
    os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"

app = Flask(__name__, static_folder="static", static_url_path="/static", template_folder="templates")
CORS(app)

session_histories = {}
session_data = {}

# ── Dummy customers for offline testing (no Firebase needed) ──
DUMMY_CUSTOMERS = {
    "cust01": {
        "customer_id": "cust01", "name": "Ramesh S.", "email": "ramesh@example.com",
        "phone": "9876543210", "credit_score": 810, "salary": 80000,
        "city": "Delhi", "age": 35, "pannumber": "ABCDE1234F", "current_loan_status": "NA"
    },
    "cust10": {
        "customer_id": "cust10", "name": "Neha C.", "email": "neha@example.com",
        "phone": "8080808080", "credit_score": 740, "salary": 50000,
        "city": "Mumbai", "age": 28, "pannumber": "FGHIJ5678K", "current_loan_status": "NA"
    },
    "cust99": {
        "customer_id": "cust99", "name": "Low Score User", "email": "low@example.com",
        "phone": "7070707070", "credit_score": 580, "salary": 30000,
        "city": "Pune", "age": 25, "pannumber": "LMNOP9012Q", "current_loan_status": "NA"
    },
}

# ── LLM Initialization ──
llm = None
if ChatGoogleGenerativeAI and API_KEY:
    try:
        # Default to gemini-3.5-flash-lite or user-configured model
        active_model = MODEL_NAME if MODEL_NAME != "gemini-2.5-flash" else "gemini-3.5-flash-lite"
        llm = ChatGoogleGenerativeAI(
            model=active_model,
            google_api_key=API_KEY,
            temperature=MODEL_TEMP,
            safety_settings=None,
            timeout=10
        )
        print(f"[INFO] Google Gemini API loaded with model: {active_model}")
    except Exception as e:
        print(f"[WARNING] LLM could not be loaded: {e}. Using local fallback agent.")
        llm = None
else:
    print("[INFO] No Gemini API key set. Running in local fallback mode.")

LLM_SYSTEM_PROMPT = """
You are the Supervisor Agent for an AI Loan Sales & Approval assistant that coordinates three worker agents internally:
  1) Verification Agent — verifies customer IDs and fetches customer data.
  2) Underwriting Agent — calculates EMI, checks limits (loan <= 15x salary, credit >= 700, EMI <= 50% salary), decides Pre-Approve/Approve/Reject.
  3) Documentation Agent — prepares sanction letter content and confirms document dispatch.

RULES (very strict):
- You must behave as one Supervisor who coordinates the workflow smoothly.
- If the user provides a customer ID in the format custXXXX (case-insensitive, e.g. cust01, cust8171601302), the Supervisor MUST trigger a backend KYC call by replying with the token: `[[FLASK_CALL:VERIFY_KYC]]` on its own line.
- After KYC is successful (the backend returns customer profile data), when the user provides a loan amount (e.g. 500000, 5 lakhs), the Supervisor MUST trigger underwriting by replying with: `[[FLASK_CALL:UNDERWRITE]]` on its own line.
- If the user says they are a new customer or don't have a Customer ID, explain that they can register directly in this chat or follow the onboarding prompts.
- For general questions (EMI explanations, required documents, eligibility rules, greetings, etc.), respond clearly and concisely as a professional financial assistant (do NOT include any FLASK_CALL tokens).
- When a loan is approved, confirm: "Sanction letter sent to <email>."
- Do not expose your internal chain-of-thought or markdown code blocks for system commands.

Output rules summary:
- To trigger backend KYC: reply with `[[FLASK_CALL:VERIFY_KYC]]` on its own line.
- To trigger backend underwriting: reply with `[[FLASK_CALL:UNDERWRITE]]` on its own line.
- Otherwise, reply with friendly, professional conversational text.
"""

def get_session_history(session_id):
    if session_id not in session_histories:
        session_histories[session_id] = [SystemMessage(content=LLM_SYSTEM_PROMPT)]
    return session_histories[session_id]

def save_message_to_firebase(session_id, sender, message):
    if not FIREBASE_DB_URL:
        return
    try:
        url = f"{FIREBASE_DB_URL}/sessions/{session_id}/messages.json"
        if FIREBASE_API_KEY:
            url += f"?auth={FIREBASE_API_KEY}"
        data = {"timestamp": datetime.now(timezone.utc).isoformat(), "sender": sender, "message": message}
        requests.post(url, json=data, timeout=3)
    except Exception:
        pass  # Firebase is optional; silently skip if unavailable

def save_session_meta(session_id, meta):
    if not FIREBASE_DB_URL:
        return
    try:
        url = f"{FIREBASE_DB_URL}/sessions/{session_id}/meta.json"
        if FIREBASE_API_KEY:
            url += f"?auth={FIREBASE_API_KEY}"
        requests.patch(url, json=meta, timeout=3)
    except Exception:
        pass

def get_customer_from_firebase(customer_id):
    if not FIREBASE_DB_URL:
        return None
    try:
        url = f"{FIREBASE_DB_URL}/customers/{customer_id}.json"
        if FIREBASE_API_KEY:
            url += f"?auth={FIREBASE_API_KEY}"
        resp = requests.get(url, timeout=3)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data:
            return None
        kyc = data.get("kyc", {})
        return {
            "customer_id": customer_id,
            "name": kyc.get("name") or data.get("name"),
            "email": kyc.get("email") or data.get("email"),
            "phone": kyc.get("phone", ""),
            "pannumber": kyc.get("pannumber", ""),
            "city": kyc.get("city", ""),
            "age": kyc.get("age", ""),
            "credit_score": data.get("credit_score", 0),
            "pre_approved_limit": data.get("pre_approved_limit", 0),
            "salary": data.get("salary", 0),
            "current_loan_status": kyc.get("currentloan", "NA")
        }
    except Exception:
        return None

def verify_kyc(customer_id):
    """Try Firebase first; then local customers.json; then in-memory dummy customers."""
    cid = customer_id.lower().strip()

    # 1. Check Firebase
    c = get_customer_from_firebase(cid)
    if c:
        c["status"] = "Verification Successful"
        return c

    # 2. Check local customers.json (saved from Admin Panel)
    local_file = "customers.json"
    if os.path.exists(local_file):
        try:
            with open(local_file, "r") as f:
                saved = json.load(f)
            # Check exact or lowercase key
            match = saved.get(cid) or saved.get(customer_id)
            if match:
                res = match.copy()
                res["status"] = "Verification Successful"
                return res
        except Exception:
            pass

    # 3. Check built-in dummy customers
    dummy = DUMMY_CUSTOMERS.get(cid)
    if dummy:
        result = dummy.copy()
        result["status"] = "Verification Successful"
        return result

    return {"status": "Verification Failed", "message": "Customer ID not found"}

# ── Loan Calculation Logic ──

def parse_loan_amount_text(text):
    """
    Robust parser for loan amounts:
    Handles:
    - "5 lakhs", "5.5 lakh", "5 lac", "5L" -> 500000, 550000
    - "50k", "50 k" -> 50000
    - "5,00,000", "500000" -> 500000
    - "₹3,50,000" -> 350000
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text).lower().replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "").strip()

    # Match Lakhs: e.g. 5.5 lakh, 5 lakhs, 5 lac, 5l
    m_lakh = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakhs|lakh|lacs|lac|l)\b", t)
    if m_lakh:
        try:
            return float(m_lakh.group(1)) * 100000
        except Exception:
            pass

    # Match Thousands: e.g. 50k, 50 k
    m_k = re.search(r"(\d+(?:\.\d+)?)\s*k\b", t)
    if m_k:
        try:
            return float(m_k.group(1)) * 1000
        except Exception:
            pass

    # Match raw number >= 1000
    m_num = re.search(r"\b\d{4,}\b", t)
    if m_num:
        try:
            return float(m_num.group(0))
        except Exception:
            pass

    # Match 3 digit number (e.g. 500)
    m_num3 = re.search(r"\b\d{3}\b", t)
    if m_num3:
        try:
            return float(m_num3.group(0))
        except Exception:
            pass

    # Fallback to any digits
    m_digits = re.search(r"\d+", t)
    if m_digits:
        try:
            val = float(m_digits.group(0))
            if val > 0:
                return val
        except Exception:
            pass

    return None


def calculate_age_from_dob(dob_input):
    """
    Calculate age in whole years from Date of Birth string or date object.
    Supports formats: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, YYYY/MM/DD.
    """
    if not dob_input:
        return None
    if isinstance(dob_input, (date, datetime)):
        bdate = dob_input.date() if isinstance(dob_input, datetime) else dob_input
    else:
        s = str(dob_input).strip()
        bdate = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
            try:
                bdate = datetime.strptime(s, fmt).date()
                break
            except ValueError:
                continue
        if bdate is None:
            return None

    today = date.today()
    age = today.year - bdate.year - ((today.month, today.day) < (bdate.month, bdate.day))
    return age


def parse_tenure_months(text):
    """Extract tenure in months from text, e.g. '36 months', '3 years', 'tenure 60'."""
    if not text:
        return None
    t = str(text).lower()

    # Match "X years" / "X yr"
    m_yr = re.search(r"(\d+)\s*(?:years?|yrs?)\b", t)
    if m_yr:
        try:
            return int(m_yr.group(1)) * 12
        except Exception:
            pass

    # Match "X months" / "X mo"
    m_mo = re.search(r"(\d+)\s*(?:months?|mos?|m)\b", t)
    if m_mo:
        try:
            return int(m_mo.group(1))
        except Exception:
            pass

    # Match "tenure 36"
    m_ten = re.search(r"tenure\s*(?:of|is|:)?\s*(\d+)", t)
    if m_ten:
        try:
            val = int(m_ten.group(1))
            return val * 12 if val <= 6 else val
        except Exception:
            pass

    return None


def calculate_preapproved_limit_from_salary(salary):
    """Pre-approved limit = 15x monthly salary (simple rule)."""
    try:
        return float(salary) * 15
    except Exception:
        return 0

def determine_tenure_months(salary):
    """Assign loan tenure based on monthly salary band."""
    try:
        s = float(salary)
    except Exception:
        s = 0
    if s < 40000:
        return 48   # 4 years for lower salaries
    if s <= 80000:
        return 60   # 5 years for mid salaries
    return 72       # 6 years for higher salaries

def calculate_emi(principal, rate, months):
    """
    Standard EMI formula:
      EMI = P * r * (1+r)^n / ((1+r)^n - 1)
    where r = monthly interest rate, n = number of months.
    """
    r = (rate / 100) / 12
    if months <= 0:
        return None
    if r == 0:
        return principal / months
    return (principal * r * (1 + r) ** months) / ((1 + r) ** months - 1)

def save_customer_to_storage(customer_data):
    """Save customer to customers.json and Firebase (if configured)."""
    customer_id = customer_data["customer_id"].lower().strip()

    # 1. Save to local customers.json
    local_file = "customers.json"
    customers = {}
    if os.path.exists(local_file):
        try:
            with open(local_file, "r") as f:
                customers = json.load(f)
        except Exception:
            customers = {}

    customers[customer_id] = customer_data
    try:
        with open(local_file, "w") as f:
            json.dump(customers, f, indent=2)
        print(f"[INFO] Customer {customer_id} saved locally in {local_file}")
    except Exception as e:
        print(f"[ERROR] Could not save customer to {local_file}: {e}")

    # 2. Save to Firebase if configured
    if FIREBASE_DB_URL:
        try:
            url = f"{FIREBASE_DB_URL}/customers/{customer_id}.json"
            if FIREBASE_API_KEY:
                url += f"?auth={FIREBASE_API_KEY}"
            fb_payload = {
                "kyc": {
                    "name": customer_data.get("name"),
                    "phone": customer_data.get("phone"),
                    "email": customer_data.get("email"),
                    "age": customer_data.get("age"),
                    "city": customer_data.get("city"),
                    "pannumber": customer_data.get("pannumber"),
                    "currentloan": customer_data.get("current_loan_status", 0)
                },
                "salary": customer_data.get("salary"),
                "credit_score": customer_data.get("credit_score"),
                "pre_approved_limit": customer_data.get("pre_approved_limit")
            }
            requests.put(url, json=fb_payload, timeout=3)
            print(f"[INFO] Customer {customer_id} saved to Firebase")
        except Exception as e:
            print(f"[WARNING] Could not save customer to Firebase: {e}")


def underwrite(customer, loan_amount, tenure=None):
    """
    Rule-based underwriting engine enforcing all mandatory eligibility criteria:
    1. Age: Minimum 21 years and maximum 65 years.
    2. CIBIL Score: Minimum 700 (max 900).
    3. Maximum Loan Amount: Up to 15x applicant's monthly net salary.
    4. FOIR (Fixed Obligation to Income Ratio): Total monthly EMI obligations
       (existing EMIs + proposed loan EMI) must not exceed 50% of monthly net salary.
    5. Loan Tenure: Minimum 48 months and maximum 72 months.
    6. Interest Rate: Fixed 12% per annum.

    If multiple criteria fail, displays ALL failed conditions clearly.
    """
    if not isinstance(customer, dict):
        return {
            "status": "Rejection",
            "message": "Customer data is missing or invalid.",
            "failed_conditions": ["Missing or invalid customer data."]
        }

    parsed_amt = parse_loan_amount_text(loan_amount)
    if parsed_amt is None or parsed_amt <= 0:
        return {
            "status": "Rejection",
            "message": "Loan amount must be a valid number greater than zero.",
            "failed_conditions": ["Loan amount must be a valid number greater than zero."]
        }
    loan_amount = parsed_amt

    name = customer.get("name", "Customer")
    salary = float(customer.get("salary", 0) or 0)
    credit = int(customer.get("credit_score", 0) or 0)

    # ── Age Calculation (from DOB if present, otherwise direct age) ──
    dob_raw = customer.get("dob")
    age_calc = calculate_age_from_dob(dob_raw) if dob_raw else None
    if age_calc is not None:
        age = age_calc
    else:
        try:
            age = int(customer.get("age", 0) or 0)
        except Exception:
            age = 0

    # ── Loan Tenure (from argument, or salary bracket) ──
    if tenure is None:
        tenure = determine_tenure_months(salary)
    else:
        try:
            tenure = int(tenure)
        except Exception:
            tenure = determine_tenure_months(salary)

    # ── Maximum Loan Limit (15x Salary) ──
    limit = calculate_preapproved_limit_from_salary(salary)
    customer["pre_approved_limit"] = limit

    # ── Existing Monthly Debt Obligations ──
    curr_loan_raw = customer.get("current_loan_status") or customer.get("currentloan") or 0
    try:
        if isinstance(curr_loan_raw, str):
            clean_curr = re.sub(r"[^\d.]", "", curr_loan_raw)
            existing_emi = float(clean_curr) if clean_curr else 0.0
        else:
            existing_emi = float(curr_loan_raw)
    except Exception:
        existing_emi = 0.0

    # ── Proposed Loan EMI (at 12% p.a.) ──
    calc_tenure = tenure if tenure > 0 else 60
    emi = calculate_emi(loan_amount, 12, calc_tenure) or 0.0

    # ── Total Monthly EMI & FOIR Calculation ──
    total_monthly_emi = existing_emi + emi
    foir = (total_monthly_emi / salary) * 100.0 if salary > 0 else 100.0

    failed_reasons = []

    # 1. Age Validation (21 - 65 years)
    if age < 21:
        failed_reasons.append(
            f"Age Requirement: Applicant age ({age} years) is below the minimum required age of 21 years."
        )
    elif age > 65:
        failed_reasons.append(
            f"Age Requirement: Applicant age ({age} years) exceeds the maximum eligible age of 65 years."
        )

    # 2. CIBIL Score Validation (>= 700)
    if credit < 700:
        failed_reasons.append(
            f"CIBIL Score: Credit score ({credit}) is below the minimum required threshold of 700."
        )

    # 3. Tenure Validation (48 - 72 months)
    if tenure < 48:
        failed_reasons.append(
            f"Loan Tenure: Selected tenure ({tenure} months) is below the minimum allowed tenure of 48 months."
        )
    elif tenure > 72:
        failed_reasons.append(
            f"Loan Tenure: Selected tenure ({tenure} months) exceeds the maximum allowed tenure of 72 months."
        )

    # 4. Maximum Loan Amount (15x monthly net salary)
    if loan_amount > limit:
        failed_reasons.append(
            f"Maximum Loan Eligibility: Requested loan of ₹{int(loan_amount):,} exceeds the maximum eligible limit of ₹{int(limit):,} "
            f"(15x monthly net salary of ₹{int(salary):,})."
        )

    # 5. FOIR Affordability Check (Total monthly EMI <= 50% salary)
    # Using rounded precision to prevent float rounding false flags (e.g. 50.0000000001%)
    if round(foir, 2) > 50.00 or total_monthly_emi > (salary * 0.50 + 0.01):
        failed_reasons.append(
            f"FOIR Limit Exceeded: Total monthly debt obligations (FOIR) of {foir:.1f}% "
            f"(₹{int(total_monthly_emi):,}/month: ₹{int(existing_emi):,} existing EMIs + ₹{int(emi):,} proposed EMI) "
            f"exceeds the maximum allowed 50% of monthly net salary (limit: ₹{int(salary * 0.5):,})."
        )

    # ── Check for Multi-Failure or Approval ──
    if failed_reasons:
        bullet_text = "\n• " + "\n• ".join(failed_reasons)
        return {
            "status": "Rejection",
            "failed_conditions": failed_reasons,
            "foir": foir,
            "emi": emi,
            "total_monthly_emi": total_monthly_emi,
            "tenure_months": tenure,
            "message": f"Dear {name}, your loan application cannot be approved due to the following criteria failure(s):{bullet_text}"
        }

    # All criteria satisfied -> Approved
    return {
        "status": "Approved",
        "message": (
            f"Congratulations {name}! Your loan of ₹{int(loan_amount):,} has received Final Approved status. "
            f"EMI: ₹{int(emi):,}/month for {tenure} months at 12% p.a. (FOIR: {foir:.1f}%)."
        ),
        "emi": emi,
        "tenure_months": tenure,
        "foir": foir,
        "total_monthly_emi": total_monthly_emi,
        "pre_approved_limit": limit
    }

# ── PDF Generation ──

SANCTIONS_DIR = "sanctions"
os.makedirs(SANCTIONS_DIR, exist_ok=True)

def generate_sanction_letter_pdf(customer_input, loan_amount, tenure):
    """
    Generate a styled sanction letter PDF using xhtml2pdf.
    Falls back to reportlab if xhtml2pdf is unavailable.
    """
    if isinstance(customer_input, dict):
        customer_name = customer_input.get("name", "Customer")
        customer_city = customer_input.get("city", "")
        customer_id = customer_input.get("customer_id", "")
    else:
        customer_name = str(customer_input)
        customer_city = ""
        customer_id = ""

    app_no = f"APP-{int(time.time())}"
    sanctioned_on = datetime.now(timezone.utc).strftime("%d-%b-%Y")
    interest_rate = 12
    emi = calculate_emi(loan_amount, interest_rate, tenure)

    # Sanitize name for filename
    safe_name = re.sub(r"[^\w\d]+", "_", customer_name).strip("_")
    filename = f"Sanction_Letter_{safe_name}_{app_no}.pdf"
    path = os.path.join(SANCTIONS_DIR, filename)

    if pisa:
        # Render HTML template to string, then convert to PDF
        with app.app_context():
            html = render_template(
                "letter.html",
                date=sanctioned_on,
                customer_name=customer_name,
                customer_city=customer_city,
                application_no=app_no,
                loan_amount=f"{int(loan_amount):,}",
                tenure=tenure,
                emi=f"{int(emi):,}" if emi else "N/A"
            )
        # FIX: pisa.CreatePDF expects (src=string_or_filelike, dest=filelike)
        with open(path, "wb") as pdf_file:
            result = pisa.CreatePDF(src=html, dest=pdf_file)
        if result.err:
            print(f"[WARNING] xhtml2pdf reported errors: {result.err}. PDF may be incomplete.")
    else:
        # Fallback: use reportlab directly
        path = _generate_simple_pdf(customer_name, customer_id, loan_amount, tenure, emi, app_no, sanctioned_on, path)

    return path

def _generate_simple_pdf(customer_name, customer_id, loan_amount, tenure, emi, app_no, date, path):
    """ReportLab fallback PDF if xhtml2pdf is not available."""
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, 750, "Tata Capital – Loan Sanction Letter")
    c.setFont("Helvetica", 12)
    c.drawString(50, 720, f"Date: {date}")
    c.drawString(50, 700, f"Application No: {app_no}")
    c.drawString(50, 680, f"Customer: {customer_name}")
    c.drawString(50, 660, f"Customer ID: {customer_id}")
    c.drawString(50, 640, f"Loan Amount: Rs.{int(loan_amount):,}")
    if emi:
        c.drawString(50, 620, f"EMI: Rs.{int(emi):,}/month for {tenure} months at 12% p.a.")
    c.drawString(50, 600, "This is a system-generated sanction letter.")
    c.showPage()
    c.save()
    return path

# ── Email Sending ──

def send_email_with_attachment(to_email, subject, body, pdf_path):
    """
    Send sanction letter PDF via Gmail SMTP.
    Returns (True, None) on success, (False, error_message) on failure.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        msg = "Email not sent: Gmail credentials not configured in config.json."
        print(f"[WARNING] {msg}")
        return False, msg

    if not to_email:
        msg = "Email not sent: customer email address is missing."
        print(f"[WARNING] {msg}")
        return False, msg

    try:
        email_msg = EmailMessage()
        email_msg["Subject"] = subject
        email_msg["From"] = GMAIL_FROM or GMAIL_USER
        email_msg["To"] = to_email
        email_msg.set_content(body)

        with open(pdf_path, "rb") as f:
            email_msg.add_attachment(
                f.read(), maintype="application", subtype="pdf",
                filename=os.path.basename(pdf_path)
            )

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.send_message(email_msg)

        print(f"[INFO] Email sent to {to_email}")
        return True, None

    except smtplib.SMTPAuthenticationError:
        msg = "Email failed: Gmail authentication error. Check gmail_user and gmail_app_password in config.json."
        print(f"[ERROR] {msg}")
        return False, msg
    except smtplib.SMTPException as e:
        msg = f"Email failed: SMTP error – {e}"
        print(f"[ERROR] {msg}")
        return False, msg
    except Exception as e:
        msg = f"Email failed: {e}"
        print(f"[ERROR] {msg}")
        return False, msg

# ── Local Fallback Agent & Conversational State Machine ──

def local_master_agent(session_id, text):
    """
    Intelligent conversational supervisor:
    - In-chat step-by-step onboarding for new customers (persists to customers.json & Firebase)
    - Full loan application guidance ("I want to apply for a loan")
    - Real-time loan limit & profile inspection
    - Reducing-balance EMI calculators & repayment schedules
    - Document requirements & eligibility rules guidance
    - Automatic routing to VERIFY_KYC and UNDERWRITE pipelines
    """
    t = text.lower().strip()
    sess = session_data.setdefault(session_id, {})
    onboarding_state = sess.get("onboarding_state")

    # ── 1. ACTIVE IN-CHAT ONBOARDING STATE MACHINE ──
    if onboarding_state:
        # Check if user wants to cancel
        if any(w in t for w in ["cancel", "stop", "abort", "exit", "quit", "start over"]):
            sess["onboarding_state"] = None
            sess["onboarding_data"] = {}
            return (
                "❌ **Registration Cancelled.**\n\n"
                "No problem! Whenever you're ready, you can type **'I am a new customer'** to start again, "
                "or provide an existing Customer ID (e.g. `cust01`)."
            )

        data = sess.setdefault("onboarding_data", {})

        if onboarding_state == "ASK_NAME":
            name = text.strip()
            if len(name) < 2 or re.match(r"^\d+$", name):
                return "Please provide your **Full Legal Name** (e.g., *Rahul Sharma* or *Priya Patel*)."
            data["name"] = name.title()
            sess["onboarding_state"] = "ASK_PHONE"
            return (
                f"Nice to meet you, **{data['name']}**! 👋\n\n"
                "What is your **10-digit Mobile Number**?\n"
                "*(This will serve as your unique Customer ID, e.g. 9876543210)*"
            )

        if onboarding_state == "ASK_PHONE":
            phone = re.sub(r"\D", "", text)
            if len(phone) != 10:
                return "Please enter a valid **10-digit mobile number** (e.g., *9876543210*)."

            # Check if this customer ID already exists in our records
            existing = verify_kyc(f"cust{phone}")
            if existing.get("status") == "Verification Successful":
                sess["onboarding_state"] = None
                sess["onboarding_data"] = {}
                session_data[session_id] = existing.copy()
                limit = existing.get("pre_approved_limit") or existing.get("salary", 0) * 15
                return (
                    f"🎉 **Account Already Found!**\n\n"
                    f"Welcome back, **{existing.get('name')}**! We found your existing profile with mobile **{phone}** (`cust{phone}`).\n\n"
                    f"• **Preliminary Loan Eligibility**: Up to **₹{int(limit):,}**\n"
                    f"• **Application Status**: `Preliminary Eligible`\n"
                    f"• **CIBIL Score**: {existing.get('credit_score')}\n\n"
                    f"ℹ️ *This is an initial eligibility estimate based on your monthly net salary (15x salary). Final loan approval is subject to CIBIL verification, age eligibility, FOIR calculation, document verification and the lender's final assessment.*\n\n"
                    f"How much loan amount would you like to apply for? (e.g. **500000**)"
                )

            data["phone"] = phone
            sess["onboarding_state"] = "ASK_EMAIL"
            return (
                "Got it! What is your **Email Address**?\n"
                "*(We will email your official loan sanction letter and agreement here)*"
            )

        if onboarding_state == "ASK_EMAIL":
            em_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
            if not em_match:
                return "Please enter a valid **email address** (e.g., *rahul@gmail.com*)."
            data["email"] = em_match.group(0).lower()
            sess["onboarding_state"] = "ASK_AGE_CITY"
            return (
                "Thanks! What is your **Age** and **City** of residence?\n"
                "*(e.g., '28, Mumbai' or '30, Delhi')*"
            )

        if onboarding_state == "ASK_AGE_CITY":
            dob_age = calculate_age_from_dob(text)
            if dob_age is not None:
                age = dob_age
            else:
                age_m = re.search(r"\b(1[89]|[2-9][0-9])\b", text)
                age = int(age_m.group(0)) if age_m else 0

            # Validate Age bounds (21 to 65 years)
            if age < 21:
                return (
                    f"❌ **Eligibility Check Failed (Age)**: Minimum eligible age is **21 years** (maximum 65 years). "
                    f"At {age} years, you do not meet our mandatory age requirement.\n\n"
                    f"*Please enter an eligible age between 21 and 65 to continue, or type 'cancel' to exit.*"
                )
            if age > 65:
                return (
                    f"❌ **Eligibility Check Failed (Age)**: Maximum eligible age is **65 years**. "
                    f"At {age} years, you exceed our maximum age limit.\n\n"
                    f"*Please enter an eligible age between 21 and 65 to continue, or type 'cancel' to exit.*"
                )

            city_cand = re.sub(r"[\d,.-]", " ", text).strip()
            city = " ".join([w.capitalize() for w in city_cand.split() if len(w) > 1]) or "Mumbai"
            data["age"] = age
            data["city"] = city
            sess["onboarding_state"] = "ASK_PAN"
            return (
                f"Great ({age} yrs, {city}). Now, please enter your **PAN Card Number**\n"
                f"*(10-character alphanumeric, e.g. `ABCDE1234F`)*:"
            )

        if onboarding_state == "ASK_PAN":
            pan_clean = re.sub(r"[^A-Za-z0-9]", "", text).upper()
            if len(pan_clean) < 8:
                return "Please enter a valid **PAN Number** (e.g., *ABCDE1234F*)."
            data["pannumber"] = pan_clean
            sess["onboarding_state"] = "ASK_SALARY"
            return (
                "Almost done! What is your **Monthly In-Hand Salary** in ₹?\n"
                "*(e.g., 50000 or 80000 — this determines your pre-approved loan limit)*"
            )

        if onboarding_state == "ASK_SALARY":
            amt = parse_loan_amount_text(text)
            if not amt or amt < 5000:
                return "Please enter a valid monthly salary figure in numbers (e.g. *50000* or *75000*)."
            data["salary"] = int(amt)
            sess["onboarding_state"] = "ASK_EXISTING_LOAN"
            return (
                "Do you have any **Current Ongoing Monthly Loan EMIs**?\n"
                "*(Enter the monthly EMI amount e.g. 5000, or reply '0' / 'none' if no active loans)*"
            )

        if onboarding_state == "ASK_EXISTING_LOAN":
            if any(w in t for w in ["no", "none", "na", "nil", "zero", "0"]):
                curr_loan = 0
            else:
                amt = parse_loan_amount_text(text)
                curr_loan = int(amt) if amt else 0

            salary = data.get("salary", 0)
            if salary > 0 and (curr_loan / salary) > 0.50:
                foir_pct = (curr_loan / salary) * 100
                return (
                    f"❌ **Eligibility Check Failed (FOIR Limit)**: Existing monthly EMIs of ₹{int(curr_loan):,} account for "
                    f"{foir_pct:.1f}% of your monthly salary (₹{int(salary):,}), which exceeds the mandatory 50% FOIR limit.\n\n"
                    f"*Please enter a valid monthly EMI obligation (under ₹{int(salary * 0.5):,}, or '0' if none), or type 'cancel' to exit.*"
                )

            data["current_loan"] = curr_loan
            sess["onboarding_state"] = "ASK_CREDIT_SCORE"
            return (
                "Lastly, what is your approximate **Credit Score / CIBIL**?\n"
                "*(e.g., 750 or 800. Must be 700 or above for loan approval)*"
            )

        if onboarding_state == "ASK_CREDIT_SCORE":
            if any(w in t for w in ["skip", "dont know", "not sure", "na", "none", "default"]):
                credit = 750
            else:
                amt = parse_loan_amount_text(text)
                if amt:
                    credit = int(amt)
                else:
                    credit = 750

            if credit < 700:
                return (
                    f"❌ **Eligibility Check Failed (CIBIL Score)**: Minimum required CIBIL credit score is **700**. "
                    f"A credit score of {credit} does not meet our mandatory approval threshold.\n\n"
                    f"*Please provide a credit score of 700 or above (or type 'cancel' to exit).* "
                )

            data["credit_score"] = credit

            # ── FINALIZE REGISTRATION ──
            cust_id = f"cust{data['phone']}"
            salary = data["salary"]
            limit = salary * 15
            new_customer = {
                "customer_id": cust_id,
                "name": data["name"],
                "phone": data["phone"],
                "email": data["email"],
                "age": data["age"],
                "city": data["city"],
                "pannumber": data["pannumber"],
                "salary": salary,
                "credit_score": credit,
                "pre_approved_limit": limit,
                "current_loan_status": str(data["current_loan"])
            }
            save_customer_to_storage(new_customer)
            new_customer["status"] = "Verification Successful"

            # Immediately link to active session
            session_data[session_id] = new_customer.copy()
            sess["onboarding_state"] = None
            sess["onboarding_data"] = {}
            save_session_meta(session_id, {"customer_name": new_customer["name"], "email": new_customer["email"]})

            prompt_amt = f"₹{int(limit * 0.5):,}" if limit else "₹5,00,000"

            return (
                f"🎉 **Registration Completed Successfully!**\n\n"
                f"Welcome to AI Loan Approval System, **{new_customer['name']}**! Your customer profile has been registered.\n\n"
                f"📋 **Profile Assessment Summary:**\n"
                f"• **Customer ID**: `{cust_id}` *(keep this for future logins)*\n"
                f"• **Preliminary Loan Eligibility**: Up to **₹{limit:,}**\n"
                f"• **Application Status**: `Preliminary Eligible`\n"
                f"• **CIBIL Score Reported**: **{credit}**\n"
                f"• **Standard Interest Rate**: **12% p.a.**\n"
                f"• **Registered Email**: `{new_customer['email']}`\n\n"
                f"ℹ️ *This is an initial eligibility estimate based on your monthly net salary (15x salary). Final loan approval is subject to CIBIL verification, age eligibility, FOIR calculation, document verification and the lender's final assessment.*\n\n"
                f"🚀 **Next Step:**\n"
                f"How much loan amount would you like to apply for? (e.g. enter **{prompt_amt}** or up to **₹{limit:,}** to submit for underwriting review)."
            )

    # ── 2. NEW CUSTOMER REGISTRATION TRIGGER ──
    if any(phrase in t for phrase in [
        "new customer", "new user", "register", "sign up", "signup", "create account",
        "add customer", "add me", "register me", "i am new", "i am a new customer",
        "i don't have customer id", "i dont have customer id", "i don't have an id",
        "i dont have an id", "no customer id", "no id", "dont have id", "don't have id",
        "onboard me", "start onboarding"
    ]):
        if sess.get("customer_id"):
            name = sess.get("name", "Customer")
            cid = sess.get("customer_id")
            limit = sess.get("pre_approved_limit", 0)
            return (
                f"You are currently verified as **{name}** (`{cid}`).\n"
                f"• Pre-approved limit: **₹{int(limit):,}**\n\n"
                f"If you want to register a different customer, type **'logout'** or **'switch customer'** first."
            )
        sess["onboarding_state"] = "ASK_NAME"
        sess["onboarding_data"] = {}
        return (
            "👋 **Welcome New Customer!**\n\n"
            "I will help you register and get pre-approved for an instant loan in under 2 minutes right here.\n\n"
            "To get started, what is your **Full Name**?"
        )

    # ── 3. CUSTOMER ID VERIFICATION TRIGGER (custXXXX) ──
    m = re.search(r"\bcust\w+", t)
    if m:
        return "[[FLASK_CALL:VERIFY_KYC]]"

    # ── 4. LOGOUT / SWITCH CUSTOMER ──
    if any(phrase in t for phrase in ["logout", "log out", "switch customer", "change customer", "change user", "sign out", "reset customer"]):
        session_data[session_id] = {}
        return (
            "✅ **Logged out successfully.**\n\n"
            "You can now:\n"
            "1. Enter an existing Customer ID (e.g. `cust01`, `cust10`)\n"
            "2. Type **'I am a new customer'** to register a new profile."
        )

    # ── 5. CHECK PROFILE / LIMIT / WHO AM I ──
    if any(phrase in t for phrase in [
        "check limit", "my limit", "what is my limit", "eligible limit", "check my limit",
        "my profile", "who am i", "my details", "profile details", "account details",
        "check my profile", "eligibility status"
    ]):
        if sess.get("customer_id"):
            name = sess.get("name", "Customer")
            cid = sess.get("customer_id")
            salary = sess.get("salary", 0)
            credit = sess.get("credit_score", 0)
            limit = sess.get("pre_approved_limit") or salary * 15
            email = sess.get("email", "Not provided")
            tenure = determine_tenure_months(salary)
            return (
                f"👤 **Your Account Profile Details:**\n\n"
                f"• **Name**: **{name}**\n"
                f"• **Customer ID**: `{cid}`\n"
                f"• **Monthly Salary**: ₹{int(salary):,}\n"
                f"• **Credit Score**: {credit}\n"
                f"• **Preliminary Loan Eligibility**: Up to **₹{int(limit):,}**\n"
                f"• **Application Status**: `Preliminary Eligible`\n"
                f"• **Estimated Tenure**: {tenure} months @ 12% p.a.\n"
                f"• **Registered Email**: `{email}`\n\n"
                f"ℹ️ *This is an initial eligibility estimate based on your monthly net salary (15x salary). Final loan approval is subject to CIBIL verification, age eligibility, FOIR calculation, document verification and the lender's final assessment.*\n\n"
                f"Ready to apply? Simply enter the loan amount you wish to apply for (e.g. **₹{int(limit * 0.5):,}**)."
            )
        return (
            "You haven't verified a customer profile in this session yet.\n\n"
            "• If you have an ID, enter it (e.g. `cust01` or your phone number).\n"
            "• If you are new, type **'I am a new customer'** to register and check your limit!"
        )

    # ── 6. "I WANT TO APPLY FOR A LOAN" (LOAN APPLICATION INTENT) ──
    if any(phrase in t for phrase in [
        "apply for a loan", "apply for loan", "apply loan", "want a loan", "want loan",
        "need a loan", "need loan", "take a loan", "take loan", "get a loan", "get loan",
        "i want to apply", "loan application", "how to apply"
    ]):
        detected_amt = parse_loan_amount_text(text)

        if sess.get("customer_id"):
            name = sess.get("name", "Customer")
            limit = sess.get("pre_approved_limit") or sess.get("salary", 0) * 15
            if detected_amt:
                return "[[FLASK_CALL:UNDERWRITE]]"
            return (
                f"Hi **{name}**! 👋 Your profile is registered with preliminary eligibility.\n\n"
                f"💰 **Preliminary Loan Eligibility**: Up to **₹{int(limit):,}**\n"
                f"📋 **Application Status**: `Preliminary Eligible`\n"
                f"📈 **Indicative Interest Rate**: 12% p.a.\n\n"
                f"ℹ️ *This is an initial eligibility estimate based on your monthly net salary (15x salary). Final loan approval is subject to CIBIL verification, age eligibility, FOIR calculation, document verification and the lender's final assessment.*\n\n"
                f"Please enter the loan amount you wish to apply for (e.g. **500000** or **₹3,00,000**) to initiate underwriting review."
            )
        else:
            if detected_amt:
                sess["pending_loan_amount"] = detected_amt
            return (
                "I would love to help you apply for an instant personal loan! 🏦\n\n"
                "To determine your eligibility and prepare your sanction letter, I just need to verify your customer profile:\n\n"
                "1️⃣ **Existing Customer?**\n"
                "   Type your Customer ID (e.g. `cust01`, `cust10`, or `cust` + your 10-digit phone number).\n\n"
                "2️⃣ **New Customer?**\n"
                "   Simply type **'I am a new customer'**, and I will register you directly here in this chat in under 2 minutes!\n\n"
                "Which option would you like?"
            )

    # ── 7. EMI CALCULATION PREVIEW ──
    if any(phrase in t for phrase in ["calculate emi", "emi for", "what is emi", "what is the emi", "emi calculation", "monthly emi"]):
        amt = parse_loan_amount_text(text)
        if amt and amt > 1000:
            emi_36 = calculate_emi(amt, 12, 36)
            emi_48 = calculate_emi(amt, 12, 48)
            emi_60 = calculate_emi(amt, 12, 60)
            int_36 = (emi_36 * 36) - amt if emi_36 else 0
            int_48 = (emi_48 * 48) - amt if emi_48 else 0
            int_60 = (emi_60 * 60) - amt if emi_60 else 0
            return (
                f"📊 **EMI Repayment Schedule for ₹{int(amt):,} @ 12% p.a.:**\n\n"
                f"• **36 Months (3 Years)**: **₹{int(emi_36):,}/month** *(Total Interest: ₹{int(int_36):,})*\n"
                f"• **48 Months (4 Years)**: **₹{int(emi_48):,}/month** *(Total Interest: ₹{int(int_48):,})*\n"
                f"• **60 Months (5 Years)**: **₹{int(emi_60):,}/month** *(Total Interest: ₹{int(int_60):,})*\n\n"
                f"💡 *Formula used: Standard reducing-balance banking amortization.* \n"
                f"To apply for this loan, enter your Customer ID (e.g. `cust01`) or type **'I am a new customer'**!"
            )
        return (
            "To calculate your monthly EMI, please mention the loan amount.\n"
            "*(e.g., 'Calculate EMI for ₹5,00,000' or 'EMI for 3 lakhs')*"
        )

    # ── 8. DOCUMENTS & ELIGIBILITY INQUIRIES ──
    if any(phrase in t for phrase in ["document", "documents", "docs", "paperwork"]):
        return (
            "📄 **Documents Required for Loan Approval:**\n\n"
            "1. **Identity Proof**: PAN Card (mandatory) & Aadhaar Card / Passport.\n"
            "2. **Address Proof**: Aadhaar Card, Utility Bill, or Rental Agreement.\n"
            "3. **Income Proof**: Last 3 months Salary Slips & Form 16 / ITR.\n"
            "4. **Bank Statement**: Last 6 months bank statement showing regular salary deposits.\n\n"
            "✨ *With our instant automated pipeline, verified customers receive a digital sanction letter within seconds without physical paperwork!*"
        )

    if any(phrase in t for phrase in ["eligibility", "criteria", "rules", "qualify", "requirements"]):
        return (
            "📋 **Loan Eligibility Criteria & Guidelines:**\n\n"
            "• **Age**: 21 to 65 years.\n"
            "• **Credit Score**: Minimum 700 (CIBIL) required for approval.\n"
            "• **Maximum Loan Limit**: Up to **15x your monthly net salary**.\n"
            "• **Affordability Rule (FOIR)**: Monthly EMI must not exceed 50% of your net monthly salary.\n"
            "• **Interest Rate**: Fixed 12% per annum.\n"
            "• **Tenure**: 48 to 72 months based on salary band."
        )

    # ── 9. SANCTION LETTER / DISPATCH STATUS ──
    if sess.get("sanction"):
        if any(word in t for word in ["sanction", "letter", "email", "pdf", "status"]):
            s = sess["sanction"]
            return f"✅ Your loan sanction letter (`{s.get('pdf', 'Sanction_Letter.pdf')}`) has been issued and sent to **{s.get('email', 'your email')}**."

    # ── 10. UNDERWRITE TRIGGER (NUMERIC LOAN AMOUNT) ──
    if sess.get("customer_id"):
        amt = parse_loan_amount_text(text)
        if amt and amt > 0:
            return "[[FLASK_CALL:UNDERWRITE]]"

        limit = sess.get("pre_approved_limit") or sess.get("salary", 0) * 15
        return (
            f"Please enter the loan amount you wish to apply for (e.g. **500000** or **5 lakhs**).\n"
            f"Your maximum eligible pre-approved limit is **₹{int(limit):,}**."
        )

    # ── 11. GENERAL GREETINGS / HELP FALLBACK ──
    if any(phrase in t for phrase in ["hi", "hello", "hey", "help", "good morning", "good evening", "namaste", "options", "menu"]):
        return (
            "Hello! 👋 I'm your **AI Loan Approval Assistant**.\n\n"
            "Here is how I can assist you today:\n"
            "1️⃣ **Apply for a Loan**: Check your pre-approved limit and apply instantly.\n"
            "2️⃣ **New Customer Registration**: Type **'I am a new customer'** to register directly in chat.\n"
            "3️⃣ **Verify Existing Customer**: Enter your Customer ID (e.g. `cust01`, `cust10`).\n"
            "4️⃣ **Calculate EMI**: Type *'Calculate EMI for ₹5,00,000'* for a detailed payment plan.\n"
            "5️⃣ **Eligibility & Docs**: Ask for eligibility criteria or documents required.\n\n"
            "How can I help you today?"
        )

    # Default welcoming prompt
    return (
        "Welcome! I'm your **AI Loan Assistant**.\n\n"
        "• Existing customer? Please provide your **Customer ID** (format: `custXXXX`, e.g. `cust01`).\n"
        "• New customer? Type **'I am a new customer'** and you can register right here in this chat!"
    )

# ── Flask Routes ──

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    user_input = data.get("user_input", "").strip()

    if not user_input:
        return jsonify({"response_text": "Please type a message.", "orchestration_command": None})

    if not session_id:
        session_id = f"sess_{int(time.time())}"

    save_message_to_firebase(session_id, "user", user_input)

    hist = get_session_history(session_id)
    hist.append(HumanMessage(content=user_input))

    # Route through local agent if onboarding is active, triggered, or LLM is not configured
    t_lower = user_input.lower().strip()
    is_onboarding_active = bool(session_data.get(session_id, {}).get("onboarding_state"))
    is_onboarding_trigger = any(p in t_lower for p in [
        "new customer", "new user", "register", "sign up", "signup", "create account",
        "add customer", "add me", "register me", "i am new", "i am a new customer",
        "i don't have customer id", "i dont have customer id", "i don't have an id",
        "i dont have an id", "no customer id", "no id", "dont have id", "don't have id",
        "apply for a loan", "apply loan", "apply for loan", "want a loan", "need a loan"
    ])
    is_logout = any(p in t_lower for p in ["logout", "log out", "switch customer", "change customer", "change user", "sign out"])

    is_structured_query = any(p in t_lower for p in [
        "check my limit", "check limit", "what is my limit", "who am i", "my profile",
        "calculate emi", "emi for", "documents", "document", "criteria", "eligibility"
    ])
    is_cust_id = bool(re.search(r"\bcust\w+", t_lower))
    is_verified_and_amount = bool(session_data.get(session_id, {}).get("customer_id") and parse_loan_amount_text(user_input))

    if is_onboarding_active or is_onboarding_trigger or is_logout or is_structured_query or is_cust_id or is_verified_and_amount or not llm:
        text = local_master_agent(session_id, user_input)
    else:
        try:
            res = llm.invoke(hist)
            text = getattr(res, "content", "")
            if isinstance(text, (list, dict)):
                text = str(text)
        except Exception as e:
            err_msg = str(e)
            print(f"[WARNING] Primary LLM ({MODEL_NAME}) error: {err_msg}.")
            # If quota exceeded or error occurred, attempt fallback to flash-lite if different
            fallback_res = None
            if MODEL_NAME != "gemini-3.5-flash-lite" and ChatGoogleGenerativeAI and API_KEY:
                try:
                    fallback_llm = ChatGoogleGenerativeAI(
                        model="gemini-3.5-flash-lite",
                        google_api_key=API_KEY,
                        temperature=MODEL_TEMP,
                        safety_settings=None,
                        timeout=10
                    )
                    res2 = fallback_llm.invoke(hist)
                    fallback_res = getattr(res2, "content", "")
                    if isinstance(fallback_res, (list, dict)):
                        fallback_res = str(fallback_res)
                    print("[INFO] Fallback to gemini-3.5-flash-lite succeeded.")
                except Exception as e2:
                    print(f"[WARNING] Fallback LLM error: {e2}.")
            if fallback_res:
                text = fallback_res
            else:
                print("[INFO] Falling back to local deterministic supervisor.")
                text = local_master_agent(session_id, user_input)

    hist.append(AIMessage(content=text))
    save_message_to_firebase(session_id, "bot", text)

    # Check if the response contains an orchestration command
    m = re.search(r"\[\[FLASK_CALL:([A-Z_]+)\]\]", text)
    cmd = f"[[FLASK_CALL:{m.group(1)}]]" if m else None

    if cmd:
        return jsonify({"response_text": "Processing request...", "orchestration_command": cmd})

    return jsonify({"response_text": text, "orchestration_command": None})


@app.route("/orchestrate", methods=["POST"])
def orchestrate():
    data = request.get_json(silent=True) or {}
    step = data.get("step")
    session_id = data.get("session_id")
    info = data.get("customer_info", {})

    if not step or not session_id:
        return jsonify({"status": "error", "message": "Missing step or session_id"}), 400

    if step == "VERIFY_KYC":
        cid = (info.get("customer_id") or "").strip().lower()
        if not cid:
            return jsonify({"status": "error", "message": "Customer ID is required", "next_step": "AWAITING_KYC"})

        c = verify_kyc(cid)
        if c.get("status") == "Verification Successful":
            session_data[session_id] = c.copy()
            save_session_meta(session_id, {"customer_name": c["name"], "email": c.get("email")})
            return jsonify({"status": "success", "customer_data": c, "next_step": "ASK_LOAN_AMOUNT"})
        return jsonify({"status": "error", "message": c.get("message", "Verification failed"), "next_step": "AWAITING_KYC"})

    if step == "UNDERWRITE":
        c = session_data.get(session_id)
        if not c or not c.get("customer_id"):
            return jsonify({"status": "error", "message": "No verified customer found. Please verify KYC first."})

        amt_raw = info.get("loan_amount")
        if not amt_raw:
            return jsonify({"status": "error", "message": "Loan amount is required."})

        tenure_raw = info.get("tenure") or info.get("tenure_months")
        parsed_tenure = None
        if tenure_raw:
            try:
                parsed_tenure = int(tenure_raw)
            except Exception:
                pass
        if not parsed_tenure:
            parsed_tenure = parse_tenure_months(amt_raw)

        result = underwrite(c, amt_raw, tenure=parsed_tenure)

        if result["status"] in ("Pre-Approved", "Approval", "Approved"):
            tenure = result.get("tenure_months")
            try:
                clean_amt = parse_loan_amount_text(amt_raw) or float(re.sub(r"[^\d.]", "", str(amt_raw)))
                fpdf_path = generate_sanction_letter_pdf(c, clean_amt, int(tenure))
            except Exception as e:
                print(f"[ERROR] PDF generation failed: {e}")
                fpdf_path = None

            email = c.get("email", "")
            email_ok, email_err = False, "PDF generation failed; email skipped."

            if fpdf_path:
                email_ok, email_err = send_email_with_attachment(
                    email,
                    "Your Loan Sanction Letter – Tata Capital",
                    "Dear Customer,\n\nPlease find your loan sanction letter attached.\n\nTata Capital Finance Ltd.",
                    fpdf_path
                )
                session_data[session_id]["sanction"] = {
                    "pdf": os.path.basename(fpdf_path) if fpdf_path else None,
                    "email": email
                }
                save_session_meta(session_id, {"sanction_pdf_path": fpdf_path})

            if email_ok:
                email_message = f"✅ Sanction letter sent to {email}"
            else:
                email_message = f"⚠️ PDF generated but email could not be sent ({email_err}). PDF saved locally."

            return jsonify({
                "status": "complete",
                "worker_message": result["message"],
                "email_message": email_message,
                "emi": result.get("emi"),
                "tenure_months": result.get("tenure_months"),
                "pdf_file": os.path.basename(fpdf_path) if fpdf_path else None
            })

        # Rejection
        return jsonify({
            "status": "complete",
            "decision": "Rejection",
            "worker_message": result["message"],
            "failed_conditions": result.get("failed_conditions", []),
            "foir": result.get("foir")
        })

    return jsonify({"status": "error", "message": f"Unknown step: {step}"}), 400


@app.route("/new_chat")
def new_chat():
    session_id = f"sess_{int(time.time())}"
    session_histories[session_id] = [SystemMessage(content=LLM_SYSTEM_PROMPT)]
    session_data[session_id] = {}
    return jsonify({"session_id": session_id})


@app.route("/")
def index():
    return render_template("chat.html")


@app.route("/health")
def health():
    """Health check endpoint – useful for debugging."""
    return jsonify({
        "status": "ok",
        "llm_ready": llm is not None,
        "firebase_configured": bool(FIREBASE_DB_URL),
        "email_configured": bool(GMAIL_USER and GMAIL_APP_PASSWORD),
        "dummy_customers": list(DUMMY_CUSTOMERS.keys())
    })


if __name__ == "__main__":
    app.run(port=5000, debug=True)
