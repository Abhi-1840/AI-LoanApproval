# How to Use the AI Loan Approval System

This practical walkthrough demonstrates all user interaction scenarios, test cases, and administrative actions.

---

## 1. Quick Verification Profiles

The system includes pre-configured customer accounts in `customers.json` and memory:

| Customer ID | Applicant Name | Monthly Salary | CIBIL Score | Existing Debt | Expected Underwriting Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`cust01`** | Ramesh S. | ₹80,000 | 810 | ₹0 | **APPROVED** (Eligible up to ₹12,00,000; tested with ₹5L @ 60m) |
| **`cust10`** | Neha C. | ₹50,000 | 740 | ₹0 | **APPROVED** (Eligible up to ₹7,50,000; tested with ₹3L @ 60m) |
| **`cust99`** | Low Score Customer | ₹30,000 | 580 | ₹5,000 | **REJECTED** (Fails CIBIL < 700, Max Limit > ₹4.5L, FOIR > 50%) |
| **`cust9876543210`**| Vikram Patel | ₹60,000 | 760 | ₹5,000 | **APPROVED** (Eligible up to ₹9,00,000) |

---

## 2. Interactive Chatbot Scenarios (Port 5000)

Open your browser at **http://127.0.0.1:5000**.

### Scenario A: Successful Loan Application & Sanction Letter Dispatch
1. **User:** `Hello! I want to apply for a personal loan.`
2. **AI:** `Welcome to Tata Capital LoanAI! Please provide your Customer ID to verify your profile.`
3. **User:** `cust01`
4. **AI:** `Welcome back, Ramesh S.! Your profile is verified. Preliminary loan eligibility is up to ₹12,00,000. How much loan amount would you like to request?`
5. **User:** `5 lakhs for 5 years`
6. **AI:** `🎉 Congratulations Ramesh S.! Your loan of ₹5,00,000 has received Final Approved status at 12% p.a. for 60 months. Monthly EMI: ₹11,122 (FOIR: 13.9%). Your official Sanction Letter has been generated and emailed!`

### Scenario B: Rejected Application (Multi-Criteria Failure)
1. **User:** `Apply for a loan with cust99`
2. **AI:** `Profile verified for Low Score Customer. Salary: ₹30,000. How much loan do you require?`
3. **User:** `500000`
4. **AI:** `❌ Application Rejected: Your application could not be approved due to the following failure(s):`
   * `• CIBIL Score: Credit score (580) is below the minimum required threshold of 700.`
   * `• Maximum Loan Eligibility: Requested loan of ₹5,00,000 exceeds maximum eligible limit of ₹4,50,000 (15x net salary).`
   * `• FOIR Limit Exceeded: Total monthly obligations (53.7%) exceed the maximum allowed 50% limit.`

### Scenario C: Instant Calculator & Policy Queries
* Type: `Calculate EMI for 4 lakhs for 48 months` $\rightarrow$ The local agent computes ₹10,534/month instantly.
* Type: `What are the eligibility criteria?` $\rightarrow$ Lists the 5 strict underwriting conditions.
* Type: `What documents are required?` $\rightarrow$ Returns PAN, Aadhaar, 3 months salary slips, 6 months bank statements.

---

## 3. Administrative Portal Walkthrough (Port 5001)

Open your browser at **http://127.0.0.1:5001**.

1. Fill out applicant details:
   * **Full Name:** e.g. `Ananya Sen`
   * **Mobile Number:** 10 digits (e.g. `9820011223`)
   * **Date of Birth:** `1995-07-15` (Age auto-calculated as 31)
   * **Net Monthly Salary:** `₹65,000`
   * **CIBIL Score:** `770`
   * **Existing Loan EMIs:** `₹8,000`
2. Click **Submit**.
3. Strict backend validation verifies all 5 criteria before creating the customer profile.
4. The system registers the customer with ID `cust9820011223` and calculates:
   $$\text{Preliminary Loan Eligibility} = 15 \times \text{Salary} = ₹9,75,000$$
5. The applicant can now immediately log in to the chatbot on port 5000 using `cust9820011223`.
