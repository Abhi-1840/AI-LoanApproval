# Setup Guide – AI Loan Approval System

A comprehensive, step-by-step setup guide for running the **AI Loan Approval System** on Windows.

---

## 1. System Requirements & Prerequisites

| Component | Minimum Version | Recommended Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Operating System** | Windows 10 | Windows 11 | Host environment |
| **Python** | Python 3.10 | Python 3.11 – 3.13 | Backend runtime |
| **Git** | 2.30+ | Latest | Version control |
| **Terminal** | Command Prompt | PowerShell 7+ | Command execution |
| **Web Browser** | Chrome / Edge | Modern Evergreen | Client UI |

---

## 2. Step-by-Step Installation Instructions

### Step 2.1: Clone or Open the Repository
Open PowerShell and navigate to the project directory:
```powershell
cd d:\ai_loanzip\AI-LoanApproval-main
```

### Step 2.2: Create and Activate Virtual Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
*(If PowerShell blocks execution of scripts, run `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` first).*

### Step 2.3: Upgrade pip and Install Dependencies
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 3. Configuration Setup

The application supports both `config.json` and `.env` files for managing environment variables.

### Option A: Using `config.json` (Recommended)
Copy the example configuration file:
```powershell
Copy-Item config.json.example config.json
```

Edit `config.json`:
```json
{
  "firebase_database_url": "",
  "firebase_api_key": "",

  "gemini_api_key": "YOUR_ACTUAL_GEMINI_API_KEY",
  "llm_model": "gemini-3.5-flash-lite",
  "llm_temperature": 0.7,

  "gmail_user": "your_email@gmail.com",
  "gmail_app_password": "xxxx xxxx xxxx xxxx",
  "gmail_from": "your_email@gmail.com"
}
```

### Option B: Using `.env`
```powershell
Copy-Item .env.example .env
```

> [!NOTE]
> All external services (Google Gemini, Firebase, Gmail SMTP) are **completely optional**. If credentials are blank, the application will automatically run in local fallback mode using `customers.json` and `local_master_agent()`.

---

## 4. Running the Applications

The system comprises two Flask web applications:

### Terminal 1: Main Chatbot Application (Port 5000)
```powershell
.\venv\Scripts\python.exe app.py
```
* **URL:** [http://127.0.0.1:5000](http://127.0.0.1:5000)
* **Description:** Main conversational UI, AI agent, underwriting engine, and PDF generation.

### Terminal 2: Admin Registration Portal (Port 5001)
```powershell
.\venv\Scripts\python.exe form_app.py
```
* **URL:** [http://127.0.0.1:5001](http://127.0.0.1:5001)
* **Description:** Administrative portal used by bank staff to onboard new customers.

---

## 5. Running Automated Verification Tests

To verify that all 47 test cases pass:
```powershell
.\venv\Scripts\python.exe -m unittest test_loan_system.py -v
```
Expected output:
```
Ran 47 tests in 9.987s
OK
```
