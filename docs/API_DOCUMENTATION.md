# REST API Endpoint Documentation

Specifications for all HTTP endpoints exposed by the Chatbot (`app.py`, port 5000) and Admin Portal (`form_app.py`, port 5001).

---

## 1. Chatbot Endpoints (Port 5000)

### `POST /chat`
Submits a user message and receives an AI or local agent response.

* **Headers:** `Content-Type: application/json`
* **Request Body:**
  ```json
  {
    "session_id": "sess_1795521000",
    "user_input": "My ID is cust01"
  }
  ```
* **Response (200 OK):**
  ```json
  {
    "response_text": "Processing request...",
    "orchestration_command": "[[FLASK_CALL:VERIFY_KYC]]"
  }
  ```

---

### `POST /orchestrate`
Internal token broker that executes backend business actions triggered by action tokens.

* **Headers:** `Content-Type: application/json`
* **Step 1: VERIFY_KYC Request:**
  ```json
  {
    "step": "VERIFY_KYC",
    "session_id": "sess_1795521000",
    "customer_info": { "customer_id": "cust01" }
  }
  ```
* **Step 1 Response (200 OK):**
  ```json
  {
    "status": "success",
    "customer_data": {
      "customer_id": "cust01",
      "name": "Ramesh S.",
      "salary": 80000,
      "credit_score": 810,
      "pre_approved_limit": 1200000
    }
  }
  ```

* **Step 2: UNDERWRITE Request:**
  ```json
  {
    "step": "UNDERWRITE",
    "session_id": "sess_1795521000",
    "loan_amount": 500000,
    "tenure": 60
  }
  ```
* **Step 2 Response (200 OK):**
  ```json
  {
    "status": "success",
    "approval_status": "Approved",
    "emi": 11122.22,
    "foir": 13.9,
    "tenure_months": 60,
    "pdf_url": "/sanctions/Sanction_Letter_Ramesh_S_APP-1795521042.pdf"
  }
  ```

---

### `GET /new_chat`
Initializes a clean chat session, resetting conversation memory.
* **Response (200 OK):**
  ```json
  {
    "session_id": "sess_1795536000",
    "status": "ok"
  }
  ```

---

### `GET /health`
System health check endpoint.
* **Response (200 OK):**
  ```json
  {
    "status": "ok",
    "model": "gemini-3.5-flash-lite",
    "firebase_configured": false,
    "dummy_customers": ["cust01", "cust10", "cust99"]
  }
  ```

---

## 2. Admin Portal Endpoints (Port 5001)

### `GET /`
Renders `templates/form.html` for customer registration.

---

### `POST /add-customer`
Submits a multi-field customer registration form with strict backend validation.
* **Content-Type:** `application/x-www-form-urlencoded`
* **Form Fields:** `customerName`, `phoneNumber`, `dob`, `age`, `city`, `panNumber`, `emailAddress`, `salary`, `currentLoan`, `creditScore`.
* **Validation Failure:** Returns HTTP 200 with HTML displaying error list.
* **Validation Success:** Saves to `customers.json` (and Firebase if active), renders confirmation page showing `Preliminary Loan Eligibility: Up to ₹(salary * 15)`.
