import os
import json
import re
import requests
import warnings
from datetime import datetime, date

# Suppress cosmetic dependency mismatch warning for clean terminal logs
warnings.filterwarnings("ignore", message=r".*urllib3.*or chardet.*doesn't match a supported version!.*")

from flask import Flask, request, render_template, jsonify
from flask_cors import CORS

app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app)

# ── Load config.json (graceful fallback) ──
CONFIG_PATH = "config.json"
config = {}
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH) as f:
            config = json.load(f)
    except Exception as e:
        print(f"[WARNING] Could not read {CONFIG_PATH}: {e}")
else:
    print("[WARNING] config.json not found. Firebase saving will be disabled.")

FIREBASE_DB_URL = os.environ.get("FIREBASE_DATABASE_URL", config.get("firebase_database_url", "")).rstrip("/")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", config.get("firebase_api_key", ""))


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


def validate_customer_eligibility(name, phone, age, salary, credit, currentloan=0, dob=None):
    """
    Strict backend eligibility validation:
    - Age: Minimum 21 years and maximum 65 years (calculated from DOB if provided)
    - CIBIL Score: Minimum 700 (max 900)
    - Salary: Positive net monthly figure (> 0)
    - FOIR: Existing loan obligations cannot exceed 50% of monthly net salary
    Returns (list_of_errors, final_age)
    """
    errors = []

    # 1. Basic format validations
    if not name or len(name.strip()) < 2:
        errors.append("Customer name is required (minimum 2 characters).")
    if not phone or not phone.isdigit() or len(phone) != 10:
        errors.append("Valid 10-digit mobile number is required.")

    # 2. Date of birth / Age validation (21 to 65)
    calculated_age = None
    if dob:
        calculated_age = calculate_age_from_dob(dob)

    if calculated_age is not None:
        age_val = calculated_age
    else:
        try:
            age_val = int(age)
        except (ValueError, TypeError):
            age_val = 0
            errors.append("Valid age (number between 21 and 65) is required.")

    if age_val < 21:
        errors.append(f"Age Validation Failed: Applicant age ({age_val} years) is below the minimum required age of 21 years.")
    elif age_val > 65:
        errors.append(f"Age Validation Failed: Applicant age ({age_val} years) exceeds the maximum allowed age of 65 years.")

    # 3. CIBIL Score (>= 700)
    try:
        credit_val = int(credit)
        if credit_val < 700:
            errors.append(f"CIBIL Score Validation Failed: Credit score ({credit_val}) is below the minimum required threshold of 700.")
        elif credit_val > 900:
            errors.append(f"CIBIL Score Validation Failed: Credit score ({credit_val}) cannot exceed 900.")
    except (ValueError, TypeError):
        credit_val = 0
        errors.append("Valid CIBIL credit score (number between 700 and 900) is required.")

    # 4. Salary (> 0)
    try:
        salary_val = float(salary)
        if salary_val <= 0:
            errors.append("Monthly net salary must be greater than zero.")
    except (ValueError, TypeError):
        salary_val = 0.0
        errors.append("Valid monthly net salary is required.")

    # 5. Existing Loan / FOIR obligation (cannot exceed 50% of monthly salary)
    try:
        curr_loan_val = float(currentloan) if currentloan else 0.0
        if curr_loan_val < 0:
            errors.append("Current loan EMI cannot be negative.")
        elif salary_val > 0:
            foir_pct = (curr_loan_val / salary_val) * 100
            if foir_pct > 50.0:
                errors.append(
                    f"FOIR Validation Failed: Existing monthly EMIs (₹{int(curr_loan_val):,}) account for "
                    f"{foir_pct:.1f}% of salary, which exceeds the maximum allowed 50% FOIR limit."
                )
    except (ValueError, TypeError):
        errors.append("Current loan must be a valid number.")

    return errors, age_val


@app.route("/")
def form():
    return render_template("form.html", chatbot_url="http://localhost:5000", chatbot_label="Open Chatbot :5000")


@app.route("/add-customer", methods=["POST"])
def add_customer():
    # Read form fields
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

    # Strict backend eligibility validation
    errors, final_age = validate_customer_eligibility(
        name=name,
        phone=phone,
        age=age,
        salary=salary,
        credit=credit,
        currentloan=currentloan,
        dob=dob
    )

    if errors:
        return render_template(
            "form.html",
            error="<br>• " + "<br>• ".join(errors),
            chatbot_url="http://localhost:5000",
            chatbot_label="Open Chatbot :5000",
        )

    customer_id = f"cust{phone}"
    salary_int = int(float(salary))
    credit_int = int(credit)
    currentloan_int = int(float(currentloan)) if currentloan else 0

    data = {
        "kyc": {
            "name": name,
            "phone": phone,
            "email": email,
            "dob": dob,
            "age": final_age,
            "city": city,
            "pannumber": pan,
            "currentloan": currentloan_int
        },
        "salary": salary_int,
        "credit_score": credit_int,
    }

    # LOCAL FALLBACK STORAGE (customers.json)
    local_file = "customers.json"
    local_customers = {}
    if os.path.exists(local_file):
        try:
            with open(local_file, "r") as f:
                local_customers = json.load(f)
        except Exception:
            local_customers = {}

    # Save to local file dictionary
    local_customers[customer_id] = {
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
        "current_loan_status": str(currentloan_int)
    }

    try:
        with open(local_file, "w") as f:
            json.dump(local_customers, f, indent=2)
        saved_locally = True
    except Exception as e:
        saved_locally = False

    firebase_saved = False
    firebase_error = ""

    if FIREBASE_DB_URL:
        try:
            url = FIREBASE_DB_URL + f"/customers/{customer_id}.json"
            if FIREBASE_API_KEY:
                url += f"?auth={FIREBASE_API_KEY}"
            resp = requests.put(url, json=data, timeout=5)
            if resp.status_code == 200:
                firebase_saved = True
            else:
                firebase_error = f"Firebase returned status {resp.status_code}"
        except Exception as e:
            firebase_error = str(e)
    else:
        firebase_error = "Firebase not configured. Saved to local customers.json file instead."

    return render_template(
        "form.html",
        success=True,
        customer_id=customer_id,
        firebase_saved=firebase_saved,
        firebase_error=firebase_error,
        chatbot_url="http://localhost:5000",
        chatbot_label="Open Chatbot :5000",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5001)
