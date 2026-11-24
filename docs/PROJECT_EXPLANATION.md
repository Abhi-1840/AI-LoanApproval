# Technical Architecture & Project Explanation

A deep dive into the engineering principles, data pipelines, underwriting logic, and security architecture of the **AI Loan Approval System**.

---

## 1. System Architecture Overview

```
[Browser Client: chat.html / chat.js]
             │
             │ HTTP POST (JSON)
             ▼
     [Flask App (Port 5000)]
             │
     ┌───────┴───────────────────────────────┐
     │ Query Classifier                      │
     ▼                                       ▼
[Structured Query Heuristics]      [Conversational Route]
     │                                       │
     ▼                                       ▼
[local_master_agent()]             [LangChain Orchestration]
(Deterministic Instant Calc)                 │
                                             ▼
                                  [Google Gemini LLM API]
                                  (gemini-3.5-flash-lite)
                                             │
                                             ▼
                                  [[FLASK_CALL:...]] Tokens
                                             │
             ┌───────────────────────────────┘
             ▼
[Python Core Business Services]
   ├── verify_kyc()        ──► Firebase REST / customers.json / DUMMY_CUSTOMERS
   ├── underwrite()        ──► 5 Rules Evaluator (Age, CIBIL, FOIR, Limit, Tenure)
   ├── calculate_emi()     ──► Reducing Balance Compound Formula
   ├── generate_pdf()      ──► xhtml2pdf / ReportLab Canvas (templates/letter.html)
   └── send_email()        ──► smtplib Gmail SMTP (Port 587 STARTTLS)
```

---

## 2. The 5 Mandatory Underwriting Rules

All financial underwriting is executed deterministically by `underwrite()` in `app.py`:

1. **Age Requirement:** $21 \le \text{Age} \le 65\text{ years}$.
   * Extracted from Date of Birth via `calculate_age_from_dob()`.
2. **CIBIL Credit Score:** $\text{Credit Score} \ge 700$.
   * Unsecured personal lending requires prime or super-prime credit records.
3. **Maximum Loan Eligibility Ceiling:**
   $$\text{Max Loan Limit} = \text{Monthly Net Salary} \times 15$$
4. **FOIR (Fixed Obligation to Income Ratio):**
   $$\text{FOIR} = \frac{\text{Existing Monthly EMIs} + \text{Proposed Loan EMI}}{\text{Monthly Net Salary}} \times 100 \le 50.0\%$$
   * Ensures at least 50% of monthly income is reserved for living sustenance.
5. **Permissible Tenure Range:** $48 \le \text{Tenure} \le 72\text{ months}$ (4 to 6 years) at fixed **12% per annum**.

---

## 3. Mathematical EMI Derivation

The standard banking compound interest formula used in `calculate_emi()`:

$$\text{EMI} = \frac{P \times r \times (1 + r)^n}{(1 + r)^n - 1}$$

Where:
* $P$ = Principal Loan Requested
* $r$ = Monthly interest rate = $\frac{12\% / 12}{100} = 0.01$
* $n$ = Number of tenure months

### Concrete Proof:
For $P = ₹5,00,000$, $n = 60\text{ months}$, $r = 0.01$:
$$(1.01)^{60} \approx 1.8166967$$
$$\text{Numerator} = 500000 \times 0.01 \times 1.8166967 = 9083.4835$$
$$\text{Denominator} = 1.8166967 - 1 = 0.8166967$$
$$\text{EMI} = \frac{9083.4835}{0.8166967} = \mathbf{₹11,122.22 \implies ₹11,122/\text{month}}$$

---

## 4. The [[FLASK_CALL:...]] Token Protocol

To prevent hallucination, the AI Large Language Model is strictly separated from decision-making:
* Gemini understands user statements and generates standardized tokens:
  * `[[FLASK_CALL:VERIFY_KYC:<id>]]`
  * `[[FLASK_CALL:UNDERWRITE:<amount>]]`
* Flask intercepts the token using regex, strips it from the user-facing text, and executes the audited Python function.
* The verified Python output is injected into the response payload.

---

## 5. Security & Credential Isolation

* **Strict Git Exclusion:** `config.json` and `.env` are listed in `.gitignore` and are never committed.
* **Server-Side Secret Consumption:** Credentials are only accessed in Python (`os.environ` or `config.json`); never exposed to frontend JavaScript or client HTML.
* **Backend Validation Supremacy:** Even if an attacker bypasses the browser frontend, Python rejects invalid requests.
