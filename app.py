import os
import re
import json
import time
import hashlib
import tempfile
import smtplib
import requests
import io
import warnings
from datetime import datetime, timedelta, timezone, date
from email.message import EmailMessage

# Suppress cosmetic dependency mismatch warning for clean terminal logs
warnings.filterwarnings("ignore", message=r".*urllib3.*or chardet.*doesn't match a supported version!.*")

from flask import Flask, request, jsonify, render_template, session, send_from_directory, has_request_context
from flask_cors import CORS
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from monitoring import (
    AIMonitoringStore,
    classify_intent_category,
    extract_gemini_token_usage,
    sanitize_error_reason,
)

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
FIREBASE_DB_URL = (os.environ.get("FIREBASE_DATABASE_URL") or config.get("firebase_database_url", "")).strip().rstrip("/")
FIREBASE_API_KEY = (os.environ.get("FIREBASE_API_KEY") or config.get("firebase_api_key", "")).strip()
API_KEY = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or config.get("gemini_api_key", "")).strip()
MODEL_NAME = (os.environ.get("LLM_MODEL") or config.get("llm_model", "gemini-3.5-flash-lite")).strip()
MODEL_TEMP = float(os.environ.get("LLM_TEMPERATURE") or config.get("llm_temperature", 0.7))

GMAIL_USER = (os.environ.get("GMAIL_USER") or config.get("gmail_user", "")).strip()
GMAIL_APP_PASSWORD = (os.environ.get("GMAIL_APP_PASSWORD") or config.get("gmail_app_password", "")).replace(" ", "").strip()
GMAIL_FROM = (os.environ.get("GMAIL_FROM") or config.get("gmail_from", "")).strip() or GMAIL_USER

if API_KEY:
    os.environ["GOOGLE_API_KEY"] = API_KEY
    os.environ["GENAI_API_KEY"] = API_KEY
    os.environ["GOOGLE_GENAI_API_KEY"] = API_KEY
    os.environ["GOOGLE_API_USE_CLIENT_CERTIFICATE"] = "false"

IS_SERVERLESS = bool(
    os.environ.get("VERCEL")
    or os.environ.get("VERCEL_ENV")
    or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
)


def _use_temp_storage():
    if IS_SERVERLESS:
        return True
    try:
        return not os.access(".", os.W_OK)
    except Exception:
        return True


USE_TEMP_STORAGE = _use_temp_storage()
WRITABLE_DATA_DIR = tempfile.gettempdir() if USE_TEMP_STORAGE else "."
BUNDLED_CUSTOMERS_FILE = "customers.json"
RUNTIME_CUSTOMERS_FILE = (
    BUNDLED_CUSTOMERS_FILE
    if WRITABLE_DATA_DIR == "."
    else os.path.join(WRITABLE_DATA_DIR, "customers.json")
)
SANCTIONS_DIR = (
    "sanctions"
    if WRITABLE_DATA_DIR == "."
    else os.path.join(WRITABLE_DATA_DIR, "sanctions")
)
os.makedirs(SANCTIONS_DIR, exist_ok=True)
DEFAULT_MONITORING_STATS_PATH = (
    "monitoring_stats.json"
    if WRITABLE_DATA_DIR == "."
    else os.path.join(WRITABLE_DATA_DIR, "monitoring_stats.json")
)

app = Flask(__name__, static_folder="static", static_url_path="/static", template_folder="templates")
CORS(app)
_secret_seed = os.environ.get("FLASK_SECRET_KEY") or API_KEY or "loanai-local-dev-session-secret"
app.secret_key = hashlib.sha256(_secret_seed.encode("utf-8")).hexdigest()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

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

# ── LLM Initialization & Resolved Model Tracking ──
SECONDARY_MODEL_NAME = "gemini-3.5-flash-lite"
ACTIVE_MODEL_NAME = MODEL_NAME if MODEL_NAME != "gemini-2.5-flash" else SECONDARY_MODEL_NAME
LLM_INIT_ERROR = None
llm = None
if ChatGoogleGenerativeAI and API_KEY:
    try:
        llm = ChatGoogleGenerativeAI(
            model=ACTIVE_MODEL_NAME,
            google_api_key=API_KEY,
            temperature=MODEL_TEMP,
            safety_settings=None,
            timeout=10
        )
        print(f"[INFO] Google Gemini API loaded with model: {ACTIVE_MODEL_NAME}")
    except Exception as e:
        LLM_INIT_ERROR = str(e)
        print(f"[WARNING] LLM could not be loaded: {e}. Using local fallback agent.")
        llm = None
else:
    print("[INFO] No Gemini API key set. Running in local fallback mode.")

monitoring_store = AIMonitoringStore(
    local_path=os.environ.get("MONITORING_STATS_PATH", DEFAULT_MONITORING_STATS_PATH),
    firebase_db_url=FIREBASE_DB_URL,
    firebase_api_key=FIREBASE_API_KEY,
    configured_model=MODEL_NAME,
    active_model=ACTIVE_MODEL_NAME,
    secondary_model=SECONDARY_MODEL_NAME,
    llm_available=(llm is not None),
    init_error=LLM_INIT_ERROR,
)

LLM_SYSTEM_PROMPT = """
You are the AI Financial Assistant for the AI Loan Approval System.

PROJECT DEMONSTRATION RULES (factual reference only — NEVER approve/reject loans yourself or modify customer records):
- Eligibility criteria used by the deterministic Python underwriting engine:
  1) Age: 21 to 65 years.
  2) CIBIL / Credit Score: minimum 700 (on the standard 300–900 scale) as this project's demonstration eligibility threshold. Clarify when asked that a higher score reflects stronger repayment history and lower perceived credit risk, while 700 is the configured rule in this demo system rather than a universal cutoff for all external lenders.
  3) Maximum Loan Limit: up to 15x monthly net salary.
  4) Affordability (FOIR - Fixed Obligation to Income Ratio): existing monthly EMIs + proposed EMI must not exceed 50% of monthly net salary.
  5) Tenure: 48 to 72 months at a fixed 12% per annum interest rate.
  6) Minimum Loan Amount: backend underwriting validates amount > 0 with no arbitrary fixed floor, though practical loan applications are assessed against the 15x cap and 50% FOIR limit.

STRICT SAFETY RULES:
- Answer general, educational, and policy questions clearly, concisely, and accurately in plain conversational language.
- NEVER emit `[[FLASK_CALL:...]]` tokens, never trigger KYC/underwriting, and never claim a registration or loan approval is complete.
- NEVER fabricate customer details, credit scores, ages, cities, or loan amounts.
- If a user is currently partway through registration (onboarding), answer their question helpfully and remind them to provide the requested pending onboarding detail when ready.
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


def _build_compact_session_snapshot(session_id):
    """Build compact JSON-serializable state snapshot for serverless persistence."""
    sess = session_data.get(session_id)
    if not isinstance(sess, dict) or not session_id:
        return None
    if sess.get("customer_id") and (sess.get("verified") or sess.get("status") == "Verification Successful"):
        snap = {
            "session_id": session_id,
            "customer_id": str(sess["customer_id"]).lower().strip(),
            "verified": True,
        }
        for k in (
            "verified_at",
            "last_requested_amount",
            "last_requested_tenure",
            "last_underwriting_result",
            "sanction",
        ):
            if sess.get(k) is not None:
                snap[k] = sess.get(k)
        return snap
    if sess.get("onboarding_state"):
        return {
            "session_id": session_id,
            "onboarding_state": sess.get("onboarding_state"),
            "onboarding_data": sess.get("onboarding_data") or {},
        }
    return None


def persist_session_state(session_id):
    """Persist verified KYC or active onboarding state to Firebase RTDB + signed Flask cookie."""
    if not session_id:
        return
    snap = _build_compact_session_snapshot(session_id)
    if has_request_context():
        try:
            if snap:
                session["loanai_state"] = snap
                session.modified = True
            else:
                session.pop("loanai_state", None)
        except Exception:
            pass

    if FIREBASE_DB_URL:
        try:
            url = f"{FIREBASE_DB_URL}/sessions/{session_id}/runtime_state.json"
            if FIREBASE_API_KEY:
                url += f"?auth={FIREBASE_API_KEY}"
            if snap:
                requests.put(url, json=snap, timeout=2)
            else:
                requests.delete(url, timeout=2)
        except Exception:
            pass


def clear_persisted_session_state(session_id):
    """Clear session state in memory, signed cookie, and Firebase RTDB."""
    session_data[session_id] = {}
    if has_request_context():
        try:
            session.pop("loanai_state", None)
        except Exception:
            pass
    if FIREBASE_DB_URL and session_id:
        try:
            url = f"{FIREBASE_DB_URL}/sessions/{session_id}/runtime_state.json"
            if FIREBASE_API_KEY:
                url += f"?auth={FIREBASE_API_KEY}"
            requests.delete(url, timeout=2)
        except Exception:
            pass


def restore_session_state(session_id):
    """
    Restore verified customer or onboarding state when running across serverless instances.
    Re-hydrates verified customer profiles authoritatively via verify_kyc() to prevent tampering.
    """
    if not session_id:
        return None
    existing = session_data.get(session_id)
    if isinstance(existing, dict) and (
        existing.get("customer_id") or existing.get("onboarding_state")
    ):
        return existing

    snap = None
    if FIREBASE_DB_URL:
        try:
            url = f"{FIREBASE_DB_URL}/sessions/{session_id}/runtime_state.json"
            if FIREBASE_API_KEY:
                url += f"?auth={FIREBASE_API_KEY}"
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                candidate = resp.json()
                if isinstance(candidate, dict) and candidate.get("session_id") == session_id:
                    snap = candidate
        except Exception:
            snap = None

    if not snap and has_request_context():
        try:
            cookie_state = session.get("loanai_state")
            if isinstance(cookie_state, dict) and cookie_state.get("session_id") == session_id:
                snap = cookie_state
        except Exception:
            snap = None

    if not isinstance(snap, dict):
        return existing

    cid = snap.get("customer_id")
    if cid and snap.get("verified"):
        cust = verify_kyc(cid)
        if cust.get("status") == "Verification Successful":
            cust["verified"] = True
            for k in (
                "verified_at",
                "last_requested_amount",
                "last_requested_tenure",
                "last_underwriting_result",
                "sanction",
            ):
                if snap.get(k) is not None:
                    cust[k] = snap[k]
            cust["profile_assessment"] = evaluate_customer_profile_eligibility(cust)
            session_data[session_id] = cust
            return cust

    if snap.get("onboarding_state"):
        restored = {
            "onboarding_state": snap.get("onboarding_state"),
            "onboarding_data": snap.get("onboarding_data") or {},
        }
        session_data[session_id] = restored
        return restored

    return existing

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

    # 2. Check runtime writable customers.json, then bundled customers.json
    candidate_files = [RUNTIME_CUSTOMERS_FILE]
    if BUNDLED_CUSTOMERS_FILE != RUNTIME_CUSTOMERS_FILE:
        candidate_files.append(BUNDLED_CUSTOMERS_FILE)

    for local_file in candidate_files:
        if os.path.exists(local_file):
            try:
                with open(local_file, "r") as f:
                    saved = json.load(f)
                match = saved.get(cid) or saved.get(customer_id)
                if match:
                    res = match.copy()
                    res["status"] = "Verification Successful"
                    return res
            except Exception:
                pass

    # 3. Check signed browser cookie customer cache (bridges ephemeral /tmp across serverless instances)
    if has_request_context():
        try:
            cookie_customers = session.get("loanai_customers")
            if isinstance(cookie_customers, dict):
                match = cookie_customers.get(cid) or cookie_customers.get(customer_id)
                if isinstance(match, dict):
                    res = match.copy()
                    res["status"] = "Verification Successful"
                    return res
        except Exception:
            pass

    # 4. Check built-in dummy customers
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
    """Save customer to writable customers.json, signed session cookie cache, and Firebase (if configured)."""
    customer_id = customer_data["customer_id"].lower().strip()
    local_saved = False
    firebase_saved = False
    firebase_error = ""

    # 1. Save to writable customers.json (seeded from bundled customers.json on serverless)
    local_file = RUNTIME_CUSTOMERS_FILE
    customers = {}
    seed_file = local_file if os.path.exists(local_file) else BUNDLED_CUSTOMERS_FILE
    if os.path.exists(seed_file):
        try:
            with open(seed_file, "r") as f:
                customers = json.load(f)
        except Exception:
            customers = {}

    customers[customer_id] = customer_data
    try:
        parent = os.path.dirname(os.path.abspath(local_file))
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        with open(local_file, "w") as f:
            json.dump(customers, f, indent=2)
        local_saved = True
        print(f"[INFO] Customer {customer_id} saved locally in {local_file}")
    except Exception as e:
        print(f"[ERROR] Could not save customer to {local_file}: {e}")

    # 2. Persist compact customer record in signed Flask cookie so serverless cold starts / lambda hops retain it
    if has_request_context():
        try:
            cookie_customers = dict(session.get("loanai_customers") or {})
            compact_customer = {
                "customer_id": customer_id,
                "name": customer_data.get("name"),
                "phone": customer_data.get("phone", ""),
                "email": customer_data.get("email", ""),
                "dob": customer_data.get("dob", ""),
                "age": customer_data.get("age"),
                "city": customer_data.get("city", ""),
                "pannumber": customer_data.get("pannumber", ""),
                "salary": customer_data.get("salary", 0),
                "credit_score": customer_data.get("credit_score", 0),
                "pre_approved_limit": customer_data.get("pre_approved_limit", 0),
                "current_loan_status": str(customer_data.get("current_loan_status", "0")),
            }
            cookie_customers.pop(customer_id, None)
            cookie_customers[customer_id] = compact_customer
            # Cap at most 5 dynamic customer records so total cookie stays safely under 4KB
            while len(cookie_customers) > 5:
                oldest_key = next(iter(cookie_customers))
                cookie_customers.pop(oldest_key, None)
            session["loanai_customers"] = cookie_customers
            session.modified = True
        except Exception:
            pass

    # 3. Save to Firebase if configured
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
                    "dob": customer_data.get("dob", ""),
                    "age": customer_data.get("age"),
                    "city": customer_data.get("city"),
                    "pannumber": customer_data.get("pannumber"),
                    "currentloan": customer_data.get("current_loan_status", 0)
                },
                "salary": customer_data.get("salary"),
                "credit_score": customer_data.get("credit_score"),
                "pre_approved_limit": customer_data.get("pre_approved_limit")
            }
            resp = requests.put(url, json=fb_payload, timeout=3)
            if resp.status_code == 200:
                firebase_saved = True
                print(f"[INFO] Customer {customer_id} saved to Firebase")
            else:
                firebase_error = f"Firebase returned HTTP {resp.status_code}"
                print(f"[WARNING] Firebase customer save failed: {firebase_error}")
        except Exception as e:
            firebase_error = str(e)
            print(f"[WARNING] Could not save customer to Firebase: {e}")

    return {
        "local_saved": local_saved,
        "firebase_saved": firebase_saved,
        "firebase_error": firebase_error,
    }


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
        msg = (
            "Email not sent: Gmail credentials not configured "
            "(set GMAIL_USER and GMAIL_APP_PASSWORD in Vercel Environment Variables or config.json)."
        )
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
        msg = "Email failed: Gmail authentication error. Check GMAIL_USER and 16-character GMAIL_APP_PASSWORD."
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

# ── Intent Classification, Validation & Safe Conversational Helpers ──

CUSTOMER_ID_REGEX = re.compile(
    r"\bcust(?!(?:omer|omers|om|oms|omize|omized|ody)\b)[a-z0-9_]+\b",
    re.IGNORECASE,
)

QUESTION_START_REGEX = re.compile(
    r"^\s*(?:why|what|how|when|where|which|who|explain|tell\s+me|can\s+you|could\s+you|would\s+you|do\s+i|does|is\s+there|are\s+there|is\s+it|should\s+i|will\s+i|could\s+i|am\s+i)\b",
    re.IGNORECASE,
)

QUESTION_PHRASE_REGEX = re.compile(
    r"(?:\?\s*$|\b(?:why\s+(?:do|is|are|does|must|need|more|above|700|21|65|50|pan)|what\s+(?:is|are|does|happens)|how\s+(?:does|do|is|can|long)|mean\s+by|meaning\s+of|difference\s+between|minimum\s+loan|maximum\s+loan|explain\b))",
    re.IGNORECASE,
)

NON_LOAN_NUMERIC_CONTEXT_REGEX = re.compile(
    r"\b(?:cibil|credit\s*score|score|age|years?\s*old|foir|percent|%|\bp\.?\s*a\.?\b|interest\s*rate|roi|pan\b|phone|mobile)\b",
    re.IGNORECASE,
)

EXPLICIT_LOAN_REQUEST_REGEX = re.compile(
    r"\b(?:apply(?:\s+for)?|want\s+(?:to\s+apply|a\s+loan|rs|₹|\d)|need\s+(?:a\s+loan|rs|₹|\d)|borrow|request(?:ing)?|take\s+(?:a\s+)?loan|get\s+(?:a\s+)?loan|loan\s+(?:of|amount)|sanction\s+(?:of|me))\b",
    re.IGNORECASE,
)

ONBOARDING_STEP_REMINDERS = {
    "ASK_NAME": "Please share your **Full Legal Name** to continue registration (or type `'cancel'` to stop).",
    "ASK_PHONE": "Please share your **10-digit Mobile Number** to continue registration (or type `'cancel'` to stop).",
    "ASK_EMAIL": "Please share your **Email Address** to continue registration (or type `'cancel'` to stop).",
    "ASK_AGE_CITY": "Please share your **Age (21–65 yrs)** and **City** of residence (e.g. `28, Mumbai`), or type `'cancel'` to stop.",
    "ASK_PAN": "Please share your **10-character PAN Number** (e.g. `ABCDE1234F`), or type `'cancel'` to stop.",
    "ASK_SALARY": "Please share your **Monthly Net Salary** in ₹ (e.g. `50000`), or type `'cancel'` to stop.",
    "ASK_EXISTING_LOAN": "Please share your **Existing Monthly EMIs** in ₹ (or reply `0` / `none`), or type `'cancel'` to stop.",
    "ASK_CREDIT_SCORE": "Please provide a valid **CIBIL / Credit Score** (**700–900** required in this system), or type `'cancel'` to stop.",
}

ONBOARDING_CONTEXT_HINTS = {
    "ASK_NAME": "Full Legal Name",
    "ASK_PHONE": "10-digit Mobile Number",
    "ASK_EMAIL": "Email Address",
    "ASK_AGE_CITY": "Age (mandatory 21–65 years) and City of residence",
    "ASK_PAN": "10-character PAN Card Number",
    "ASK_SALARY": "Monthly Net In-Hand Salary in INR",
    "ASK_EXISTING_LOAN": "Existing Monthly Loan EMIs in INR (checked against 50% FOIR limit)",
    "ASK_CREDIT_SCORE": "CIBIL Credit Score (300–900 scale; minimum 700 required by this project's rules)",
}


def is_general_question(text):
    """
    Detect informational, educational, or policy questions (e.g. 'Why do I need more than 700?',
    'What is FOIR?', 'What is the minimum loan amount?') so they are answered conversationally
    instead of corrupting onboarding fields or triggering loan underwriting.
    """
    if not text:
        return False
    s = str(text).strip()
    if QUESTION_START_REGEX.search(s):
        return True
    if QUESTION_PHRASE_REGEX.search(s):
        return True
    return False


def is_onboarding_cancel_command(text):
    t = (text or "").lower().strip()
    return bool(re.search(r"\b(?:cancel|stop|abort|exit|quit|start\s+over)\b", t))


def is_onboarding_trigger_phrase(text):
    t = (text or "").lower().strip()
    return any(p in t for p in [
        "new customer", "new user", "register me", "sign up", "signup", "create account",
        "add customer", "add me", "i am new", "i am a new customer",
        "i don't have customer id", "i dont have customer id", "i don't have an id",
        "i dont have an id", "no customer id", "no id", "dont have id", "don't have id",
        "onboard me", "start onboarding", "want to register", "register as",
    ]) or t == "register"


def is_logout_phrase(text):
    t = (text or "").lower().strip()
    return any(p in t for p in [
        "logout", "log out", "switch customer", "change customer", "change user", "sign out", "reset customer"
    ])


def is_profile_lookup_query(text):
    t = (text or "").lower().strip()
    return any(p in t for p in [
        "check limit", "my limit", "what is my limit", "eligible limit", "check my limit",
        "my profile", "who am i", "my details", "profile details", "account details",
        "check my profile", "eligibility status"
    ])


def is_emi_calculation_query(text):
    t = (text or "").lower().strip()
    if t.startswith("why "):
        return False
    return any(p in t for p in [
        "calculate emi", "emi for", "emi calculation", "calculate loan emi"
    ]) or ("emi" in t and parse_loan_amount_text(t) is not None and not EXPLICIT_LOAN_REQUEST_REGEX.search(t))


def is_structured_faq_query(text):
    """
    Match exact deterministic rule/doc FAQs when NOT framed as an explanatory 'why' or general conceptual question.
    """
    t = (text or "").lower().strip()
    if re.search(r"^\s*(?:why|what\s+happens|explain)\b", t):
        return False
    if any(w in t for w in ["document", "documents", "docs", "paperwork"]):
        return True
    if any(p in t for p in [
        "eligibility criteria", "eligibility rules", "loan criteria", "loan rules", "qualify", "requirements"
    ]) and "why" not in t and "minimum loan" not in t:
        return True
    return False


def parse_strict_numeric_value(text):
    """
    Parse an explicit standalone monetary or integer entry cleanly (for salary/EMI fields),
    without grabbing stray numbers out of conversational questions.
    """
    if not text or is_general_question(text):
        return None
    s = str(text).strip()
    # Reject obvious multi-sentence / non-numeric conversational chatter
    if len(s.split()) > 6 and not re.search(r"(?:salary|emi|income|loan|rs|₹|lakhs?|lacs?|k)\b", s, re.IGNORECASE):
        return None
    return parse_loan_amount_text(s)


def extract_explicit_cibil_input(text):
    """
    Strictly extract an explicitly supplied CIBIL credit score from user input.
    Never defaults invalid or conversational input to 700/750.
    Returns (int_score_or_None, reason_code) where reason_code in:
      'valid_int', 'question', 'skip_not_allowed', 'non_numeric'
    """
    if not text:
        return None, "non_numeric"
    if is_general_question(text):
        return None, "question"

    t = str(text).lower().strip()
    if re.search(r"\b(?:skip|don'?t\s+know|dont\s+know|not\s+sure|na|n/a|none|default)\b", t):
        return None, "skip_not_allowed"

    # Match standalone integer (e.g. "780", "200", "400") or explicit score phrase (e.g. "cibil 780", "score is 650")
    standalone = re.match(r"^\s*(\d{1,5})\s*$", t)
    if standalone:
        return int(standalone.group(1)), "valid_int"

    score_phrase = re.match(
        r"^\s*(?:my\s+)?(?:cibil|credit)?\s*(?:score)?\s*(?:is|:|=)?\s*(\d{1,5})\s*(?:score|points?)?\s*$",
        t,
    )
    if score_phrase:
        return int(score_phrase.group(1)), "valid_int"

    return None, "non_numeric"


def extract_explicit_loan_request(text):
    """
    Extract (loan_amount, tenure_months, status) ONLY when the user explicitly requests or confirms
    a loan amount — NEVER from questions, CIBIL/age mentions, or non-loan chatter.
    status in: 'valid', 'question', 'non_loan_context', 'ambiguous_amount', 'no_amount'
    """
    if not text:
        return None, None, "no_amount"
    s = str(text).strip()

    if is_general_question(s):
        return None, None, "question"

    # Extract tenure first and remove the tenure phrase so '60 months' is not parsed as loan amount 60
    tenure = parse_tenure_months(s)
    text_no_tenure = re.sub(
        r"\b(?:for\s+)?\d+\s*(?:years?|yrs?|months?|mos?)\b",
        " ",
        s,
        flags=re.IGNORECASE,
    )
    text_no_tenure = re.sub(r"\btenure\s*(?:of|is|:)?\s*\d+\b", " ", text_no_tenure, flags=re.IGNORECASE).strip()

    has_explicit_intent = bool(EXPLICIT_LOAN_REQUEST_REGEX.search(s))
    has_non_loan_context = bool(NON_LOAN_NUMERIC_CONTEXT_REGEX.search(s))

    # Numbers paired with score/age/rate/FOIR without explicit loan request intent must never trigger underwriting
    if has_non_loan_context and not has_explicit_intent:
        return None, None, "non_loan_context"

    # Parse candidate amount strictly from remaining non-tenure text
    cleaned = text_no_tenure.lower().replace(",", "").replace("₹", "").replace("rs.", "").replace("rs", "").strip()
    is_standalone_amount = bool(
        re.match(
            r"^(?:loan\s*(?:amount)?\s*(?:is|:|=)?\s*)?\d+(?:\.\d+)?\s*(?:lakhs?|lacs?|l|k)?(?:\s*only)?\.?$",
            cleaned,
        )
    )

    if not is_standalone_amount and not has_explicit_intent:
        return None, None, "no_amount"

    amt = parse_loan_amount_text(text_no_tenure)
    if not amt or amt <= 0:
        return None, None, "no_amount"

    has_currency_or_unit = bool(
        re.search(r"(?:₹|\brs\.?|\binr\b|\d\s*(?:lakhs?|lacs?|l|k)\b)", s, re.IGNORECASE)
    )

    # Guard against bare small integers like "700" or "250" typed without loan/currency context
    if amt < 1000 and not (has_explicit_intent and has_currency_or_unit):
        return None, None, "ambiguous_amount"

    return amt, tenure, "valid"


def sanitize_llm_reply(text):
    """Strip any stray FLASK_CALL tokens so Gemini cannot trigger backend actions on its own."""
    if not text:
        return ""
    return re.sub(r"\[\[FLASK_CALL:[A-Z_]+\]\]", "", str(text)).strip()


def append_onboarding_reminder(reply_text, onboarding_state):
    """Attach the pending registration question after answering an interruption cleanly."""
    reminder = ONBOARDING_STEP_REMINDERS.get(onboarding_state)
    if not reminder:
        return reply_text
    return f"{reply_text.rstrip()}\n\n---\n📌 **To continue your registration:** {reminder}"


def evaluate_customer_profile_eligibility(customer):
    """
    Deterministic Python evaluation of a verified customer's profile against underwriting thresholds.
    Clearly separates salary-based preliminary limit (15x) from actual underwriting eligibility.
    """
    if not isinstance(customer, dict):
        return None

    salary = float(customer.get("salary", 0) or 0)
    credit = int(customer.get("credit_score", 0) or 0)

    dob_raw = customer.get("dob")
    age_calc = calculate_age_from_dob(dob_raw) if dob_raw else None
    if age_calc is not None:
        age = age_calc
    else:
        try:
            age = int(customer.get("age", 0) or 0)
        except (TypeError, ValueError):
            age = 0

    curr_loan_raw = customer.get("current_loan_status") or customer.get("currentloan") or 0
    try:
        if isinstance(curr_loan_raw, str):
            clean_curr = re.sub(r"[^\d.]", "", curr_loan_raw)
            existing_emi = float(clean_curr) if clean_curr else 0.0
        else:
            existing_emi = float(curr_loan_raw)
    except (TypeError, ValueError):
        existing_emi = 0.0

    preliminary_limit = float(customer.get("pre_approved_limit") or calculate_preapproved_limit_from_salary(salary))
    max_foir_budget = salary * 0.50
    max_affordable_emi = max(0.0, max_foir_budget - existing_emi)
    recommended_tenure = determine_tenure_months(salary)

    failed_criteria = []
    if age < 21 or age > 65:
        failed_criteria.append(f"Age ({age} years) is outside the required 21–65 years range.")
    if credit < 700:
        failed_criteria.append(f"CIBIL credit score ({credit}) is below the configured minimum threshold of 700.")
    if salary <= 0:
        failed_criteria.append("Monthly net salary must be greater than ₹0.")
    elif existing_emi > max_foir_budget + 0.01:
        foir_pct = (existing_emi / salary) * 100.0
        failed_criteria.append(
            f"Existing monthly EMIs (₹{int(existing_emi):,}, {foir_pct:.1f}% FOIR) exceed the 50% affordability cap."
        )

    eligible_for_final = len(failed_criteria) == 0
    if customer.get("sanction"):
        app_status = "Final Approved (Sanction Letter Issued)"
    elif eligible_for_final:
        app_status = "Preliminary Eligible (Pending Loan Amount & Final Underwriting)"
    else:
        app_status = "Preliminary Limit Calculated — Not Eligible for Final Approval"

    return {
        "salary": salary,
        "credit_score": credit,
        "age": age,
        "existing_emi": existing_emi,
        "preliminary_limit": preliminary_limit,
        "max_foir_budget": max_foir_budget,
        "max_affordable_emi": max_affordable_emi,
        "recommended_tenure": recommended_tenure,
        "failed_criteria": failed_criteria,
        "eligible_for_final": eligible_for_final,
        "application_status": app_status,
    }


SYSTEM_INTEREST_RATE = 12.0


def build_eligibility_dashboard_payload(session_id, refresh_from_firebase=True):
    """
    Build the authoritative read-only Loan Eligibility Dashboard payload for a session's
    verified customer using existing underwriting & EMI functions.
    Never modifies customer records or triggers underwriting.
    """
    verified_cust, assessment = get_verified_customer_context(session_id, refresh_from_firebase=refresh_from_firebase)
    if not verified_cust or not assessment:
        return {
            "verified": False,
            "requires_kyc": True,
            "system_config": {
                "min_cibil": 700,
                "max_cibil": 900,
                "min_cibil_scale": 300,
                "min_age": 21,
                "max_age": 65,
                "salary_multiplier": 15,
                "max_foir_pct": 50.0,
                "allowed_tenures": [48, 60, 72],
                "interest_rate_pa": SYSTEM_INTEREST_RATE,
            },
            "message": "Please complete KYC verification first by entering your Customer ID (e.g., cust01 or cust99) or registering as a new customer.",
        }

    salary = assessment["salary"]
    credit = assessment["credit_score"]
    age = assessment["age"]
    existing_emi = assessment["existing_emi"]
    preliminary_limit = assessment["preliminary_limit"]
    max_foir_budget = assessment["max_foir_budget"]
    max_affordable_emi = assessment["max_affordable_emi"]
    rec_tenure = assessment["recommended_tenure"]

    req_amt = verified_cust.get("last_requested_amount")
    req_tenure = verified_cust.get("last_requested_tenure")
    last_uw = verified_cust.get("last_underwriting_result")

    # ── 1. Age Criterion ──
    if not age or age <= 0:
        age_item = {
            "key": "age_requirement",
            "label": "Age Requirement (21–65 yrs)",
            "status": "pending",
            "actual": "Not provided",
            "required": "21–65 years",
            "reason": "Applicant age or date of birth is missing from the profile and cannot be evaluated yet.",
        }
    elif 21 <= age <= 65:
        age_item = {
            "key": "age_requirement",
            "label": "Age Requirement (21–65 yrs)",
            "status": "passed",
            "actual": f"{age} years",
            "required": "21–65 years",
            "reason": f"Applicant age ({age} years) satisfies the mandatory 21–65 years range.",
        }
    else:
        age_item = {
            "key": "age_requirement",
            "label": "Age Requirement (21–65 yrs)",
            "status": "failed",
            "actual": f"{age} years",
            "required": "21–65 years",
            "reason": f"Applicant age ({age} years) is outside the eligible 21–65 years range.",
        }

    # ── 2. Minimum CIBIL Score Criterion ──
    if not credit or credit <= 0:
        cibil_status = "pending"
        cibil_actual = "Not available"
        cibil_reason = "CIBIL credit score is missing from the profile and has not been evaluated."
    elif 700 <= credit <= 900:
        cibil_status = "passed"
        cibil_actual = str(credit)
        cibil_reason = f"Verified CIBIL score ({credit}) meets the configured minimum threshold of 700."
    elif credit > 900:
        cibil_status = "failed"
        cibil_actual = str(credit)
        cibil_reason = f"Credit score ({credit}) exceeds the valid 300–900 CIBIL scale."
    else:
        cibil_status = "failed"
        cibil_actual = str(credit)
        cibil_reason = f"CIBIL score ({credit}) is below the configured minimum threshold of 700."

    cibil_item = {
        "key": "minimum_cibil",
        "label": "Minimum CIBIL Score (≥ 700)",
        "status": cibil_status,
        "actual": cibil_actual,
        "required": "≥ 700 (300–900)",
        "reason": cibil_reason,
    }

    # ── 3. Salary-Based Preliminary Limit Criterion ──
    if salary <= 0:
        limit_item = {
            "key": "salary_preliminary_limit",
            "label": "Salary-Based Preliminary Limit (15×)",
            "status": "pending",
            "actual": "Salary missing",
            "required": "> ₹0 net salary",
            "reason": "Monthly net salary is missing, so the 15× salary-based preliminary limit cannot be calculated.",
        }
    else:
        limit_item = {
            "key": "salary_preliminary_limit",
            "label": "Salary-Based Preliminary Limit (15×)",
            "status": "passed",
            "actual": f"₹{int(preliminary_limit):,}",
            "required": "15× ₹" + f"{int(salary):,}",
            "reason": f"Monthly net salary of ₹{int(salary):,} establishes a salary-based preliminary cap of ₹{int(preliminary_limit):,}.",
        }

    # ── 4. Requested Amount vs Limit & FOIR & Tenure Evaluation ──
    eval_emi = None
    eval_foir = None
    if req_amt is not None and req_amt > 0:
        eval_tenure = int(req_tenure) if req_tenure else rec_tenure
        eval_emi = calculate_emi(float(req_amt), SYSTEM_INTEREST_RATE, eval_tenure) or 0.0
        total_emi = existing_emi + eval_emi
        eval_foir = (total_emi / salary) * 100.0 if salary > 0 else 100.0

        # FOIR check matching underwrite()
        if salary <= 0:
            foir_item = {
                "key": "foir_affordability",
                "label": "FOIR Affordability (≤ 50%)",
                "status": "pending",
                "actual": "Salary missing",
                "required": "≤ 50.0% of salary",
                "reason": "Monthly net salary is required to compute FOIR affordability.",
            }
        elif round(eval_foir, 2) <= 50.00 and total_emi <= (max_foir_budget + 0.01):
            foir_item = {
                "key": "foir_affordability",
                "label": "FOIR Affordability (≤ 50%)",
                "status": "passed",
                "actual": f"{eval_foir:.1f}% (₹{int(total_emi):,}/mo)",
                "required": f"≤ 50.0% (₹{int(max_foir_budget):,}/mo)",
                "reason": f"Total monthly obligations of ₹{int(total_emi):,} ({eval_foir:.1f}% FOIR) fit within the 50% limit.",
            }
        else:
            foir_item = {
                "key": "foir_affordability",
                "label": "FOIR Affordability (≤ 50%)",
                "status": "failed",
                "actual": f"{eval_foir:.1f}% (₹{int(total_emi):,}/mo)",
                "required": f"≤ 50.0% (₹{int(max_foir_budget):,}/mo)",
                "reason": f"Total monthly EMIs of ₹{int(total_emi):,} ({eval_foir:.1f}% FOIR) exceed 50% of salary (₹{int(max_foir_budget):,}).",
            }

        # Requested Amount vs Limit
        if salary <= 0:
            req_limit_item = {
                "key": "requested_vs_limit",
                "label": "Requested Loan vs. Eligibility Limit",
                "status": "pending",
                "actual": f"₹{int(req_amt):,}",
                "required": "Salary limit missing",
                "reason": "Salary-based limit is missing, so requested loan amount cannot be validated.",
            }
        elif req_amt <= preliminary_limit:
            req_limit_item = {
                "key": "requested_vs_limit",
                "label": "Requested Loan vs. Eligibility Limit",
                "status": "passed",
                "actual": f"₹{int(req_amt):,}",
                "required": f"≤ ₹{int(preliminary_limit):,}",
                "reason": f"Requested amount ₹{int(req_amt):,} is within your ₹{int(preliminary_limit):,} preliminary limit.",
            }
        else:
            req_limit_item = {
                "key": "requested_vs_limit",
                "label": "Requested Loan vs. Eligibility Limit",
                "status": "failed",
                "actual": f"₹{int(req_amt):,}",
                "required": f"≤ ₹{int(preliminary_limit):,}",
                "reason": f"Requested amount ₹{int(req_amt):,} exceeds your ₹{int(preliminary_limit):,} preliminary limit.",
            }

        # Applicable Tenure
        if 48 <= eval_tenure <= 72:
            tenure_item = {
                "key": "applicable_tenure",
                "label": "Applicable Loan Tenure (48–72 mo)",
                "status": "passed",
                "actual": f"{eval_tenure} months",
                "required": "48–72 months",
                "reason": f"Selected tenure ({eval_tenure} months) is within the allowed 48–72 months window.",
            }
        else:
            tenure_item = {
                "key": "applicable_tenure",
                "label": "Applicable Loan Tenure (48–72 mo)",
                "status": "failed",
                "actual": f"{eval_tenure} months",
                "required": "48–72 months",
                "reason": f"Selected tenure ({eval_tenure} months) is outside the allowed 48–72 months range.",
            }
    else:
        # No loan amount submitted yet: check if existing EMIs already fail FOIR, otherwise mark Pending
        if salary <= 0:
            foir_item = {
                "key": "foir_affordability",
                "label": "FOIR Affordability (≤ 50%)",
                "status": "pending",
                "actual": "Salary missing",
                "required": "≤ 50.0% of salary",
                "reason": "Monthly net salary is missing; FOIR cannot be calculated.",
            }
        elif existing_emi > max_foir_budget + 0.01:
            curr_foir = (existing_emi / salary) * 100.0
            foir_item = {
                "key": "foir_affordability",
                "label": "FOIR Affordability (≤ 50%)",
                "status": "failed",
                "actual": f"{curr_foir:.1f}% existing",
                "required": f"≤ 50.0% (₹{int(max_foir_budget):,}/mo)",
                "reason": f"Existing monthly EMIs (₹{int(existing_emi):,}) already exceed the 50% FOIR cap.",
            }
        else:
            foir_item = {
                "key": "foir_affordability",
                "label": "FOIR Affordability (≤ 50%)",
                "status": "pending",
                "actual": f"₹{int(max_affordable_emi):,}/mo free capacity",
                "required": f"≤ 50.0% (₹{int(max_foir_budget):,}/mo)",
                "reason": f"Remaining EMI capacity is ₹{int(max_affordable_emi):,}/month; submit a loan amount to evaluate total FOIR.",
            }

        req_limit_item = {
            "key": "requested_vs_limit",
            "label": "Requested Loan vs. Eligibility Limit",
            "status": "pending",
            "actual": "Not requested yet",
            "required": (f"≤ ₹{int(preliminary_limit):,}" if salary > 0 else "Salary limit missing"),
            "reason": "No loan amount has been submitted for underwriting comparison yet.",
        }

        tenure_item = {
            "key": "applicable_tenure",
            "label": "Applicable Loan Tenure (48–72 mo)",
            "status": "pending",
            "actual": (f"Band default: {rec_tenure} mo" if salary > 0 else "Pending salary"),
            "required": "48–72 months",
            "reason": (
                f"Default tenure based on salary band is {rec_tenure} months; final tenure is evaluated upon submission."
                if salary > 0
                else "Salary is missing; tenure band cannot be assigned yet."
            ),
        }

    checklist = [age_item, cibil_item, limit_item, foir_item, req_limit_item, tenure_item]

    passed_list = [item["reason"] for item in checklist if item["status"] == "passed"]
    failed_list = [item["reason"] for item in checklist if item["status"] == "failed"]
    pending_list = [item["reason"] for item in checklist if item["status"] == "pending"]

    # Determine overall status & "Why this result?" narrative
    has_missing_core = any(
        item["key"] in ("age_requirement", "minimum_cibil", "salary_preliminary_limit") and item["status"] == "pending"
        for item in checklist
    )

    if last_uw and last_uw.get("status") == "Approved":
        overall_status = "Final Approved"
        overall_tone = "approved"
        why_headline = "Final Loan Approval Granted"
        why_summary = (
            f"Your requested loan of ₹{int(req_amt):,} passed all underwriting rules "
            f"(Age {age}, CIBIL {credit}, within ₹{int(preliminary_limit):,} limit, {eval_foir:.1f}% FOIR ≤ 50%)."
        )
    elif failed_list:
        overall_status = "Not Eligible"
        overall_tone = "rejected"
        why_headline = "Eligibility Criteria Not Met"
        if salary > 0 and credit > 0 and credit < 700:
            why_summary = (
                f"Your salary-based preliminary limit is ₹{int(preliminary_limit):,}. "
                f"However, your CIBIL score is {credit}, below the configured minimum of 700. "
                "Therefore, you currently fail the credit-score criterion and cannot obtain final approval."
            )
        else:
            why_summary = " ".join(failed_list)
    elif has_missing_core:
        overall_status = "Incomplete Profile"
        overall_tone = "pending"
        why_headline = "Profile Incomplete — Cannot Evaluate Fully"
        why_summary = "One or more mandatory customer attributes (age, CIBIL score, or monthly salary) are missing and must be provided before eligibility can be finalized."
    elif req_amt is None:
        overall_status = "Preliminary Eligible"
        overall_tone = "preapproved"
        why_headline = "Baseline Criteria Passed — Ready to Apply"
        why_summary = (
            f"You meet all baseline profile checks (Age {age} yrs, CIBIL {credit} ≥ 700) with a "
            f"salary-based preliminary limit of ₹{int(preliminary_limit):,} and ₹{int(max_affordable_emi):,}/month remaining EMI capacity. "
            "Submit a loan amount below or in chat to run final underwriting."
        )
    else:
        overall_status = "Eligible"
        overall_tone = "approved"
        why_headline = "All Underwriting Checks Passed"
        why_summary = f"All criteria passed for ₹{int(req_amt):,} at {eval_foir:.1f}% FOIR."

    return {
        "verified": True,
        "requires_kyc": False,
        "customer": {
            "customer_id": verified_cust.get("customer_id"),
            "name": verified_cust.get("name", "Customer"),
            "salary": salary,
            "credit_score": credit,
            "age": age,
            "existing_emi": existing_emi,
            "preliminary_limit": preliminary_limit,
            "max_foir_budget": max_foir_budget,
            "max_affordable_emi": max_affordable_emi,
            "recommended_tenure": rec_tenure,
            "requested_loan_amount": req_amt,
            "requested_tenure": req_tenure,
            "overall_status": overall_status,
            "overall_tone": overall_tone,
            "application_status": assessment["application_status"],
            "sanction": verified_cust.get("sanction"),
        },
        "credit_score_card": {
            "score": credit if credit and credit > 0 else None,
            "min_required": 700,
            "min_scale": 300,
            "max_scale": 900,
            "status": cibil_status,
            "explanation": cibil_reason,
        },
        "checklist": checklist,
        "why_this_result": {
            "headline": why_headline,
            "summary": why_summary,
            "passed_conditions": passed_list,
            "failed_conditions": failed_list,
            "pending_conditions": pending_list,
            "preliminary_vs_final_note": (
                "Preliminary eligibility (15× monthly net salary) only estimates borrowing capacity and is not final approval. "
                "Final loan approval requires passing Age (21–65), CIBIL (≥ 700), Limit (≤ 15× salary), Tenure (48–72 months), and FOIR (≤ 50%) in Python underwriting."
            ),
        },
        "system_config": {
            "min_cibil": 700,
            "max_cibil": 900,
            "min_cibil_scale": 300,
            "min_age": 21,
            "max_age": 65,
            "salary_multiplier": 15,
            "max_foir_pct": 50.0,
            "allowed_tenures": [48, 60, 72],
            "interest_rate_pa": SYSTEM_INTEREST_RATE,
        },
    }


def simulate_loan_for_verified_customer(session_id, loan_amount, tenure_months=None, interest_rate=None):
    """
    Read-only backend EMI & FOIR simulator using calculate_emi() and verified session profile.
    Never modifies customer records or initiates underwriting.
    """
    verified_cust, assessment = get_verified_customer_context(session_id, refresh_from_firebase=False)
    if not verified_cust or not assessment:
        return {"verified": False, "requires_kyc": True, "message": "Please complete KYC verification first."}, 200

    amt = parse_loan_amount_text(loan_amount)
    if amt is None or amt <= 0 or amt > 1_000_000_000:
        return {"verified": True, "error": "Please enter a valid positive loan amount (up to ₹1,00,00,00,000)."}, 400

    try:
        tenure = int(tenure_months) if tenure_months is not None else assessment["recommended_tenure"]
    except (TypeError, ValueError):
        return {"verified": True, "error": "Tenure must be a valid integer in months (48, 60, or 72)."}, 400
    if tenure < 12 or tenure > 120:
        return {"verified": True, "error": "Simulator tenure must be between 12 and 120 months (system underwriting supports 48–72 months)."}, 400

    try:
        rate = float(interest_rate) if interest_rate is not None else SYSTEM_INTEREST_RATE
    except (TypeError, ValueError):
        return {"verified": True, "error": "Interest rate must be a valid number."}, 400
    if rate < 0 or rate > 50:
        return {"verified": True, "error": "Interest rate must be between 0% and 50% p.a."}, 400

    salary = assessment["salary"]
    existing_emi = assessment["existing_emi"]
    preliminary_limit = assessment["preliminary_limit"]
    max_foir_budget = assessment["max_foir_budget"]

    emi = calculate_emi(amt, rate, tenure) or 0.0
    total_repayment = emi * tenure
    total_interest = max(0.0, total_repayment - amt)
    total_monthly_emi = existing_emi + emi
    foir_pct = (total_monthly_emi / salary) * 100.0 if salary > 0 else 100.0

    within_limit = (salary > 0) and (amt <= preliminary_limit)
    within_foir = (salary > 0) and (round(foir_pct, 2) <= 50.00) and (total_monthly_emi <= (max_foir_budget + 0.01))
    within_tenure_policy = 48 <= tenure <= 72

    if salary <= 0:
        affordability_status = "Salary Missing"
        affordability_tone = "pending"
    elif within_foir and within_limit and within_tenure_policy and assessment["eligible_for_final"]:
        affordability_status = "Affordable & Eligible"
        affordability_tone = "approved"
    elif within_foir and within_limit:
        affordability_status = "Affordable EMI (Profile/Policy Check Pending or Blocked)"
        affordability_tone = "preapproved"
    elif not within_limit:
        affordability_status = "Exceeds 15× Salary Limit"
        affordability_tone = "rejected"
    else:
        affordability_status = "Exceeds 50% FOIR Limit"
        affordability_tone = "rejected"

    return {
        "verified": True,
        "simulation_only": True,
        "inputs": {
            "loan_amount": amt,
            "tenure_months": tenure,
            "interest_rate_pa": rate,
        },
        "results": {
            "monthly_emi": round(emi, 2),
            "monthly_emi_rounded": int(round(emi)),
            "total_interest": round(total_interest, 2),
            "total_interest_rounded": int(round(total_interest)),
            "total_repayment": round(total_repayment, 2),
            "total_repayment_rounded": int(round(total_repayment)),
            "existing_emi": existing_emi,
            "total_monthly_emi": round(total_monthly_emi, 2),
            "foir_pct": round(foir_pct, 1),
            "within_foir": within_foir,
            "within_salary_limit": within_limit,
            "within_tenure_policy": within_tenure_policy,
            "affordability_status": affordability_status,
            "affordability_tone": affordability_tone,
            "uses_custom_rate": abs(rate - SYSTEM_INTEREST_RATE) > 0.001,
            "system_interest_rate_pa": SYSTEM_INTEREST_RATE,
        },
    }, 200


def get_verified_customer_context(session_id, refresh_from_firebase=True):
    """
    Retrieve the session-bound verified customer record and deterministic eligibility summary.
    Restores across serverless invocations if needed and refreshes from Firebase RTDB when configured.
    Returns (customer_dict, assessment_dict) or (None, None) if session is unverified.
    """
    restore_session_state(session_id)
    sess = session_data.get(session_id)
    if not isinstance(sess, dict):
        return None, None
    cid = sess.get("customer_id")
    if not cid:
        return None, None
    if not (sess.get("verified") or sess.get("status") == "Verification Successful"):
        return None, None

    if refresh_from_firebase and FIREBASE_DB_URL:
        live_fb = get_customer_from_firebase(cid.lower().strip())
        if live_fb:
            # Preserve active session state flags (verified timestamp, sanction record)
            sanction_state = sess.get("sanction")
            verified_at = sess.get("verified_at")
            live_fb["status"] = "Verification Successful"
            live_fb["verified"] = True
            if verified_at:
                live_fb["verified_at"] = verified_at
            if sanction_state:
                live_fb["sanction"] = sanction_state
            session_data[session_id] = live_fb
            sess = live_fb

    assessment = evaluate_customer_profile_eligibility(sess)
    return sess, assessment


def build_minimal_verified_context_prompt(customer, assessment):
    """
    Build a concise, read-only verified customer context block for Gemini index-0 SystemMessage.
    Passes only minimum relevant financial/eligibility facts — omits PAN, phone, email, and other customers.
    """
    if not customer or not assessment:
        return ""

    failed_summary = (
        "None (meets baseline profile rules; final approval still depends on requested loan amount <= 15x salary, tenure 48–72 months, and total FOIR <= 50%)"
        if assessment["eligible_for_final"]
        else " | ".join(assessment["failed_criteria"])
    )
    sanction_info = customer.get("sanction")
    sanction_note = f"Yes ({sanction_info.get('pdf')})" if isinstance(sanction_info, dict) and sanction_info.get("pdf") else "No"

    return (
        "\n\nCURRENT VERIFIED SESSION CUSTOMER CONTEXT (session-bound, authenticated via KYC — use these exact figures when answering personal questions; do NOT ask the user to re-enter info shown below, do NOT reveal internal field names, and do NOT treat salary-based preliminary limit as final approval if any criterion failed):\n"
        f"- Customer ID: {customer.get('customer_id')}\n"
        f"- Name: {customer.get('name', 'Customer')}\n"
        f"- Monthly Net Salary: ₹{int(assessment['salary']):,}\n"
        f"- Total 50% FOIR Monthly Debt Ceiling (50% of salary): ₹{int(assessment['max_foir_budget']):,}/month\n"
        f"- Existing Monthly EMIs Already Committed: ₹{int(assessment['existing_emi']):,}/month\n"
        f"- Remaining Affordable Additional Proposed EMI (Ceiling minus Existing EMIs — already calculated; do NOT subtract existing EMIs again): ₹{int(assessment['max_affordable_emi']):,}/month\n"
        f"- Verified CIBIL / Credit Score: {assessment['credit_score']} (system minimum threshold: 700; scale: 300–900)\n"
        f"- Age: {assessment['age']} years (system range: 21–65)\n"
        f"- Salary-Based Preliminary Limit (15x salary): ₹{int(assessment['preliminary_limit']):,}\n"
        f"- Recommended Tenure Band: {assessment['recommended_tenure']} months @ 12% p.a.\n"
        f"- Current Application Status: {assessment['application_status']}\n"
        f"- Eligibility Check Result: {'MEETS BASELINE CRITERIA' if assessment['eligible_for_final'] else 'NOT ELIGIBLE FOR FINAL APPROVAL — Failed: ' + failed_summary}\n"
        f"- Sanction Letter Issued: {sanction_note}\n"
    )


def safe_local_informational_fallback(session_id, text):
    """
    Deterministic safe responder used ONLY when Gemini is unavailable or fails.
    Uses verified session customer context when available; never modifies onboarding state,
    never fabricates defaults, never triggers underwriting, and never leaks other customers.
    """
    t = (text or "").lower().strip()
    sess = session_data.get(session_id, {})
    verified_cust, assessment = get_verified_customer_context(session_id, refresh_from_firebase=False)

    # ── Verified Customer Personal Follow-up Handling (Local Fallback Parity) ──
    if verified_cust and assessment and not sess.get("onboarding_state"):
        name = verified_cust.get("name", "Customer")
        cid = verified_cust.get("customer_id")
        sal = int(assessment["salary"])
        score = assessment["credit_score"]
        limit = int(assessment["preliminary_limit"])
        max_emi = int(assessment["max_affordable_emi"])
        existing_emi = int(assessment["existing_emi"])
        failed = assessment["failed_criteria"]

        # 1. "Am I eligible for a loan?" / "Why am I not eligible?"
        if any(p in t for p in ["am i eligible", "not eligible", "why am i not", "eligible for a loan", "do i qualify", "can i get a loan", "eligibility"]):
            if assessment["eligible_for_final"]:
                return (
                    f"Based on your verified profile (**{name}**, `{cid}`):\n\n"
                    f"• **Monthly Net Salary**: ₹{sal:,}\n"
                    f"• **Credit Score (CIBIL)**: **{score}** *(meets minimum 700)*\n"
                    f"• **Preliminary Salary-Based Loan Limit (15×)**: **₹{limit:,}**\n"
                    f"• **Max Affordable Monthly EMI (50% FOIR)**: **₹{max_emi:,}/month**\n\n"
                    f"Your baseline profile meets our eligibility criteria (**Age 21–65**, **CIBIL ≥ 700**). "
                    f"Note that final loan approval is only granted after you enter a specific loan amount and pass full underwriting (amount ≤ ₹{limit:,}, tenure 48–72 months, total FOIR ≤ 50%)."
                )
            reasons_text = "\n• ".join(failed)
            return (
                f"Based on your verified profile (`{cid}`), your **monthly net salary is ₹{sal:,}** and your **credit score is {score}**.\n\n"
                f"• **Salary-Based Preliminary Limit (15×)**: ₹{limit:,} *(calculated strictly from salary)*\n"
                f"• **Final Underwriting Eligibility**: **Not Eligible for Final Approval**\n\n"
                f"**Reason(s):**\n• {reasons_text}\n\n"
                f"While a salary-based preliminary limit of ₹{limit:,} is shown, it is not final loan approval—our system requires CIBIL ≥ 700, age 21–65, and FOIR ≤ 50%."
            )

        # 2. "What is my credit score?" / "What is my CIBIL?"
        if any(p in t for p in ["my credit score", "my cibil", "what is my score", "credit score"]):
            meets = "meets" if score >= 700 else "does **not** meet"
            return (
                f"Your verified **CIBIL / Credit Score** (`{cid}`) is **{score}** (on the 300–900 scale).\n\n"
                f"• This {meets} our configured minimum threshold of **700** required for final loan approval."
            )

        # 3. "What is my maximum loan limit?"
        if any(p in t for p in ["maximum loan", "max loan", "my limit", "loan limit"]):
            status_clause = (
                "You can submit a loan application up to this limit for final underwriting."
                if assessment["eligible_for_final"]
                else f"However, because **{' '.join(failed)}**, you are currently **not eligible for final loan approval** despite the salary-based preliminary limit."
            )
            return (
                f"Based on your verified monthly salary of **₹{sal:,}**, your **salary-based preliminary maximum loan limit (15×)** is **₹{limit:,}**.\n\n"
                f"{status_clause}"
            )

        # 4. "How much salary do I earn?"
        if any(p in t for p in ["salary", "income", "earn"]):
            return (
                f"Your verified **Monthly Net Salary** on file (`{cid}`) is **₹{sal:,}** "
                f"(giving a 15× salary-based preliminary limit of **₹{limit:,}** and a 50% FOIR monthly debt ceiling of **₹{int(assessment['max_foir_budget']):,}/month**)."
            )

        # 5. "What is my current application status?"
        if any(p in t for p in ["application status", "current status", "my status"]):
            extra = "" if assessment["eligible_for_final"] else f"\n• **Blocking Criterion**: {' '.join(failed)}"
            return (
                f"**Current Application Status (`{cid}`):** `{assessment['application_status']}`\n\n"
                f"• **Salary-Based Preliminary Limit**: ₹{limit:,}\n"
                f"• **Verified CIBIL Score**: {score}{extra}"
            )

        # 6. "How much EMI can I afford?"
        if any(p in t for p in ["afford", "how much emi", "monthly emi"]):
            return (
                f"Under our **50% FOIR rule** on your verified monthly salary of **₹{sal:,}**:\n\n"
                f"• **Total Monthly Debt Ceiling (50%)**: ₹{int(assessment['max_foir_budget']):,}/month\n"
                f"• **Existing Monthly EMIs**: ₹{existing_emi:,}/month\n"
                f"• **Maximum Affordable Proposed EMI**: **₹{max_emi:,}/month**"
            )

        # 7. "What can I do to improve my eligibility?"
        if any(p in t for p in ["improve", "increase my", "how can i qualify", "become eligible"]):
            tips = []
            if score < 700:
                tips.append(
                    f"• **Improve Credit Score (currently {score} → need ≥ 700)**: Pay all credit card/loan EMIs on time, keep credit utilization below 30%, and avoid multiple hard credit inquiries."
                )
            if existing_emi > assessment["max_foir_budget"]:
                tips.append("• **Reduce Existing Debt Obligations**: Pay down active EMIs so total FOIR stays at or below 50% of monthly net salary.")
            if not tips:
                tips.append("• Your profile already meets baseline CIBIL (≥ 700), Age (21–65), and FOIR capacity. Keeping your EMI under 50% of salary and choosing 48–72 month tenure keeps eligibility strong.")
            return f"**Recommendations for your profile (`{cid}`):**\n\n" + "\n".join(tips)

    if any(w in t for w in ["700", "cibil", "credit score", "score"]):
        return (
            "A **CIBIL score of 700 or above** (on the 300–900 scale) is used as an eligibility threshold because a higher score generally indicates a stronger repayment history and lower perceived credit risk.\n\n"
            "• Note: **700** is the threshold configured in this project's demonstration underwriting rules, not a universal rule across every external lender."
        )

    if "foir" in t or "fixed obligation" in t:
        return (
            "**FOIR (Fixed Obligation to Income Ratio)** measures how much of your monthly net salary already goes toward debt EMIs:\n\n"
            "• Formula: `(Existing Monthly EMIs + Proposed Loan EMI) / Monthly Net Salary × 100`\n"
            "• In this project's rules, total FOIR must be **≤ 50%** so monthly repayments remain affordable."
        )

    if "minimum loan" in t or ("minimum" in t and "amount" in t):
        return (
            "This project's deterministic underwriting engine requires a requested loan amount **greater than ₹0**, subject to:\n\n"
            "• **Maximum Limit**: Up to **15× your monthly net salary**\n"
            "• **Affordability (FOIR)**: Total monthly EMIs must stay **≤ 50%** of monthly net salary\n\n"
            "*(There is no separate hardcoded minimum floor above ₹0 in the code, though practical personal loan requests are typically in thousands or lakhs. Let me know the amount you'd like to check!)*"
        )

    if "after registration" in t or ("what happens" in t and ("register" in t or "onboarding" in t)) or "how does loan approval work" in t:
        return (
            "Once you complete registration cleanly with valid details:\n\n"
            "1. Your customer profile receives an automatic **Customer ID** (`cust<mobile>`) and a **Preliminary Loan Eligibility** estimate (**15× monthly net salary**).\n"
            "2. You can then specify the loan amount you wish to apply for (or check EMI first).\n"
            "3. Our deterministic Python underwriting engine evaluates **Age (21–65), CIBIL (≥ 700), 15× salary limit, Tenure (48–72 months), and FOIR (≤ 50%)**.\n"
            "4. Approved applications automatically generate a PDF Sanction Letter in `sanctions/` and dispatch it if email is configured."
        )

    if "document" in t or "docs" in t or "paperwork" in t:
        return (
            "📄 **Documents Required for Loan Approval:**\n\n"
            "1. **Identity Proof**: PAN Card (mandatory) & Aadhaar Card / Passport.\n"
            "2. **Address Proof**: Aadhaar Card, Utility Bill, or Rental Agreement.\n"
            "3. **Income Proof**: Last 3 months Salary Slips & Form 16 / ITR.\n"
            "4. **Bank Statement**: Last 6 months bank statement showing regular salary deposits."
        )

    if any(w in t for w in ["eligibility", "criteria", "rules", "requirements", "age", "tenure", "interest"]):
        return (
            "📋 **Loan Eligibility Criteria (Demonstration Rules):**\n\n"
            "• **Age**: 21 to 65 years.\n"
            "• **CIBIL Score**: Minimum 700 (range 300–900).\n"
            "• **Maximum Loan Limit**: Up to **15× monthly net salary**.\n"
            "• **FOIR Limit**: Existing EMIs + proposed EMI ≤ **50%** of monthly net salary.\n"
            "• **Interest Rate**: Fixed 12% per annum.\n"
            "• **Tenure**: 48 to 72 months."
        )

    if sess.get("onboarding_state"):
        return (
            "I'm currently running in local fallback mode because the Gemini AI service is unavailable, so I can best help with questions about CIBIL rules, FOIR, eligibility limits, or required documents while keeping your registration progress safe."
        )

    if any(w in t for w in ["hi", "hello", "hey", "help", "good morning", "good evening", "namaste", "options", "menu"]):
        return (
            "Hello! 👋 I'm your **AI Loan Approval Assistant**.\n\n"
            "Here is how I can assist you:\n"
            "1️⃣ **New Customer Registration**: Type **'I am a new customer'** to register step-by-step.\n"
            "2️⃣ **Verify Existing Customer**: Enter your Customer ID (e.g. `cust01`, `cust10`).\n"
            "3️⃣ **Calculate EMI**: Type *'Calculate EMI for ₹5,00,000'*.\n"
            "4️⃣ **Eligibility & Docs**: Ask about CIBIL 700 threshold, FOIR, minimum/maximum limits, or documents."
        )

    return (
        "*(Local Fallback Active — Gemini AI unavailable)* I can reliably assist you with:\n\n"
        "• Verifying your Customer ID (e.g. `cust01`)\n"
        "• Registering as a new customer (`I am a new customer`)\n"
        "• Explaining CIBIL (≥700), FOIR (≤50%), age (21–65), and EMI calculations (`Calculate EMI for ₹5,00,000`)."
    )


# ── Local Fallback Agent & Conversational State Machine ──

def local_master_agent(session_id, text):
    """
    Deterministic business & onboarding supervisor:
    - Strictly validates every onboarding field without fabricated defaults
    - Never marks registration complete when any mandatory field fails validation
    - Answers structured queries (KYC, Profile, EMI, Docs, Criteria, Explicit Loan Application)
    - Uses safe_local_informational_fallback() only when Gemini is unavailable/errors, without mutating state
    """
    t = text.lower().strip()
    restore_session_state(session_id)
    sess = session_data.setdefault(session_id, {})
    onboarding_state = sess.get("onboarding_state")

    # ── 1. ACTIVE IN-CHAT ONBOARDING STATE MACHINE ──
    if onboarding_state:
        if is_onboarding_cancel_command(text):
            sess["onboarding_state"] = None
            sess["onboarding_data"] = {}
            return (
                "❌ **Registration Cancelled.**\n\n"
                "No problem! Whenever you're ready, you can type **'I am a new customer'** to start again, "
                "or provide an existing Customer ID (e.g. `cust01`)."
            )

        # Safeguard: if local_master_agent receives a general question during onboarding, answer safely & preserve state
        if is_general_question(text):
            faq_answer = safe_local_informational_fallback(session_id, text)
            return append_onboarding_reminder(faq_answer, onboarding_state)

        data = sess.setdefault("onboarding_data", {})

        if onboarding_state == "ASK_NAME":
            name = text.strip()
            if (
                len(name) < 2
                or re.match(r"^\d+$", name)
                or name.lower() in {"hi", "hello", "hey", "help", "ok", "yes", "no"}
            ):
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
            elif "pending_age" in data and not re.search(r"\d+", text):
                age = data["pending_age"]
            else:
                age_m = re.search(r"\b(\d{1,3})\b", text)
                age = int(age_m.group(1)) if age_m else None

            if age is None:
                return (
                    "Please provide your **Age** (21–65 years) and **City** of residence "
                    "(e.g., *28, Mumbai*), or type `'cancel'` to exit."
                )

            if age < 21:
                data.pop("pending_age", None)
                return (
                    f"❌ **Eligibility Check Failed (Age)**: Minimum eligible age is **21 years** (maximum 65 years). "
                    f"At {age} years, you do not meet our mandatory age requirement.\n\n"
                    f"*Please enter an eligible age between 21 and 65 with your city to continue, or type `'cancel'` to exit.*"
                )
            if age > 65:
                data.pop("pending_age", None)
                return (
                    f"❌ **Eligibility Check Failed (Age)**: Maximum eligible age is **65 years**. "
                    f"At {age} years, you exceed our maximum age limit.\n\n"
                    f"*Please enter an eligible age between 21 and 65 with your city to continue, or type `'cancel'` to exit.*"
                )

            city_cand = re.sub(r"\b(?:years?|yrs?|old|age)\b", " ", text, flags=re.IGNORECASE)
            city_cand = re.sub(r"[\d,./-]", " ", city_cand).strip()
            city = " ".join([w.capitalize() for w in city_cand.split() if len(w) > 1])

            if not city:
                data["pending_age"] = age
                return (
                    f"Age **{age} yrs** noted. Please also enter your **City** of residence "
                    "(e.g., *Mumbai* or *Delhi*) — we do not auto-fill missing city fields."
                )

            data.pop("pending_age", None)
            data["age"] = age
            data["city"] = city
            sess["onboarding_state"] = "ASK_PAN"
            return (
                f"Great ({age} yrs, {city}). Now, please enter your **PAN Card Number**\n"
                f"*(10-character alphanumeric, e.g. `ABCDE1234F`)*:"
            )

        if onboarding_state == "ASK_PAN":
            pan_clean = re.sub(r"[^A-Za-z0-9]", "", text).upper()
            if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", pan_clean):
                return "Please enter a valid **10-character PAN Number** in format `ABCDE1234F` (5 letters, 4 digits, 1 letter)."
            data["pannumber"] = pan_clean
            sess["onboarding_state"] = "ASK_SALARY"
            return (
                "Almost done! What is your **Monthly In-Hand Salary** in ₹?\n"
                "*(e.g., 50000 or 80000 — this determines your pre-approved loan limit)*"
            )

        if onboarding_state == "ASK_SALARY":
            amt = parse_strict_numeric_value(text)
            if not amt or amt < 5000:
                return "Please enter a valid monthly net salary figure in numbers (minimum ₹5,000, e.g. *50000* or *75000*)."
            data["salary"] = int(amt)
            sess["onboarding_state"] = "ASK_EXISTING_LOAN"
            return (
                "Do you have any **Current Ongoing Monthly Loan EMIs**?\n"
                "*(Enter the monthly EMI amount e.g. `5000`, or reply `0` / `none` if no active loans)*"
            )

        if onboarding_state == "ASK_EXISTING_LOAN":
            if re.search(r"^\s*0+\s*$", t) or re.search(r"\b(?:no|none|nil|zero|n/?a)\b", t):
                curr_loan = 0
            else:
                amt = parse_strict_numeric_value(text)
                if amt is None:
                    return (
                        "Please enter a valid numeric monthly EMI obligation (e.g. `5000`), "
                        "or reply `0` / `none` if you have no existing loans."
                    )
                curr_loan = int(amt)

            salary = data.get("salary", 0)
            if salary > 0 and (curr_loan / salary) > 0.50:
                foir_pct = (curr_loan / salary) * 100
                return (
                    f"❌ **Eligibility Check Failed (FOIR Limit)**: Existing monthly EMIs of ₹{int(curr_loan):,} account for "
                    f"{foir_pct:.1f}% of your monthly salary (₹{int(salary):,}), which exceeds the mandatory 50% FOIR limit.\n\n"
                    f"*Please enter a valid monthly EMI obligation (under ₹{int(salary * 0.5):,}, or `0` if none), or type `'cancel'` to exit.*"
                )

            data["current_loan"] = curr_loan
            sess["onboarding_state"] = "ASK_CREDIT_SCORE"
            return (
                "Lastly, what is your **CIBIL / Credit Score**?\n"
                "*(e.g., `750` or `800`. Valid eligible range in this system: **700–900**)*"
            )

        if onboarding_state == "ASK_CREDIT_SCORE":
            credit, parse_status = extract_explicit_cibil_input(text)

            if parse_status == "question":
                return append_onboarding_reminder(
                    safe_local_informational_fallback(session_id, text),
                    onboarding_state,
                )

            if parse_status == "skip_not_allowed" or credit is None:
                return (
                    "A valid **CIBIL credit score** between **700 and 900** is strictly required and cannot be skipped or defaulted.\n\n"
                    "*Please enter your numeric CIBIL score (e.g. `750`), or type `'cancel'` to exit.*"
                )

            if credit < 700:
                data.pop("credit_score", None)
                return (
                    f"❌ **Eligibility Check Failed (CIBIL Score)**: Minimum required CIBIL credit score is **700**. "
                    f"The score you entered (**{credit}**) does not meet our mandatory approval threshold.\n\n"
                    f"*Please provide an eligible score between **700 and 900** to continue, or type `'cancel'` to exit.*"
                )

            if credit > 900:
                data.pop("credit_score", None)
                return (
                    f"❌ **Invalid CIBIL Score**: CIBIL scores range up to **900**. "
                    f"The score you entered (**{credit}**) exceeds 900.\n\n"
                    f"*Please provide a valid CIBIL score between **700 and 900**, or type `'cancel'` to exit.*"
                )

            # Store exact validated score (never substituted or defaulted)
            data["credit_score"] = credit

            # ── STRICT PRE-FINALIZATION COMPLETENESS VERIFICATION ──
            required_checks = [
                ("name", isinstance(data.get("name"), str) and len(data["name"].strip()) >= 2),
                ("phone", isinstance(data.get("phone"), str) and data["phone"].isdigit() and len(data["phone"]) == 10),
                ("email", isinstance(data.get("email"), str) and "@" in data["email"]),
                ("age", isinstance(data.get("age"), int) and 21 <= data["age"] <= 65),
                ("city", isinstance(data.get("city"), str) and len(data["city"].strip()) >= 2),
                ("pannumber", isinstance(data.get("pannumber"), str) and len(data["pannumber"]) == 10),
                ("salary", isinstance(data.get("salary"), (int, float)) and data["salary"] >= 5000),
                ("current_loan", isinstance(data.get("current_loan"), (int, float)) and data["current_loan"] >= 0),
                ("credit_score", isinstance(data.get("credit_score"), int) and 700 <= data["credit_score"] <= 900),
            ]
            missing_or_invalid = [field for field, ok in required_checks if not ok]
            if missing_or_invalid:
                return (
                    f"⚠️ Cannot complete registration because required field(s) are incomplete or invalid: "
                    f"**{', '.join(missing_or_invalid)}**. Please type `'cancel'` to restart onboarding cleanly."
                )

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

            # Immediately link verified profile to active session
            new_customer["verified"] = True
            new_customer["verified_at"] = datetime.now(timezone.utc).isoformat()
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
    if is_onboarding_trigger_phrase(text):
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

    # ── 3. CUSTOMER ID VERIFICATION TRIGGER (custXXXX, excluding English 'customer') ──
    cust_match = CUSTOMER_ID_REGEX.search(t)
    if cust_match:
        mentioned_cid = cust_match.group(0).lower()
        verified_cust, _ = get_verified_customer_context(session_id, refresh_from_firebase=False)
        if verified_cust and verified_cust.get("customer_id", "").lower() != mentioned_cid:
            return (
                f"You are currently verified as **{verified_cust.get('name')}** (`{verified_cust.get('customer_id')}`). "
                f"For security, mentioning another Customer ID (`{mentioned_cid}`) in conversation cannot switch accounts or expose their details.\n\n"
                "Please type **'logout'** first if you want to end this session and verify a different customer."
            )
        if not is_general_question(text):
            return "[[FLASK_CALL:VERIFY_KYC]]"
        return (
            f"For security and privacy, you must verify KYC for **`{mentioned_cid}`** before accessing account details. "
            f"Enter `{mentioned_cid}` directly to verify."
        )

    # ── 4. LOGOUT / SWITCH CUSTOMER ──
    if is_logout_phrase(text):
        clear_persisted_session_state(session_id)
        session_histories[session_id] = [SystemMessage(content=LLM_SYSTEM_PROMPT)]
        return (
            "✅ **Logged out successfully.** Your verified customer context has been cleared.\n\n"
            "You can now:\n"
            "1. Enter an existing Customer ID (e.g. `cust01`, `cust10`)\n"
            "2. Type **'I am a new customer'** to register a new profile."
        )

    # ── 5. CHECK PROFILE / LIMIT / WHO AM I ──
    if is_profile_lookup_query(text):
        verified_cust, assessment = get_verified_customer_context(session_id, refresh_from_firebase=True)
        if verified_cust and assessment:
            name = verified_cust.get("name", "Customer")
            cid = verified_cust.get("customer_id")
            salary = int(assessment["salary"])
            credit = assessment["credit_score"]
            limit = int(assessment["preliminary_limit"])
            email = verified_cust.get("email", "Not provided")
            tenure = assessment["recommended_tenure"]
            status_badge_val = "Preliminary Eligible" if assessment["eligible_for_final"] else "Not Eligible for Final Approval"
            blocking_note = (
                ""
                if assessment["eligible_for_final"]
                else "\n• **Eligibility Note**: " + " ".join(assessment["failed_criteria"])
            )
            next_step = (
                f"Ready to apply? Simply enter the loan amount you wish to apply for (e.g. **₹{int(limit * 0.5):,}**)."
                if assessment["eligible_for_final"]
                else f"A salary-based preliminary limit of ₹{limit:,} does **not** grant final approval until the failed criteria above are satisfied."
            )
            return (
                f"👤 **Your Verified Account Profile Details:**\n\n"
                f"• **Name**: **{name}**\n"
                f"• **Customer ID**: `{cid}`\n"
                f"• **Monthly Salary**: ₹{salary:,}\n"
                f"• **Credit Score**: {credit}\n"
                f"• **Salary-Based Preliminary Limit (15×)**: Up to **₹{limit:,}**\n"
                f"• **Eligibility Status**: `{status_badge_val}`{blocking_note}\n"
                f"• **Estimated Tenure**: {tenure} months @ 12% p.a.\n"
                f"• **Registered Email**: `{email}`\n\n"
                f"ℹ️ *Salary-based preliminary limits are initial estimates only. Final approval requires passing CIBIL (≥700), Age (21–65), and FOIR (≤50%) underwriting checks.*\n\n"
                f"{next_step}"
            )
        return (
            "You haven't verified a customer profile in this session yet.\n\n"
            "• If you have an ID, enter it (e.g. `cust01` or `cust99`).\n"
            "• If you are new, type **'I am a new customer'** to register and check your limit!"
        )

    # ── 6. LOAN APPLICATION INTENT ──
    if (not is_general_question(text)) and any(phrase in t for phrase in [
        "apply for a loan", "apply for loan", "apply loan", "want a loan", "want loan",
        "need a loan", "need loan", "take a loan", "take loan", "get a loan", "get loan",
        "i want to apply", "loan application", "how to apply"
    ]):
        detected_amt, _, amt_status = extract_explicit_loan_request(text)

        if sess.get("customer_id"):
            name = sess.get("name", "Customer")
            limit = sess.get("pre_approved_limit") or sess.get("salary", 0) * 15
            if amt_status == "valid" and detected_amt:
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
            if amt_status == "valid" and detected_amt:
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
    if is_emi_calculation_query(text):
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
    if is_structured_faq_query(text):
        if any(w in t for w in ["document", "documents", "docs", "paperwork"]):
            return (
                "📄 **Documents Required for Loan Approval:**\n\n"
                "1. **Identity Proof**: PAN Card (mandatory) & Aadhaar Card / Passport.\n"
                "2. **Address Proof**: Aadhaar Card, Utility Bill, or Rental Agreement.\n"
                "3. **Income Proof**: Last 3 months Salary Slips & Form 16 / ITR.\n"
                "4. **Bank Statement**: Last 6 months bank statement showing regular salary deposits.\n\n"
                "✨ *With our instant automated pipeline, verified customers receive a digital sanction letter within seconds without physical paperwork!*"
            )

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
    if sess.get("sanction") and not is_general_question(text):
        if any(word in t for word in ["sanction", "letter", "email", "pdf", "status"]):
            s = sess["sanction"]
            return f"✅ Your loan sanction letter (`{s.get('pdf', 'Sanction_Letter.pdf')}`) has been issued and sent to **{s.get('email', 'your email')}**."

    # ── 10. EXPLICIT LOAN AMOUNT UNDERWRITE TRIGGER ──
    if sess.get("customer_id"):
        amt, _, amt_status = extract_explicit_loan_request(text)
        if amt_status == "valid" and amt and amt > 0:
            return "[[FLASK_CALL:UNDERWRITE]]"
        if amt_status == "ambiguous_amount":
            return (
                "That number looks ambiguous without loan context. "
                "Please specify the exact loan amount you want to apply for (e.g., `50000`, `₹5,00,000`, or `I want a loan of ₹3,00,000`)."
            )

    # ── 11. SAFE INFORMATIONAL & GENERAL FALLBACK ──
    return safe_local_informational_fallback(session_id, text)


# ── Flask Routes ──

@app.route("/chat", methods=["POST"])
def chat():
    start_ts = time.perf_counter()
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    user_input = data.get("user_input", "").strip()
    request_id = data.get("request_id") or None

    if not user_input:
        return jsonify({
            "response_text": "Please type a message.",
            "orchestration_command": None,
            "monitoring": monitoring_store.get_snapshot(session_id),
        })

    if not session_id:
        session_id = f"sess_{int(time.time())}"

    save_message_to_firebase(session_id, "user", user_input)

    hist = get_session_history(session_id)
    hist.append(HumanMessage(content=user_input))

    restore_session_state(session_id)
    sess = session_data.setdefault(session_id, {})
    onboarding_state = sess.get("onboarding_state")
    t_lower = user_input.lower().strip()

    verified_cust, verified_assessment = get_verified_customer_context(session_id, refresh_from_firebase=True)

    is_question = is_general_question(user_input)
    is_cancel = bool(onboarding_state and is_onboarding_cancel_command(user_input))
    is_onboarding_trigger = (not onboarding_state) and is_onboarding_trigger_phrase(user_input)
    is_logout = is_logout_phrase(user_input)
    is_profile_query = is_profile_lookup_query(user_input)
    is_emi_query = is_emi_calculation_query(user_input)
    is_dashboard_request = (not onboarding_state) and any(p in t_lower for p in [
        "view my eligibility dashboard", "open eligibility dashboard", "show eligibility dashboard",
        "show my eligibility dashboard", "open my eligibility dashboard", "eligibility dashboard"
    ])

    # Keep personal verified-customer follow-ups conversational (Gemini + context-aware fallback)
    is_personal_followup = bool(
        verified_cust
        and (not onboarding_state)
        and re.search(r"\b(?:i|my|me|am i|do i|can i)\b", t_lower)
        and not is_profile_query
        and not is_emi_query
    )
    is_structured_faq = is_structured_faq_query(user_input) and (not is_personal_followup)
    is_apply_intent = (not onboarding_state) and (not is_question) and any(p in t_lower for p in [
        "apply for a loan", "apply for loan", "apply loan", "want a loan", "want loan",
        "need a loan", "need loan", "take a loan", "take loan", "get a loan", "get loan",
        "i want to apply", "loan application", "how to apply"
    ])

    cust_id_match = CUSTOMER_ID_REGEX.search(t_lower) if (not onboarding_state) else None
    is_cross_customer_attempt = bool(
        cust_id_match
        and (
            (verified_cust and cust_id_match.group(0).lower() != verified_cust.get("customer_id", "").lower())
            or ((not verified_cust) and is_question)
        )
    )
    is_cust_id = bool(cust_id_match) and (not is_question) and (not is_cross_customer_attempt)

    extracted_loan_amount = None
    extracted_tenure = None
    loan_parse_status = "no_amount"
    is_verified_and_amount = False

    if (not onboarding_state) and sess.get("customer_id") and (not is_question):
        extracted_loan_amount, extracted_tenure, loan_parse_status = extract_explicit_loan_request(user_input)
        is_verified_and_amount = (loan_parse_status == "valid")

    is_onboarding_field_reply = bool(onboarding_state) and (not is_question) and (not is_structured_faq) and (not is_emi_query)
    is_structured_query = is_profile_query or is_emi_query or is_structured_faq

    # Decide strictly: deterministic Python rules vs conversational Gemini AI
    should_use_local_rules = (
        is_cancel
        or is_onboarding_field_reply
        or is_onboarding_trigger
        or is_logout
        or is_dashboard_request
        or is_profile_query
        or is_emi_query
        or is_structured_faq
        or is_apply_intent
        or is_cross_customer_attempt
        or is_cust_id
        or is_verified_and_amount
        or (loan_parse_status == "ambiguous_amount")
    )

    intent_category = classify_intent_category(user_input, {
        "is_onboarding_active": bool(onboarding_state),
        "is_onboarding_trigger": is_onboarding_trigger,
        "is_logout": is_logout,
        "is_structured_query": is_structured_query,
        "is_cust_id": is_cust_id,
        "is_verified_and_amount": is_verified_and_amount,
    })

    # Telemetry accumulators for this turn
    engine_category = "local_rules"
    model_used = "local_master_agent"
    token_usage = None
    gemini_attempts = 0
    gemini_successes = 0
    gemini_failures = 0
    fallback_reason = None

    raw_llm_model = getattr(llm, "model", None) if llm is not None else None
    resolved_primary = raw_llm_model.replace("models/", "") if isinstance(raw_llm_model, str) and raw_llm_model else ACTIVE_MODEL_NAME

    monitoring_store.update_runtime_config(
        firebase_db_url=FIREBASE_DB_URL,
        firebase_api_key=FIREBASE_API_KEY,
        active_model=resolved_primary,
        llm_available=(llm is not None),
        init_error=LLM_INIT_ERROR,
    )

    if is_dashboard_request:
        if verified_cust:
            text = (
                f"Opening your **Loan Eligibility Dashboard** for **{verified_cust.get('name', 'Customer')}** "
                f"(`{verified_cust.get('customer_id')}`)."
            )
        else:
            text = (
                "Please complete **KYC verification** first by entering your Customer ID "
                "(e.g., `cust01` or `cust99`) or typing `'I am a new customer'` before opening your personal dashboard."
            )
        engine_category = "local_rules"
        model_used = "local_master_agent"
    elif should_use_local_rules:
        text = local_master_agent(session_id, user_input)
        # If an FAQ/EMI interrupted onboarding, remind the pending step cleanly while preserving state
        if onboarding_state and (is_structured_faq or is_emi_query) and sess.get("onboarding_state"):
            text = append_onboarding_reminder(text, sess["onboarding_state"])
        if not is_logout:
            persist_session_state(session_id)
        engine_category = "local_rules"
        model_used = "local_master_agent"
    elif not llm:
        base_reply = safe_local_informational_fallback(session_id, user_input)
        if onboarding_state and sess.get("onboarding_state"):
            base_reply = append_onboarding_reminder(base_reply, sess["onboarding_state"])
        text = base_reply
        engine_category = "local_error_fallback"
        model_used = "local_master_agent"
        fallback_reason = LLM_INIT_ERROR or "Gemini API unavailable / not configured"
    else:
        # Prepare Gemini message list; merge non-PII pending step & session-verified customer context into index-0 SystemMessage
        # (langchain-google-genai only allows SystemMessage at position 0, never mid-conversation)
        llm_messages = list(hist)
        base_sys = llm_messages[0].content if llm_messages and isinstance(llm_messages[0], SystemMessage) else LLM_SYSTEM_PROMPT
        extra_context_parts = []
        if onboarding_state:
            step_desc = ONBOARDING_CONTEXT_HINTS.get(onboarding_state, onboarding_state)
            extra_context_parts.append(
                f"\n\nCURRENT SESSION CONTEXT (mid-registration interruption): "
                f"The user paused onboarding at step '{onboarding_state}' ({step_desc}). "
                "Answer their informational question concisely and accurately, do NOT complete or reset registration, "
                "do NOT invent field values, and do NOT emit any [[FLASK_CALL:...]] tokens."
            )
        if verified_cust and verified_assessment and not onboarding_state:
            extra_context_parts.append(build_minimal_verified_context_prompt(verified_cust, verified_assessment))

        if extra_context_parts:
            merged_sys = SystemMessage(content=f"{base_sys}{''.join(extra_context_parts)}")
            if llm_messages and isinstance(llm_messages[0], SystemMessage):
                llm_messages = [merged_sys] + llm_messages[1:]
            else:
                llm_messages = [merged_sys] + llm_messages

        try:
            gemini_attempts += 1
            res = llm.invoke(llm_messages)
            raw_reply = getattr(res, "content", "")
            if isinstance(raw_reply, (list, dict)):
                raw_reply = str(raw_reply)
            # Never allow Gemini to inject [[FLASK_CALL:...]] commands autonomously
            text = sanitize_llm_reply(raw_reply)
            gemini_successes += 1
            token_usage = extract_gemini_token_usage(res)
            engine_category = "gemini_primary"
            model_used = resolved_primary
        except Exception as e:
            gemini_failures += 1
            err_msg = str(e)
            print(f"[WARNING] Primary LLM ({resolved_primary}) error: {err_msg}.")
            fallback_res = None

            if resolved_primary != SECONDARY_MODEL_NAME and ChatGoogleGenerativeAI and API_KEY:
                try:
                    gemini_attempts += 1
                    fallback_llm = ChatGoogleGenerativeAI(
                        model=SECONDARY_MODEL_NAME,
                        google_api_key=API_KEY,
                        temperature=MODEL_TEMP,
                        safety_settings=None,
                        timeout=10
                    )
                    res2 = fallback_llm.invoke(llm_messages)
                    raw_fallback = getattr(res2, "content", "")
                    if isinstance(raw_fallback, (list, dict)):
                        raw_fallback = str(raw_fallback)
                    fallback_res = sanitize_llm_reply(raw_fallback)
                    gemini_successes += 1
                    token_usage = extract_gemini_token_usage(res2)
                    engine_category = "gemini_secondary"
                    model_used = SECONDARY_MODEL_NAME
                    fallback_reason = err_msg
                    print(f"[INFO] Fallback to {SECONDARY_MODEL_NAME} succeeded.")
                except Exception as e2:
                    gemini_failures += 1
                    err_msg = str(e2) or err_msg
                    print(f"[WARNING] Fallback LLM error: {e2}.")

            if fallback_res is not None:
                text = fallback_res
            else:
                print("[INFO] Falling back to safe local informational fallback.")
                text = safe_local_informational_fallback(session_id, user_input)
                engine_category = "local_error_fallback"
                model_used = "local_master_agent"
                fallback_reason = err_msg

        # After any Gemini or fallback answer during onboarding, remind pending step cleanly without changing state
        if onboarding_state and sess.get("onboarding_state"):
            text = append_onboarding_reminder(text, sess["onboarding_state"])

    latency_ms = (time.perf_counter() - start_ts) * 1000.0
    monitoring_store.record_event(
        session_id=session_id,
        engine_category=engine_category,
        latency_ms=latency_ms,
        request_id=request_id,
        intent_category=intent_category,
        model_used=model_used,
        token_usage=token_usage,
        gemini_attempts=gemini_attempts,
        gemini_failures=gemini_failures,
        gemini_successes=gemini_successes,
        fallback_reason=fallback_reason,
    )

    hist.append(AIMessage(content=text))
    save_message_to_firebase(session_id, "bot", text)

    # Only local rule engine commands are emitted as orchestration_command
    m = re.search(r"\[\[FLASK_CALL:([A-Z_]+)\]\]", text)
    cmd = f"[[FLASK_CALL:{m.group(1)}]]" if m else None
    snapshot = monitoring_store.get_snapshot(session_id)

    if cmd:
        payload = {
            "response_text": "Processing request...",
            "orchestration_command": cmd,
            "monitoring": snapshot,
        }
        if cmd == "[[FLASK_CALL:UNDERWRITE]]" and extracted_loan_amount:
            payload["loan_amount"] = extracted_loan_amount
            if extracted_tenure:
                payload["tenure"] = extracted_tenure
        return jsonify(payload)

    return jsonify({
        "response_text": text,
        "orchestration_command": None,
        "open_eligibility_dashboard": bool(is_dashboard_request),
        "monitoring": snapshot,
    })


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

        # Prevent silent session hijacking if session is already verified under a different Customer ID
        existing_verified, _ = get_verified_customer_context(session_id, refresh_from_firebase=False)
        if existing_verified and existing_verified.get("customer_id", "").lower() != cid:
            return jsonify({
                "status": "error",
                "message": (
                    f"Session is already verified for {existing_verified.get('customer_id')}. "
                    "Please log out before verifying a different Customer ID."
                ),
                "next_step": "LOGOUT_REQUIRED",
            })

        c = verify_kyc(cid)
        if c.get("status") == "Verification Successful":
            c["verified"] = True
            c["verified_at"] = datetime.now(timezone.utc).isoformat()
            assessment = evaluate_customer_profile_eligibility(c)
            c["profile_assessment"] = assessment
            session_data[session_id] = c.copy()
            persist_session_state(session_id)
            save_session_meta(session_id, {"customer_name": c["name"], "email": c.get("email")})

            # Record concise verification summary in conversation history for continuity
            hist = get_session_history(session_id)
            hist.append(AIMessage(
                content=(
                    f"KYC Verification Successful for {c.get('name')} ({cid}). "
                    f"Salary: ₹{int(assessment['salary']):,}, CIBIL Score: {assessment['credit_score']}, "
                    f"Salary-Based Preliminary Limit: ₹{int(assessment['preliminary_limit']):,}, "
                    f"Status: {assessment['application_status']}."
                )
            ))
            return jsonify({
                "status": "success",
                "customer_data": c,
                "next_step": "ASK_LOAN_AMOUNT" if assessment["eligible_for_final"] else "INELIGIBLE_CIBIL_OR_PROFILE",
            })
        return jsonify({"status": "error", "message": c.get("message", "Verification failed"), "next_step": "AWAITING_KYC"})

    if step == "UNDERWRITE":
        restore_session_state(session_id)
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

        # Record requested loan details on active verified session only (never mutates customer DB record)
        try:
            clean_req_amt = parse_loan_amount_text(amt_raw)
        except Exception:
            clean_req_amt = None
        if clean_req_amt and clean_req_amt > 0:
            c["last_requested_amount"] = clean_req_amt
        c["last_requested_tenure"] = result.get("tenure_months") or parsed_tenure
        c["last_underwriting_result"] = {
            "status": result.get("status"),
            "emi": result.get("emi"),
            "foir": result.get("foir"),
            "failed_conditions": result.get("failed_conditions", []),
        }
        c["profile_assessment"] = evaluate_customer_profile_eligibility(c)

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
            elif fpdf_path:
                email_message = f"⚠️ PDF generated but email could not be sent ({email_err}). PDF saved locally."
            else:
                email_message = f"⚠️ Loan approved, but PDF generation failed ({email_err})."

            persist_session_state(session_id)

            return jsonify({
                "status": "complete",
                "worker_message": result["message"],
                "email_message": email_message,
                "emi": result.get("emi"),
                "tenure_months": result.get("tenure_months"),
                "pdf_file": os.path.basename(fpdf_path) if fpdf_path else None
            })

        persist_session_state(session_id)
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
    clear_persisted_session_state(session_id)
    return jsonify({"session_id": session_id})


@app.route("/")
def index():
    return render_template("chat.html")


@app.route("/sanctions/<path:filename>")
def download_sanction_pdf(filename):
    """Serve generated sanction letter PDF from writable sanctions directory."""
    safe_name = os.path.basename(filename)
    return send_from_directory(SANCTIONS_DIR, safe_name, as_attachment=False)


@app.route("/admin", methods=["GET"])
def admin_panel():
    """Serve Customer Onboarding & Admin Panel directly under the main app (Vercel-compatible)."""
    return render_template("form.html", chatbot_url="/", chatbot_label="Open Chatbot")


@app.route("/add-customer", methods=["POST"])
def admin_add_customer():
    """Validate and save a new customer directly from the integrated Admin Panel."""
    from form_app import validate_customer_eligibility

    name = request.form.get("customerName", "").strip()
    phone = request.form.get("phoneNumber", "").strip()
    dob = request.form.get("dob", "").strip()
    age = request.form.get("age", "").strip()
    city = request.form.get("city", "").strip()
    pan = request.form.get("panNumber", "").strip().upper()
    email = request.form.get("emailAddress", "").strip()
    salary = request.form.get("salary", "").strip()
    currentloan = request.form.get("currentLoan", "0").strip()
    credit = request.form.get("creditScore", "").strip()

    errors, final_age = validate_customer_eligibility(
        name=name,
        phone=phone,
        age=age,
        salary=salary,
        credit=credit,
        currentloan=currentloan,
        dob=dob,
    )
    if errors:
        return render_template(
            "form.html",
            error="<br>• " + "<br>• ".join(errors),
            chatbot_url="/",
            chatbot_label="Open Chatbot",
        )

    customer_id = f"cust{phone}"
    salary_int = int(float(salary))
    credit_int = int(credit)
    currentloan_int = int(float(currentloan)) if currentloan else 0
    new_customer = {
        "customer_id": customer_id,
        "name": name,
        "phone": phone,
        "email": email,
        "dob": dob,
        "age": final_age,
        "city": city,
        "pannumber": pan,
        "salary": salary_int,
        "credit_score": credit_int,
        "pre_approved_limit": salary_int * 15,
        "current_loan_status": str(currentloan_int),
    }
    save_res = save_customer_to_storage(new_customer)
    firebase_saved = bool(save_res.get("firebase_saved"))
    firebase_error = save_res.get("firebase_error") or (
        "" if firebase_saved else "Firebase not configured. Saved to browser session & runtime store."
    )
    return render_template(
        "form.html",
        success=True,
        customer_id=customer_id,
        firebase_saved=firebase_saved,
        firebase_error=firebase_error,
        chatbot_url="/",
        chatbot_label="Open Chatbot",
    )


@app.route("/api/eligibility-dashboard", methods=["GET"])
def api_eligibility_dashboard():
    """Return verified customer Loan Eligibility Dashboard payload from authoritative Python rules."""
    session_id = request.args.get("session_id")
    payload = build_eligibility_dashboard_payload(session_id, refresh_from_firebase=True)
    return jsonify(payload)


@app.route("/api/eligibility-simulate", methods=["POST"])
def api_eligibility_simulate():
    """Read-only EMI & FOIR simulator backed by Python calculate_emi()."""
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    loan_amount = data.get("loan_amount")
    tenure_months = data.get("tenure_months")
    interest_rate = data.get("interest_rate")
    payload, status_code = simulate_loan_for_verified_customer(
        session_id=session_id,
        loan_amount=loan_amount,
        tenure_months=tenure_months,
        interest_rate=interest_rate,
    )
    return jsonify(payload), status_code


@app.route("/api/monitoring")
def api_monitoring():
    """Return real-time AI engine status, exact token counts, and engine distribution."""
    session_id = request.args.get("session_id")
    raw_llm_model = getattr(llm, "model", None) if llm is not None else None
    resolved_primary = raw_llm_model.replace("models/", "") if isinstance(raw_llm_model, str) and raw_llm_model else ACTIVE_MODEL_NAME
    monitoring_store.update_runtime_config(
        firebase_db_url=FIREBASE_DB_URL,
        firebase_api_key=FIREBASE_API_KEY,
        active_model=resolved_primary,
        llm_available=(llm is not None),
        init_error=LLM_INIT_ERROR,
    )
    return jsonify(monitoring_store.get_snapshot(session_id))


@app.route("/health")
def health():
    """Health check endpoint – useful for debugging."""
    snapshot = monitoring_store.get_snapshot()
    return jsonify({
        "status": "ok",
        "llm_ready": llm is not None,
        "active_model": snapshot["engine_status"]["active_model"],
        "gemini_status": snapshot["engine_status"]["gemini_status"],
        "local_fallback_status": snapshot["engine_status"]["local_fallback_status"],
        "persistence_mode": snapshot["engine_status"]["persistence_mode"],
        "firebase_configured": bool(FIREBASE_DB_URL),
        "email_configured": bool(GMAIL_USER and GMAIL_APP_PASSWORD),
        "serverless_mode": IS_SERVERLESS,
        "writable_data_dir": WRITABLE_DATA_DIR,
        "dummy_customers": list(DUMMY_CUSTOMERS.keys())
    })


if __name__ == "__main__":
    app.run(port=5000, debug=True)
