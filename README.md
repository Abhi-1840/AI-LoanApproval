# AI Loan Approval System

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask 3.1.0](https://img.shields.io/badge/Flask-3.1.0-black.svg)](https://flask.palletsprojects.com/)
[![Google Gemini API](https://img.shields.io/badge/Google%20Gemini-gemini--3.5--flash--lite-orange.svg)](https://aistudio.google.com/)
[![LangChain](https://img.shields.io/badge/LangChain-0.3.14-green.svg)](https://www.langchain.com/)
[![Tests](https://img.shields.io/badge/Unit%20Tests-47%20Passed-brightgreen.svg)](test_loan_system.py)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An intelligent, conversational loan underwriting and pre-screening platform that bridges modern Generative AI (**Google Gemini** via **LangChain**) with a deterministic, rule-based financial underwriting engine in **Python**.

---

## 1. Project Overview

The **AI Loan Approval System** digitizes the initial customer consultation and preliminary underwriting phases of personal loan origination. Instead of forcing applicants to navigate rigid, static 30-field forms, the system provides a conversational chat interface where users can apply for a loan in plain English.

The AI assistant interprets user intent, requests the applicant's Customer ID, evaluates five mandatory banking underwriting criteria in pure Python, calculates accurate monthly EMIs using the standard reducing-balance compound interest formula, and immediately issues a formal PDF Sanction Letter sent directly to the customer's email address.

---

## 2. Problem Statement

Traditional retail loan pre-screening presents significant challenges:
* **High Customer Friction:** Multi-page paper or static online forms have high bounce rates.
* **Delayed Decisioning:** Manual evaluations by loan officers introduce delays of several days for basic eligibility checks.
* **Opaque Rejections:** Conventional applications frequently decline applicants with vague responses rather than specific mathematical reasons.
* **Operational Inefficiencies:** Bank underwriting personnel spend considerable time evaluating applications that fail fundamental age, credit score, or debt-to-income limits.

---

## 3. Key Features

* **Conversational AI Interface:** Natural language dialogue powered by Google's `gemini-3.5-flash-lite` via LangChain.
* **Deterministic Underwriting Engine:** Pure Python logic enforces 5 strict lending conditions with zero AI hallucination.
* **Standard Compound EMI Calculation:** Accurate calculation at 12% per annum using standard banking compound interest formulas.
* **Multi-Failure Rejection Explanations:** When multiple criteria fail, the system outputs clear bullet points explaining all reasons.
* **Multi-Tier Customer Data Access:** Queries Firebase Realtime Database $\rightarrow$ local `customers.json` $\rightarrow$ built-in test records.
* **Dynamic PDF Sanction Letter:** Renders professional bank letters via `xhtml2pdf` and `reportlab`.
* **Automated Email Transmission:** Dispatches sanction letter attachments over Gmail SMTP with TLS encryption.
* **Admin Registration Portal:** Dedicated portal on port `5001` for bank staff to onboard applicants with strict validation.
* **Luxury Fintech Aesthetic:** Styled with charcoal black, warm cream, and champagne gold typography.
* **Animated Feedback:** Continuous rotating brand logo animation during active AI response generation.
* **Comprehensive Test Suite:** 47 automated unit tests covering financial formulas, boundary checks, and API routes.

---

## 4. Technology Stack

| Layer | Technology | Version | Purpose in System |
| :--- | :--- | :--- | :--- |
| **Backend Language** | Python | 3.10 – 3.13 | Core server logic, math, and data processing |
| **Web Framework** | Flask & Flask-CORS | 3.1.0 / 5.0.0 | HTTP REST API endpoints and template rendering |
| **Generative AI** | Google Gemini API | `gemini-3.5-flash-lite` | Natural language comprehension & intent parsing |
| **LLM Orchestration** | LangChain | 0.3.14 | Conversation memory, message modeling, and prompt routing |
| **Database (Local)** | Local JSON Storage | `customers.json` | Resilient, offline-first customer record store |
| **Database (Cloud)** | Firebase Realtime DB | REST API | Optional cloud synchronization via HTTP PUT/GET |
| **PDF Generation** | xhtml2pdf & ReportLab | 0.2.16 / 4.2.5 | HTML-to-PDF rendering and fallback canvas engine |
| **Email Protocol** | smtplib & email.message | Python stdlib | Gmail SMTP transmission over port 587 (STARTTLS) |
| **Frontend** | HTML5, CSS3, Vanilla JS | ES6+ | Responsive Luxury Fintech UI with localStorage session history |
| **Typography** | Google Fonts | Web CDN | Plus Jakarta Sans & Playfair Display fonts |

---

## 5. System Architecture & Workflow

```
[Applicant Browser: chat.html / chat.js]
                 │
                 │ HTTP POST JSON
                 ▼
         [Flask Application (Port 5000)]
                 │
       ┌─────────┴─────────────────────────────────┐
       │ Query Intent Classifier                   │
       ▼                                           ▼
[Structured Query Handler]                [Conversational Route]
(local_master_agent())                    (LangChain + Google Gemini)
       │                                           │
       ▼                                           ▼
[Instant Policy / EMI Reply]              [[FLASK_CALL:...]] Action Tokens
                                                   │
                 ┌─────────────────────────────────┘
                 ▼
    [Core Python Underwriting Engine]
       ├── verify_kyc()        ──► Firebase / customers.json / DUMMY_CUSTOMERS
       ├── underwrite()        ──► 5 Criteria (Age, CIBIL, FOIR, 15x Limit, Tenure)
       ├── calculate_emi()     ──► Reducing Balance Compound Formula
       ├── generate_pdf()      ──► xhtml2pdf Sanction Letter (templates/letter.html)
       └── send_email()        ──► smtplib Gmail SMTP (STARTTLS)
```

### The 5 Strict Underwriting Rules
1. **Age Requirement:** Between **21 and 65 years** (dynamically calculated from Date of Birth).
2. **CIBIL Credit Score:** Minimum threshold of **700** (scale 300 to 900).
3. **Maximum Loan Eligibility:** Up to **15× Monthly Net Salary** (e.g., ₹50k salary $\rightarrow$ ₹7.5L limit).
4. **FOIR (Fixed Obligation to Income Ratio):**
   $$\text{FOIR} = \frac{\text{Existing Monthly EMIs} + \text{Proposed EMI}}{\text{Monthly Net Salary}} \times 100 \le 50.0\%$$
5. **Loan Tenure:** Between **48 months** and **72 months** (4 to 6 years) at fixed **12.0% per annum**.

---

## 6. Project Folder Structure

```
AI-Loan-Approval-System/
├── app.py                     # Main chatbot application (Port 5000)
├── form_app.py                # Admin customer onboarding portal (Port 5001)
├── test_loan_system.py        # Automated test suite (47 unit tests)
├── requirements.txt           # Pinned project dependencies
├── config.json.example        # Configuration template
├── .env.example               # Environment variables template
├── .gitignore                 # Excluded files and secret patterns
├── customers.json             # Local customer database (clean sample data)
├── run.bat                    # 1-click Windows launcher for both servers
├── templates/
│   ├── chat.html              # Chatbot interface
│   ├── form.html              # Customer registration form
│   └── letter.html            # Loan sanction letter HTML template
├── static/
│   ├── css/
│   │   ├── chat.css           # Luxury charcoal + warm cream design system
│   │   └── form.css           # Admin portal styles
│   ├── js/
│   │   └── chat.js            # Frontend chat logic, API integration & animation
│   └── img/
│       └── loanai-logo.png    # Official LoanAI brand logo
├── sanctions/
│   └── .gitkeep               # Directory for generated PDF sanction letters
└── docs/                      # Documentation, Reports & Presentation Package
    ├── AI_Loan_Approval_System_Project_Report.pdf   # Formal Academic Project Report
    ├── AI_Loan_Approval_System_Project_Report.docx  # Editable Project Report
    ├── AI_Loan_Approval_System_Complete_Guide.pdf   # 22-page comprehensive viva handbook
    ├── AI_Loan_Approval_System_Complete_Guide.docx  # Editable viva handbook
    ├── QUICK_REVISION.pdf                           # 5-page last-minute revision sheet
    ├── SETUP_GUIDE.md                               # Detailed installation guide
    ├── HOW_TO_USE_PROJECT.md                        # Step-by-step user walkthrough
    ├── PROJECT_EXPLANATION.md                       # Architecture & underwriting derivation
    └── API_DOCUMENTATION.md                         # Complete REST endpoint specifications
```

---

## 7. Installation & Setup (Windows)

### Prerequisites
* Python 3.10 or higher installed. Ensure **"Add python.exe to PATH"** was checked during installation.
* Git installed.

### Setup Instructions
1. **Clone the repository:**
   ```powershell
   git clone https://github.com/<YOUR_USERNAME>/AI-Loan-Approval-System.git
   cd AI-Loan-Approval-System
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   ```

3. **Install dependencies:**
   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

## 8. Configuration

Copy the example configuration file:
```powershell
Copy-Item config.json.example config.json
```

Open `config.json` and configure your API keys (all keys are optional; the application falls back to local deterministic mode if left blank):
```json
{
  "firebase_database_url": "",
  "firebase_api_key": "",

  "gemini_api_key": "YOUR_GOOGLE_GEMINI_API_KEY",
  "llm_model": "gemini-3.5-flash-lite",
  "llm_temperature": 0.7,

  "gmail_user": "your_email@gmail.com",
  "gmail_app_password": "xxxx xxxx xxxx xxxx",
  "gmail_from": "your_email@gmail.com"
}
```

> [!WARNING]
> **Security:** Never commit `config.json` or `.env` to Git. Both files are listed in `.gitignore`.

---

## 9. Running the Applications

Open two separate PowerShell terminal windows:

### Terminal 1: Chatbot Application (Port 5000)
```powershell
.\venv\Scripts\python.exe app.py
```
* Access the chatbot at: **http://127.0.0.1:5000**

### Terminal 2: Admin Registration Portal (Port 5001)
```powershell
.\venv\Scripts\python.exe form_app.py
```
* Access the admin portal at: **http://127.0.0.1:5001**

---

## 10. Sample Test Profiles & How to Use

The application includes pre-configured sample customer profiles:

| Customer ID | Applicant Name | Monthly Salary | CIBIL | Existing Debt | Expected Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`cust01`** | Ramesh S. | ₹80,000 | 810 | ₹0 | **APPROVED** (EMI: ₹11,122 @ 60m for ₹5L) |
| **`cust10`** | Neha C. | ₹50,000 | 740 | ₹0 | **APPROVED** (EMI: ₹6,673 @ 60m for ₹3L) |
| **`cust99`** | Low Score Customer | ₹30,000 | 580 | ₹5,000 | **REJECTED** (Fails CIBIL, Limit, FOIR) |

### Sample Conversation
1. Open **http://127.0.0.1:5000**
2. Type: `Hello, I want to apply for a loan`
3. Enter Customer ID: `cust01`
4. Enter Loan Amount: `5 lakhs for 5 years`
5. The system approves the loan, displays the monthly EMI and debt ratio, and generates a formal PDF Sanction Letter.

---

## 11. Testing & Verification

Run the comprehensive unit test suite:
```powershell
.\venv\Scripts\python.exe -m unittest test_loan_system.py -v
```

Expected output:
```
Ran 47 tests in 9.987s
OK
```

---

## 12. Known Limitations & Honest Disclaimers

* **Demonstration Prototype:** This is an educational mini-project; no actual financial funds or disbursements occur.
* **Simulated KYC:** Customer verification checks database records by ID; it does not perform regulatory Aadhaar e-KYC or biometric scanning.
* **Authentication:** There is no user password/OTP barrier on customer IDs in this prototype.
* **In-Memory Session Storage:** Chat histories are stored in Python memory and reset upon server restart.

---

## 13. Future Roadmap

1. **Supervised ML Risk Scoring:** Train XGBoost or Logistic Regression models on historical loan default datasets.
2. **Regulatory e-KYC Integration:** Connect to government sandbox APIs (DigiLocker, Aadhaar OTP).
3. **Live Bureau Gateway:** Connect with CRIF High Mark or TransUnion CIBIL REST APIs.
4. **Scalable Production Architecture:** Migrate to PostgreSQL with JWT authentication and Docker containerization.

---

## 14. License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
