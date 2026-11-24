# KCC INSTITUTE OF TECHNOLOGY AND MANAGEMENT
**GREATER NOIDA, UTTAR PRADESH**  
*(Affiliated to Dr. A.P.J. Abdul Kalam Technical University, Lucknow)*  
**DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING**

---

### A MINI-PROJECT REPORT ON
# **AI LOAN APPROVAL SYSTEM**

*Submitted in partial fulfillment of the requirements for the award of the degree of*  
**Bachelor of Technology (B.Tech) in Computer Science and Engineering**

---

**Submitted By:**

| Candidate Name | University Roll Number |
| :--- | :--- |
| **Abhinav Ranakoti** | 2404920100017 |
| **Geeta Rawat** | 2404920100142 |
| **Priyanshu Singh** | 2404920100260 |
| **Manan Attrash** | 2404920100190 |

<br/>

**Under the Guidance of:**  
**Mr. Arpit Verma**  
Assistant Professor  
Department of Computer Science & Engineering  

**Head of Department:**  
**Mr. Chetan Khemraj**  
Department of Computer Science and Engineering  

**Academic Session:** 2026–2027  

---

## CERTIFICATE

This is to certify that the Mini-Project Report entitled **"AI LOAN APPROVAL SYSTEM"** submitted by **Abhinav Ranakoti (Roll No: 2404920100017)**, **Geeta Rawat (Roll No: 2404920100142)**, **Priyanshu Singh (Roll No: 2404920100260)**, and **Manan Attrash (Roll No: 2404920100190)** in partial fulfillment of the requirements for the award of the degree of **Bachelor of Technology in Computer Science and Engineering** from **KCC Institute of Technology and Management, Greater Noida** *(Affiliated to Dr. A.P.J. Abdul Kalam Technical University, Lucknow)*, is a bonafide record of project work carried out under my supervision during the academic session 2026–2027.

The technical designs, software architecture, financial underwriting rules, and code implementations documented herein have been verified against the actual repository source code and have not been submitted to any other University or Institution for any degree or diploma.

<br/><br/>

| ______________________________ | ______________________________ |
| :--- | :--- |
| **Mr. Arpit Verma** | **Mr. Chetan Khemraj** |
| Project Guide | Head of Department (CSE) |
| Assistant Professor, Dept. of CSE | Dept. of Computer Science & Engineering |

---

## DECLARATION

We hereby declare that the work presented in this mini-project report entitled **"AI LOAN APPROVAL SYSTEM"** is an authentic record of our own work carried out at **KCC Institute of Technology and Management, Greater Noida**, under the guidance of **Mr. Arpit Verma**. We confirm that the explanations, diagrams, formulas, and codebase analyses accurately reflect the project repository and have not been plagiarized or submitted elsewhere for any academic award.

**Place:** Greater Noida  
**Date:** 25 November 2026  

**Signature of Candidates:**

| Candidate Name | Roll Number | Signature |
| :--- | :--- | :--- |
| **Abhinav Ranakoti** | 2404920100017 | ______________________________ |
| **Geeta Rawat** | 2404920100142 | ______________________________ |
| **Priyanshu Singh** | 2404920100260 | ______________________________ |
| **Manan Attrash** | 2404920100190 | ______________________________ |

---

## ACKNOWLEDGEMENT

We express our deepest sense of gratitude and sincere thanks to our respected Project Guide, **Mr. Arpit Verma**, Assistant Professor, Department of Computer Science and Engineering, for his invaluable guidance, continuous encouragement, and constructive critique throughout the duration of this mini-project.

We extend our profound thanks to **Mr. Chetan Khemraj**, Head, Department of Computer Science & Engineering, and our respected Director/Principal for providing excellent academic infrastructure, computational facilities, and an encouraging learning environment.

We also thank all faculty members and technical staff of the Computer Science & Engineering department for their continuous support and cooperation during our laboratory sessions.

Finally, we express our heartfelt appreciation to our parents and fellow classmates for their moral support, motivation, and cooperation that enabled the successful completion of this project work.

<br/>

**Abhinav Ranakoti** | **Geeta Rawat** | **Priyanshu Singh** | **Manan Attrash**  
*B.Tech CSE, 5th Semester*  
*KCC Institute of Technology and Management, Greater Noida*  

---

## ABSTRACT

Traditional retail banking loan approval workflows frequently suffer from slow processing speeds, heavy reliance on manual document scrutiny, subjective underwriting interpretations, and fragmented customer communications. This B.Tech mini-project presents the architectural design, algorithmic implementation, and empirical analysis of the **AI Loan Approval System**, an intelligent web-based loan processing platform that marries conversational artificial intelligence with deterministic financial underwriting logic.

The application is developed on a lightweight Flask backend and an asynchronous vanilla JavaScript web interface styled with a luxury fintech visual aesthetic. Conversational interaction is orchestrated via Google Gemini (`gemini-3.5-flash-lite`) wrapped by LangChain, operating under a specialized prompt that acts as a supervisory router. When the user submits identity tokens or financial figures, the AI supervisor yields deterministic system tokens (`[[FLASK_CALL:VERIFY_KYC]]` and `[[FLASK_CALL:UNDERWRITE]]`) rather than hallucinating financial judgments. Customer identity verification is handled via an offline-resilient local database (`customers.json`) with optional cloud synchronization to Firebase Realtime Database and embedded fallback records.

Underwriting decisions are strictly governed by deterministic Python algorithms enforcing five mandatory banking criteria:
1. **Age Requirement:** 21 to 65 years (dynamically computed from Date of Birth).
2. **CIBIL Credit Score Threshold:** Minimum score of 700 (scale 300 to 900).
3. **Salary-Indexed Maximum Borrowing Limit:** Up to 15× applicant's monthly net salary.
4. **Fixed Obligation to Income Ratio (FOIR):** Total monthly debt obligations (existing EMIs + proposed loan EMI) must not exceed a 50% income ceiling.
5. **Loan Tenure Bounds:** 48 to 72 months at a fixed 12.0% annual interest rate.

If multiple eligibility criteria fail, the system outputs clear bulleted explanations detailing every failed condition. Successful applicants receive an instant provisional approval notice, an automatically generated PDF sanction letter produced via `xhtml2pdf` (with ReportLab canvas fallback), and automated email transmission via Gmail SMTP with STARTTLS encryption. An administrative web portal (port 5001) enables staff to register customer records with strict backend validation. A comprehensive test suite of 47 automated unit tests validates mathematical accuracy, edge cases, and API integrity with 100% passing results. This report provides an academically rigorous evaluation of the repository, highlighting its architectural strengths, modular separation of concerns, and concrete real-world limitations.

**Keywords:** Automated Underwriting, Google Gemini, gemini-3.5-flash-lite, LangChain Orchestration, Flask Architecture, Firebase Realtime Database, Equated Monthly Installment (EMI), Fixed Obligation to Income Ratio (FOIR), xhtml2pdf Sanction Letters, Deterministic Financial Computation.

---

## TABLE OF CONTENTS

* **1. Introduction**
  * 1.1 Background and Motivation
  * 1.2 Problem Statement
  * 1.3 Objectives of the Project
  * 1.4 Scope of the Project
* **2. Literature Review and Existing System**
  * 2.1 Review of Existing Systems
  * 2.2 Critique of Traditional Loan Processing
  * 2.3 Proposed Hybrid Architecture
  * 2.4 Key Architectural Advantages
* **3. Requirement Analysis**
  * 3.1 Functional Requirements Specification
  * 3.2 Non-Functional Requirements
  * 3.3 Hardware and Software Specifications
* **4. System Design and Diagrams**
  * 4.1 System Architecture and Data Flow
  * 4.2 Process and Behavioral Modeling
  * 4.3 Actuarial Underwriting Rules and Database Design
* **5. Technology Stack**
  * 5.1 Core Technology Overview
* **6. System Implementation**
  * 6.1 Project Directory Structure
  * 6.2 Key Implementation Code Listings
* **7. Working and Results**
  * 7.1 End-to-End Application Workflow
  * 7.2 Real-World Evaluation Scenarios
  * 7.3 Test Cases and Quality Assurance Matrix
* **8. Limitations and Future Scope**
  * 8.1 Current Technical Limitations
  * 8.2 Future Enhancements
* **9. Conclusion and References**
  * 9.1 Conclusion
  * 9.2 References
* **Appendix: Setup & Formulas**
  * A.1 Important Actuarial Formulas
  * A.2 Installation and Execution Instructions

---

## LIST OF FIGURES & TABLES

### Figures
* **Fig. 4.1:** System Architecture of AI Loan Approval System
* **Fig. 4.2:** Application Workflow Flowchart
* **Fig. 4.3:** Data Flow Diagram (Level 1 DFD)
* **Fig. 4.4:** System Use Case Diagram
* **Fig. 4.5:** Activity Diagram: Customer Journey & Underwriting Flow
* **Fig. 4.6:** Sequence Diagram: Multi-Tier Service Interaction
* **Fig. 4.7:** Loan Eligibility Decision Tree Flowchart
* **Fig. 4.8:** Data Storage Model & Structure

### Tables
* **Table 3.1:** Functional Requirements Specification
* **Table 3.2:** Non-Functional Requirements Specification
* **Table 3.3:** Hardware and Software Specifications
* **Table 4.1:** Underwriting Decision Rules Matrix
* **Table 5.1:** Technology Stack Summary
* **Table 6.1:** Repository Structure Summary
* **Table 7.1:** Underwriting Scenarios & Mathematical Outcomes
* **Table 7.2:** Comprehensive Quality Assurance Matrix (47-Test Suite)

---

## CHAPTER 1: INTRODUCTION

### 1.1 Background and Motivation
The personal credit and retail lending sector forms the bedrock of modern consumer finance. Historically, commercial banks and Non-Banking Financial Companies (NBFCs) relied on physical branch visits, manual scrutiny of income tax returns, salary slips, and physical address verifications. This paper-heavy paradigm introduced multi-week turnaround times, high administrative overheads, and inconsistent subjective evaluations.

With the rapid maturation of generative artificial intelligence and Large Language Models (LLMs), financial institutions are adopting conversational automation. However, direct application of LLMs to underwriting risks arithmetic hallucinations and regulatory non-compliance. The **AI Loan Approval System** resolves this dichotomy by employing a hybrid architecture: **Google Gemini (`gemini-3.5-flash-lite`)** handles natural language interaction, while deterministic Python algorithms execute 100% of the financial calculations and compliance rules.

### 1.2 Problem Statement
Traditional retail lending workflows encounter four systemic bottlenecks:
1. **Lengthy Turnaround Times:** Manual verification cycles delay credit access, causing substantial applicant drop-off.
2. **High Operational Expenses:** Dedicated underwriting teams increase transaction costs for low-ticket retail loans.
3. **Underwriting Inconsistencies:** Human credit officers apply subjective risk interpretations across identical financial profiles.
4. **LLM Hallucination Risks:** Naive AI loan bots frequently hallucinate non-existent credit terms, approve ineligible loans, or compute faulty interest rates.

### 1.3 Objectives of the Project
* Develop an intuitive web-based conversational interface for retail loan applications with an understated luxury fintech aesthetic.
* Integrate Google Gemini (`gemini-3.5-flash-lite`) via LangChain purely as a supervisory conversational router without financial decision-making authority.
* Implement automated KYC identity resolution via local JSON storage (`customers.json`) with optional cloud-hosted Firebase Realtime Database and robust dummy fallbacks.
* Enforce five strict deterministic underwriting rules: Age (21–65 years calculated from DOB), credit score threshold (≥700), borrowing limit (up to 15× monthly salary), tenure bounds (48–72 months), and a 50% Fixed Obligation to Income Ratio (FOIR) debt-to-income ceiling.
* Provide multi-failure rejection reporting when multiple criteria are breached.
* Compute reducing-balance Equated Monthly Installments (EMI) using actuarial banking mathematics at a fixed 12.0% per annum.
* Automatically generate legally formatted PDF sanction letters via `xhtml2pdf` (with ReportLab canvas fallback) and dispatch them via Gmail SMTP with STARTTLS.
* Provide a standalone administrative web portal (port 5001) for registering customer records with strict backend validation.
* Validate all functional operations through an automated test suite of 47 unit tests.

### 1.4 Scope of the Project
The project encompasses unsecured personal loans for salaried retail applicants. It validates customer IDs, processes loan amount requests, computes actuarial EMIs, renders formal sanction letters with *Tata Capital Finance Ltd.* template branding, and transmits email attachments. Core banking ledger integration and live bureau credit pulls (CIBIL/Experian) remain outside the academic prototype scope.

---

## CHAPTER 2: LITERATURE REVIEW AND EXISTING SYSTEM

### 2.1 Review of Existing Systems
Digital lending solutions fall broadly into three historical categories:
1. **Legacy Portal Systems:** Static web forms that collect user data for asynchronous batch review by human underwriters. While mathematically safe, they offer zero real-time interactivity.
2. **Rule-Based Chatbots:** Decision-tree chatbots using static regex keyword matching. They provide instant responses but break down when users deviate from rigid conversational scripts.
3. **Pure LLM Agents:** Experimental systems deploying end-to-end generative models. These systems suffer from severe stochastic drift, arithmetic inaccuracies, and vulnerability to prompt injection attacks.

### 2.2 Critique of Traditional Loan Processing
Traditional manual systems exhibit structural vulnerabilities: lack of scalability during peak seasonal loan demands, opaque rejection rationales provided to consumers, and heavy reliance on physical paper trails. These operational inefficiencies inflate borrower acquisition costs by up to 40% compared to automated FinTech platforms.

### 2.3 Proposed Hybrid Architecture
The proposed system adopts a dual-engine paradigm:
* **Conversational Intake Engine:** Google Gemini (`gemini-3.5-flash-lite`) wrapped by LangChain interprets user queries and extracts key financial entities.
* **Deterministic Execution Engine:** Intercepts programmatic tokens (`[[FLASK_CALL:VERIFY_KYC]]` and `[[FLASK_CALL:UNDERWRITE]]`) emitted by the supervisor, delegating customer lookup, credit scoring, tenure assignment, FOIR affordability checks, and EMI computation to auditable Python routines.

### 2.4 Key Architectural Advantages
* **Zero Arithmetic Drift:** All monetary calculations are performed by Python's floating-point math libraries.
* **Instantaneous Sanctions:** Eligible borrowers obtain downloadable, signed sanction letters within seconds.
* **High Fault Tolerance:** If Google Gemini API quotas expire, an embedded regex-based local master agent automatically resumes conversational routing.
* **Rigorous Automated Quality Assurance:** An integrated test suite of 47 unit tests continuously verifies all underwriting rules, boundary conditions, and API endpoints.

---

## CHAPTER 3: REQUIREMENT ANALYSIS

### 3.1 Functional Requirements Specification

**Table 3.1: Functional Requirements Specification**

| ID | Module | Functional Requirement Description | Verification |
| :--- | :--- | :--- | :--- |
| **FR-01** | Chatbot UI | Accept natural text, render formatted responses, show animated rotating logo feedback. | UI Inspection |
| **FR-02** | Session Init | Issue unique session IDs (`/new_chat`) and maintain conversational state in memory and localStorage. | API Verification |
| **FR-03** | AI Routing | Prompt Gemini to emit programmatic `[[FLASK_CALL:...]]` tokens upon data intake. | Prompt Testing |
| **FR-04** | Fallback Logic | Execute regex-based `local_master_agent()` when Gemini API is offline or for instant calculators. | Unit Testing |
| **FR-05** | KYC Module | Query local `customers.json` and optional Firebase RTDB; fallback to dummy dictionary. | Storage Check |
| **FR-06** | Underwriting | Enforce 5 rules: Age (21–65), CIBIL (≥700), Limit (≤15× salary), FOIR (≤50%), Tenure (48–72m). | Algorithmic Test |
| **FR-07** | EMI Engine | Compute reducing-balance monthly installment at 12% p.a. across assigned tenure. | Math Validation |
| **FR-08** | PDF Engine | Compile Jinja2 HTML sanction template into PDF via `xhtml2pdf` (with ReportLab fallback). | File Inspection |
| **FR-09** | SMTP Mailer | Transmit generated PDF letter to customer email address via Gmail SMTP (port 587, STARTTLS). | SMTP Protocol Log |
| **FR-10** | Admin Portal | Provide standalone portal (port 5001) for registering customers with strict backend validation. | Integration Test |

### 3.2 Non-Functional Requirements

**Table 3.2: Non-Functional Requirements Specification**

| NFR ID | Attribute | Target Performance Specification |
| :--- | :--- | :--- |
| **NFR-01** | Response Time | End-to-end response latency under 3.0 seconds per conversational turn. |
| **NFR-02** | Deterministic Safety | Zero reliance on generative LLM outputs for numeric decisions, amounts, or approvals. |
| **NFR-03** | Availability | Continuous availability ensured via local deterministic regex fallback routines (`local_master_agent()`). |
| **NFR-04** | Maintainability | Modular Python architecture isolating routing, underwriting, storage, and PDF generation. |
| **NFR-05** | Credential Security | Zero credentials committed; secrets loaded server-side via gitignored `config.json` and `.env`. |

### 3.3 Hardware and Software Specifications

**Table 3.3: Hardware and Software Specifications**

| Component | Development Specification | Minimum Client Environment |
| :--- | :--- | :--- |
| **Processor** | Intel Core i3 / AMD Ryzen 3 (Quad-Core 2.0 GHz) | Single Core 1.0 GHz CPU |
| **Memory (RAM)** | 4.0 GB DDR4 System RAM | 1.0 GB Available RAM |
| **Disk Storage** | 500 MB Free Disk Storage | 50 MB Browser Cache |
| **Operating System** | Windows 10/11, Ubuntu 20.04+, macOS | Platform Independent (Web Browser) |
| **Runtime & Packages** | Python 3.10+, Flask 3.1.0, LangChain 0.3.14 | HTML5 / ES6 Compliant Web Browser |
| **External Services** | Google Gemini API (`gemini-3.5-flash-lite`), Firebase RTDB, Gmail SMTP | Active Internet Connection |

---

## CHAPTER 4: SYSTEM DESIGN AND DIAGRAMS

### 4.1 System Architecture and Data Flow
The system follows a three-tier architecture: the Client Presentation Tier (`chat.html`, `chat.js`), the Server Application Tier (Flask `app.py`, `form_app.py`), and the External Services Tier (Gemini, Firebase, Gmail SMTP). Fig. 4.1 details the architectural boundaries, and Fig. 4.2 illustrates the complete application workflow.

```
                    ┌────────────────────────────────────────────────────────┐
                    │               CLIENT PRESENTATION TIER                 │
                    │   templates/chat.html  •  static/js/chat.js (ES6)      │
                    │   static/css/chat.css (Luxury Fintech Charcoal Theme)  │
                    └───────────────────────────┬────────────────────────────┘
                                                │ HTTP POST /chat
                                                ▼
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 SERVER APPLICATION TIER                                    │
│                                                                                            │
│  ┌─────────────────────────────── Flask (app.py : Port 5000) ───────────────────────────┐  │
│  │                                                                                       │  │
│  │   /chat (POST) ──────────► Query Classifier Heuristics                                │  │
│  │                                  │                                                    │  │
│  │                   ┌──────────────┴──────────────┐                                     │  │
│  │                   ▼                             ▼                                     │  │
│  │        [Structured Queries]          [Conversational Dialogue]                        │  │
│  │        local_master_agent()          LangChain + Google Gemini API                    │  │
│  │        (Instant Calculations)        (gemini-3.5-flash-lite)                          │  │
│  │                   │                             │                                     │  │
│  │                   │                  [[FLASK_CALL:...]] Tokens                        │  │
│  │                   │                             │                                     │  │
│  │                   └──────────────┬──────────────┘                                     │  │
│  │                                  ▼                                                    │  │
│  │                    Core Underwriting Engine (underwrite())                            │  │
│  │                    ├── Age Check (21–65 from DOB)                                     │  │
│  │                    ├── CIBIL Score Gate (≥ 700)                                       │  │
│  │                    ├── Max Borrowing Ceiling (≤ 15× Salary)                           │  │
│  │                    ├── FOIR Affordability Ceiling (≤ 50%)                             │  │
│  │                    └── Tenure Allocation (48–72 Months @ 12% p.a.)                    │  │
│  │                                  │                                                    │  │
│  │                    Document & Dispatch Services                                       │  │
│  │                    ├── generate_sanction_letter_pdf() (xhtml2pdf / ReportLab)         │  │
│  │                    └── send_email_with_attachment() (smtplib Gmail STARTTLS)          │  │
│  └──────────────────────────────────┬────────────────────────────────────────────────────┘  │
│                                     │                                                       │
│  ┌─────────────────────────────── Admin Portal (form_app.py : Port 5001) ───────────────┐  │
│  │   templates/form.html ──► validate_customer_eligibility() ──► Write to Storage        │  │
│  └──────────────────────────────────┬────────────────────────────────────────────────────┘  │
└─────────────────────────────────────┼───────────────────────────────────────────────────────┘
                                      │
                                      ▼
                    ┌────────────────────────────────────────────────────────┐
                    │               STORAGE & EXTERNAL SERVICES              │
                    │   Primary: customers.json (Local Resilient Database)   │
                    │   Optional: Firebase Realtime Database (REST API)      │
                    │   Dispatch: Gmail SMTP (smtp.gmail.com:587)            │
                    │   AI Model: Google Gemini API (gemini-3.5-flash-lite)  │
                    └────────────────────────────────────────────────────────┘
```
**Fig. 4.1: System Architecture of AI Loan Approval System**

```
                         [User Opens Application (chat.html)]
                                          │
                                          ▼
                       [New Session Initialized (/new_chat)]
                                          │
                                          ▼
                            [User Sends Message via Chat]
                                          │
                                          ▼
                         [Flask /chat Receives User Input]
                                          │
                      Is Structured Query or Customer ID?
                                 /                \
                             YES /                  \ NO
                                /                    \
                               ▼                      ▼
                     [local_master_agent()]     [Gemini LLM (LangChain)]
                               │                      │
                               │                Emits [[FLASK_CALL:...]]
                               │                      │
                               └──────────┬───────────┘
                                          │
                               Contains Token?
                                 /          \
                     VERIFY_KYC /            \ UNDERWRITE
                               /              \
                              ▼                ▼
                     [verify_kyc(id)]     [underwrite(amt)]
                      (JSON / Firebase)   (5 Banking Rules)
                              │                /     \
                              ▼               /       \
                     [Profile Verified]   APPROVED   REJECTED
                              │               │           │
                              ▼               ▼           ▼
                      [Ask Loan Amount]  [Build PDF]  [Display All]
                                         [Send Email] [Rejection Reasons]
```
**Fig. 4.2: Application Workflow Flowchart**

### 4.2 Process and Behavioral Modeling
* **Data Flow Diagram (Level 1 DFD):** Models data packet transformations between the borrower, chatbot UI, supervisory LLM, underwriting engine, document compiler, and SMTP mailer.
* **System Use Case Diagram:** Details actor interactions across retail applicants (starting sessions, inputting customer IDs, requesting amounts, obtaining sanction letters) and bank administrators (registering customer records via `form_app.py`).
* **Activity & Sequence Diagrams:** Illustrate the step-by-step chronological transitions from initial handshake to PDF document attachment and UI rendering.

```
Borrower (Browser)       Flask app.py        local_master_agent     Gemini LLM        Storage / SMTP
      │                        │                      │                  │                  │
      │── 1. Enter "cust01" ──►│                      │                  │                  │
      │                        │── 2. Is Cust ID? ───►│                  │                  │
      │                        │                      │── 3. Return Token│                  │
      │                        │◄── [[VERIFY_KYC]] ───│                  │                  │
      │                        │── 4. Query Record ────────────────────────────────────────►│
      │                        │◄── 5. Ramesh S., 80k Salary, 810 CIBIL ────────────────────│
      │◄── 6. Verified: Limit ─│                      │                  │                  │
      │                        │                      │                  │                  │
      │── 7. "5 lakhs, 60m" ──►│                      │                  │                  │
      │                        │── 8. underwrite() ───┼──────────────────┼─────────────────►│
      │                        │   • Age: 35 (OK)     │                  │                  │
      │                        │   • CIBIL: 810 (OK)  │                  │                  │
      │                        │   • Limit: 12L (OK)  │                  │                  │
      │                        │   • FOIR: 13.9% (OK) │                  │                  │
      │                        │   • EMI: ₹11,122     │                  │                  │
      │                        │── 9. Render PDF ─────┼──────────────────┼─────────────────►│
      │                        │── 10. Send Email ─────────────────────────────────────────►│
      │◄── 11. Final Approved ─│                      │                  │                  │
```
**Fig. 4.6: Sequence Diagram: Multi-Tier Service Interaction**

### 4.3 Actuarial Underwriting Rules and Database Design
The underwriting engine enforces strict mathematical policies mapped against the customer data model:
1. **Age Criteria:** Applicant must be between 21 and 65 years. Age is dynamically computed from Date of Birth via `calculate_age_from_dob()`.
2. **Credit Score Gate:** Applicants with CIBIL credit score < 700 are rejected immediately.
3. **Maximum Loan Eligibility Ceiling:** Total requested loan must not exceed 15× monthly net salary (`pre_approved_limit = salary * 15`). Requests exceeding this limit are rejected.
4. **Salary-Indexed Tenure Allocation:** Tenure is assigned or validated within 48 to 72 months based on income bracket (<₹40k: 48 months; ₹40k–₹80k: 60 months; >₹80k: 72 months).
5. **Actuarial Compound EMI Calculation:**
   $$\text{EMI} = \frac{P \times r \times (1 + r)^n}{(1 + r)^n - 1}$$
   where $r = \frac{12\% / 12}{100} = 0.01$ per month, and $n$ is tenure in months.
6. **Fixed Obligation to Income Ratio (FOIR):**
   $$\text{FOIR} = \frac{\text{Existing Monthly EMIs} + \text{Proposed Loan EMI}}{\text{Monthly Net Salary}} \times 100 \le 50.0\%$$
   If FOIR exceeds 50.0%, the application is rejected.
7. **Multi-Failure Diagnostic Reporting:** If an application breaches multiple conditions, all failures are collected and presented simultaneously as bullet points.

**Table 4.1: Underwriting Decision Rules Matrix**

| Evaluated Parameter | Operational Rule / Threshold | System Consequence |
| :--- | :--- | :--- |
| **Applicant Age** | $\text{Age} < 21 \text{ or } \text{Age} > 65$ | Rejection: *"Age Requirement: Below 21 or exceeds 65 years"* |
| **Credit Score** | $\text{CIBIL Score} < 700$ | Rejection: *"CIBIL Score: Below minimum threshold of 700"* |
| **Loan Amount** | $\text{Amount} > \text{Salary} \times 15$ | Rejection: *"Maximum Loan Eligibility: Exceeds 15x monthly salary limit"* |
| **FOIR Affordability** | $\text{FOIR} > 50.0\%$ | Rejection: *"FOIR Limit Exceeded: Total obligations exceed 50% of salary"* |
| **Loan Tenure** | $\text{Tenure} < 48 \text{ or } \text{Tenure} > 72$ | Rejection: *"Loan Tenure: Must be between 48 and 72 months"* |
| **All Rules Satisfied** | Age [21–65], CIBIL [≥700], Amount [≤15x], FOIR [≤50%], Tenure [48–72m] | **Final Approved:** PDF sanction letter generated and emailed |

---

## CHAPTER 5: TECHNOLOGY STACK

### 5.1 Core Technology Overview
The system leverages modern, lightweight technologies chosen for reliability, rapid execution, and ease of deployment:
* **Python 3.10+:** Core interpreter executing mathematical underwriting, file I/O, string parsing, and web routing.
* **Flask 3.1.0 & Flask-CORS 5.0.0:** Lightweight microframework managing HTTP REST endpoints and serving Jinja2 templates.
* **Google Gemini & LangChain:** `gemini-3.5-flash-lite` model accessed via `ChatGoogleGenerativeAI` abstraction for intent recognition with high free-tier rate limits (1,500 requests/day).
* **Local JSON Storage (`customers.json`):** Resilient, offline-first primary customer database.
* **Firebase Realtime Database:** Optional cloud-hosted NoSQL JSON database accessed via direct HTTPS REST endpoints.
* **xhtml2pdf 0.2.16 & ReportLab 4.2.5:** HTML/CSS to PDF compilation engine generating signed sanction documents.
* **Gmail SMTP:** Transport Layer Security (TLS) protocol client (port 587) for automated email delivery.
* **Frontend Stack:** Semantic HTML5, dark-mode Luxury Fintech CSS3, and vanilla ES6 JavaScript using asynchronous Fetch APIs.

**Table 5.1: Technology Stack Summary**

| Technology | Version | Architectural Role | Key Project Functionality |
| :--- | :--- | :--- | :--- |
| **Python** | 3.10 – 3.13 | Runtime Language | Executes underwriting math, file I/O, and server routing. |
| **Flask** | 3.1.0 | Web Server | Handles HTTP endpoints (`/`, `/chat`, `/orchestrate`, `/new_chat`, `/health`). |
| **Flask-CORS** | 5.0.0 | Security Policy | Manages Cross-Origin Resource Sharing for asynchronous client API requests. |
| **LangChain** | 0.3.14 | LLM Framework | Manages conversational memory structures (`HumanMessage`, `AIMessage`). |
| **Gemini API** | `gemini-3.5-flash-lite` | AI Model | Identifies customer tokens and emits orchestration commands. |
| **Local JSON** | Python `json` stdlib | Primary Database | Persists customer KYC records and pre-approved limits offline. |
| **Firebase RTDB** | REST API | Cloud Database | Optional real-time cloud persistence of customer KYC records. |
| **xhtml2pdf** | 0.2.16 | Document Engine | Compiles `letter.html` into formal binary PDF sanction documents. |
| **ReportLab** | 4.2.5 | Canvas Fallback | Low-level programmatic drawing engine for sanction letters and reports. |
| **Gmail SMTP** | Port 587 (STARTTLS) | Email Service | Transmits sanction letters with PDF attachments via TLS. |

---

## CHAPTER 6: SYSTEM IMPLEMENTATION

### 6.1 Project Directory Structure

**Table 6.1: Repository Structure Summary**

| File / Directory Path | Type | Operational Responsibility in Repository |
| :--- | :--- | :--- |
| **`app.py`** | Python | Primary backend server: routes, AI supervisor, underwriting math, PDF & email. |
| **`form_app.py`** | Python | Secondary admin server (port 5001) for registering customers with strict validation. |
| **`test_loan_system.py`** | Python | Comprehensive automated test suite containing 47 unit test cases. |
| **`customers.json`** | JSON | Local customer database storing KYC records, salaries, and credit scores. |
| **`templates/chat.html`** | HTML | Chatbot user interface with sidebar session history and rotating logo feedback. |
| **`templates/form.html`** | HTML | Customer data entry form for administrative record creation. |
| **`templates/letter.html`** | HTML | Formal sanction letter Jinja2 layout (*Tata Capital Finance Ltd.*). |
| **`static/js/chat.js`** | JavaScript | Asynchronous fetch client, message rendering, localStorage session management. |
| **`static/css/chat.css`** | CSS | Luxury Fintech design system (Charcoal `#1E1E1E`, Cream `#F5F0E8`, Gold `#C9A96E`). |
| **`static/img/loanai-logo.png`** | Asset | Official LoanAI brand logo asset (rotates during AI response generation). |
| **`sanctions/`** | Directory | Storage directory for generated PDF sanction letter documents. |
| **`docs/`** | Directory | Complete project reports, viva preparation guides, and technical documentation. |

### 6.2 Key Implementation Code Listings

#### Listing 6.1: Client-Side Orchestration Handler (`chat.js`)
```javascript
// chat.js: Client-side interception of backend orchestration commands
if (data.orchestration_command) {
    addMessage("Processing request...", "assistant");
    await handleOrchestration(data.orchestration_command, text);
    return;
}
addMessage(data.response_text, "assistant");
```

#### Listing 6.2: Supervisor System Prompt (`app.py`)
```python
# app.py: Gemini Supervisor System Prompt constraining LLM outputs
LLM_SYSTEM_PROMPT = """You are the Supervisor Agent for a Loan Sales assistant.
RULES (very strict):
- If user provides customer ID in format custXXXX, reply with token: [[FLASK_CALL:VERIFY_KYC]]
- When user provides loan amount, reply with token: [[FLASK_CALL:UNDERWRITE]]
- Otherwise, reply with normal conversational text."""
```

#### Listing 6.3: Three-Tier KYC Resolution (`app.py`)
```python
# app.py: Multi-Tier KYC Verification Routine
def verify_kyc(customer_id):
    cid = customer_id.lower().strip()
    # Tier 1: Check Firebase Realtime Database
    c = get_customer_from_firebase(cid)
    if c:
        c["status"] = "Verification Successful"
        return c
    # Tier 2: Check local customers.json
    if os.path.exists("customers.json"):
        with open("customers.json", "r") as f:
            saved = json.load(f)
        match = saved.get(cid) or saved.get(customer_id)
        if match:
            res = match.copy()
            res["status"] = "Verification Successful"
            return res
    # Tier 3: Check built-in dummy customers
    dummy = DUMMY_CUSTOMERS.get(cid)
    if dummy:
        res = dummy.copy()
        res["status"] = "Verification Successful"
        return res
    return {"status": "Verification Failed", "message": "Customer ID not found"}
```

#### Listing 6.4: Underwriting Algorithm Enforcing 5 Strict Rules (`app.py`)
```python
# app.py: Core Actuarial Underwriting & Multi-Criteria Validation
def calculate_emi(principal, rate, months):
    r = (rate / 100) / 12  # 12% annual = 0.01 monthly
    if months <= 0: return None
    return (principal * r * (1 + r) ** months) / ((1 + r) ** months - 1)

def underwrite(customer, loan_amount, tenure=None):
    parsed_amt = parse_loan_amount_text(loan_amount)
    if parsed_amt is None or parsed_amt <= 0:
        return {"status": "Rejection", "failed_conditions": ["Invalid loan amount."]}
    
    loan_amount = parsed_amt
    salary = float(customer.get("salary", 0) or 0)
    credit = int(customer.get("credit_score", 0) or 0)
    age = calculate_age_from_dob(customer.get("dob")) or int(customer.get("age", 0) or 0)
    tenure = int(tenure) if tenure else determine_tenure_months(salary)
    limit = salary * 15
    emi = calculate_emi(loan_amount, 12, tenure) or 0.0
    existing_emi = float(customer.get("current_loan_status", 0) or 0)
    total_monthly_emi = existing_emi + emi
    foir = (total_monthly_emi / salary) * 100.0 if salary > 0 else 100.0

    failed_reasons = []
    # 1. Age Validation (21 - 65 years)
    if age < 21: failed_reasons.append(f"Age Requirement: Applicant age ({age}) is below 21.")
    elif age > 65: failed_reasons.append(f"Age Requirement: Applicant age ({age}) exceeds 65.")
    # 2. CIBIL Score Validation (>= 700)
    if credit < 700: failed_reasons.append(f"CIBIL Score: Score ({credit}) is below minimum 700.")
    # 3. Tenure Validation (48 - 72 months)
    if tenure < 48 or tenure > 72: failed_reasons.append(f"Tenure: ({tenure} months) outside 48-72 range.")
    # 4. Maximum Loan Amount (15x Salary)
    if loan_amount > limit: failed_reasons.append(f"Loan Eligibility: Requested ₹{int(loan_amount):,} exceeds limit ₹{int(limit):,}.")
    # 5. FOIR Affordability Check (Total monthly EMI <= 50% salary)
    if round(foir, 2) > 50.00: failed_reasons.append(f"FOIR Limit: Obligations ({foir:.1f}%) exceed 50% limit.")

    if failed_reasons:
        return {"status": "Rejection", "failed_conditions": failed_reasons,
                "message": "Loan rejected:\n• " + "\n• ".join(failed_reasons)}

    return {"status": "Approved", "emi": emi, "tenure_months": tenure, "foir": foir,
            "message": f"Congratulations! Loan of ₹{int(loan_amount):,} Approved. EMI: ₹{int(emi):,}."}
```

#### Listing 6.5: Document Generation Pipeline (`app.py`)
```python
# app.py: PDF Sanction Letter Compilation & SMTP Transmission
def generate_sanction_letter_pdf(customer_input, loan_amount, tenure):
    app_no = f"APP-{int(time.time())}"
    emi = calculate_emi(loan_amount, 12, tenure)
    html = render_template(
        "letter.html",
        date=datetime.now().strftime("%d-%b-%Y"),
        customer_name=customer_input.get("name"),
        customer_city=customer_input.get("city", "Delhi"),
        application_no=app_no,
        loan_amount=f"{int(loan_amount):,}",
        tenure=tenure,
        emi=f"{int(emi):,}"
    )
    path = os.path.join(SANCTIONS_DIR, f"Sanction_Letter_{customer_input.get('customer_id')}_{app_no}.pdf")
    try:
        with open(path, "wb") as f:
            pisa.CreatePDF(io.BytesIO(html.encode("utf-8")), dest=f)
    except Exception:
        path = _generate_simple_pdf(customer_input.get("name"), customer_input.get("customer_id"),
                                    loan_amount, tenure, emi, app_no, datetime.now().strftime("%d-%b-%Y"), path)
    return path
```

---

## CHAPTER 7: WORKING AND RESULTS

### 7.1 End-to-End Application Workflow
The end-to-end user journey executes through five sequential milestones:
1. **Session Handshake:** User opens `chat.html`; `chat.js` requests a new session ID from `/new_chat` and renders the luxury dark theme with a rotating logo typing indicator.
2. **Conversational Intake:** User types a natural greeting or loan intent; Gemini supervisor responds conversationally and requests customer identification.
3. **KYC Resolution:** User enters `cust01`; supervisor outputs `[[FLASK_CALL:VERIFY_KYC]]`; `/orchestrate` fetches the Ramesh S. profile from `customers.json` or Firebase and displays their preliminary pre-approved limit.
4. **Underwriting Evaluation:** User enters desired loan amount (₹5,00,000); supervisor outputs `[[FLASK_CALL:UNDERWRITE]]`; `underwrite()` checks Age, CIBIL (810 ≥ 700), Loan Limit (₹5L ≤ ₹12L), and FOIR (13.9% ≤ 50%).
5. **Sanction Compilation & Email Dispatch:** System calls `generate_sanction_letter_pdf()`, creates the PDF document in `sanctions/`, sends it via Gmail SMTP, and displays confirmation with download link in chat.

### 7.2 Real-World Evaluation Scenarios

**Table 7.1: Underwriting Scenarios & Mathematical Outcomes**

| ID | Customer Profile | Requested Loan | Assigned Tenure | Computed EMI | Underwriting Outcome & Decision Rule |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SC-01** | Ramesh S. (`cust01`)<br/>Salary: ₹80,000, CIBIL: 810 | ₹5,00,000 | 60 Months | ₹11,122 | **FINAL APPROVED** (Amount ≤ 15× Salary Limit of ₹12L; FOIR 13.9% ≤ 50%) |
| **SC-02** | Neha C. (`cust10`)<br/>Salary: ₹50,000, CIBIL: 740 | ₹3,00,000 | 60 Months | ₹6,673 | **FINAL APPROVED** (Amount ≤ 15× Salary Limit of ₹7.5L; FOIR 13.3% ≤ 50%) |
| **SC-03** | Low Score (`cust99`)<br/>Salary: ₹30,000, CIBIL: 580 | ₹5,00,000 | 60 Months | ₹11,122 | **REJECTED** (Fails CIBIL 580 < 700, Fails Limit ₹5L > ₹4.5L, Fails FOIR 53.7% > 50%) |
| **SC-04** | Underage Applicant<br/>Age: 19 years | ₹1,00,000 | 48 Months | N/A | **REJECTED** (*Applicant age (19) is below minimum required age of 21*) |
| **SC-05** | Over-Limit Request<br/>Salary: ₹50,000, CIBIL: 780 | ₹10,00,000 | 60 Months | N/A | **REJECTED** (*Requested loan ₹10L exceeds maximum 15x salary limit of ₹7.5L*) |

### 7.3 Test Cases and Quality Assurance Matrix

**Table 7.2: Comprehensive Quality Assurance Matrix (47-Test Suite)**

| Test Group | Test Cases Covered | Input / Scenario Evaluated | Expected System Output | Status |
| :--- | :--- | :--- | :--- | :--- |
| **KYC Resolution** | Tests 01–03 | Valid `cust01`, uppercase `CUST10`, unregistered ID | Correct record or *Verification Failed* notice | **PASSED** |
| **Financial Math** | Tests 04–09 | Standard EMI, 15x salary limit, tenure determination | Exact compound formula values verified | **PASSED** |
| **Rule Engine** | Tests 10–16 | Age 21–65 from DOB, CIBIL ≥700, FOIR ≤50%, boundary conditions | Rejection on threshold breach, approval on satisfaction | **PASSED** |
| **API Endpoints** | Tests 17–22 | `/health`, `/new_chat`, `/chat`, `/orchestrate` | 200 OK responses with proper JSON structure | **PASSED** |
| **Admin Portal** | Tests 23–26 | Form render, customer registration, validation errors | Ineligible entries rejected; valid saved to storage | **PASSED** |
| **Document Engine**| Tests 27–32 | PDF compilation, Jinja2 template render, attachment | Valid binary PDF generated in `sanctions/` | **PASSED** |
| **Dialogue Logic** | Tests 33–47 | Structured queries, check limit, calculate EMI, multi-failure | Exact deterministic answers returned without hallucination | **PASSED** |

*Overall Test Result:* **Ran 47 tests in ~7.6s — 100% OK (0 failures, 0 errors).**

---

## CHAPTER 8: LIMITATIONS AND FUTURE SCOPE

### 8.1 Current Technical Limitations
An objective engineering review identifies several prototype constraints:
1. **Volatile In-Memory Sessions:** Session histories and active customer states are maintained in Python memory dictionaries (`session_histories`, `session_data`); server restarts destroy active states.
2. **Absence of User Authentication & CSRF:** The customer chatbot relies solely on knowing a Customer ID; it does not enforce password, OTP, or multi-factor authentication.
3. **Flat File Storage:** Primary persistence relies on `customers.json`. While resilient for local execution, flat JSON lacks ACID transaction semantics and concurrent write scalability.
4. **Simulated KYC Verification:** Identity verification queries pre-existing database records; it does not perform real-world regulatory Aadhaar biometric e-KYC or live NSDL PAN verification.
5. **Fixed Product Configuration:** Interest rate (12% p.a.), processing fee (₹999), and tenure bounds (48–72 months) are fixed for personal loans rather than dynamically configurable across multiple loan categories.

### 8.2 Future Enhancements
1. **Machine Learning Credit Risk Scoring:** Train supervised classification models (e.g., XGBoost, Logistic Regression) on historical default datasets to generate a complementary Default Probability Score alongside deterministic policy rules.
2. **Government API & DigiLocker e-KYC Integration:** Connect to authentic sandbox APIs for Aadhaar OTP e-KYC and DigiLocker salary/tax statement retrieval.
3. **Live Credit Bureau Gateway:** Integrate REST APIs from credit bureaus (TransUnion CIBIL or Experian) for real-time credit score verification.
4. **Production Database & JWT Authentication:** Migrate from `customers.json` to PostgreSQL with connection pooling and secure JWT / OAuth2 customer authentication.
5. **Omnichannel Containerized Deployment:** Package the application with Docker and Gunicorn for scalable deployment on cloud platforms (AWS/GCP) with WhatsApp Business API connectivity.

---

## CHAPTER 9: CONCLUSION AND REFERENCES

### 9.1 Conclusion
The **AI Loan Approval System** successfully demonstrates how conversational AI and deterministic financial computing can be unified in an enterprise FinTech architecture. By restricting Google Gemini (`gemini-3.5-flash-lite`) to supervisory intent routing and delegating all mathematical logic to audited Python routines, the system eliminates LLM hallucination risks while delivering a friction-free consumer lending experience. The application automates customer verification, underwriting, reducing-balance EMI calculation, PDF sanction document compilation, and email dispatch, providing a robust, transparent, and auditable foundation for modern digital lending solutions.

### 9.2 References
1. Flask Framework Documentation (v3.1.x), Pallets Projects, 2024. [https://flask.palletsprojects.com/](https://flask.palletsprojects.com/)
2. Google Gemini API Documentation, Google Cloud AI, 2024. [https://ai.google.dev/docs](https://ai.google.dev/docs)
3. LangChain Python Documentation (v0.3.x), Harrison Chase et al., 2024. [https://python.langchain.com/](https://python.langchain.com/)
4. Firebase Realtime Database REST API Documentation, Google LLC, 2024. [https://firebase.google.com/docs/reference/rest/database](https://firebase.google.com/docs/reference/rest/database)
5. xhtml2pdf Architecture and Developer Guide (v0.2.x), Dirk Holtwick et al., 2024. [https://xhtml2pdf.readthedocs.io/](https://xhtml2pdf.readthedocs.io/)
6. ReportLab PDF Generation Library User Guide (v4.2), ReportLab Europe Ltd., 2024.
7. Python Standard Library, *'smtplib and email.message Modules'*, Python Software Foundation, 2024.
8. Reserve Bank of India (RBI), *'Guidelines on Digital Lending'*, RBI Notification, 2022.
9. S. Russell and P. Norvig, *'Artificial Intelligence: A Modern Approach'*, 4th ed., Pearson, 2020.

---

## APPENDIX: SETUP AND FORMULAS

### A.1 Important Actuarial Formulas
The mathematical formulas governing the underwriting engine are defined as:

* **Pre-Approved Maximum Credit Limit:**
  $$\text{Limit} = \text{Salary}_{\text{monthly}} \times 15$$

* **Actuarial Monthly Interest Rate:**
  $$r = \frac{\text{Annual Rate}}{12 \times 100} = \frac{12}{1200} = 0.01$$

* **Equated Monthly Installment (EMI):**
  $$\text{EMI} = \frac{P \times r \times (1 + r)^n}{(1 + r)^n - 1}$$
  *Where $P$ is Principal, $r$ is Monthly Rate (0.01), and $n$ is Tenure in months.*

* **Fixed Obligation to Income Ratio (FOIR):**
  $$\text{FOIR} = \frac{\text{Existing Monthly EMIs} + \text{Proposed EMI}}{\text{Salary}_{\text{monthly}}} \times 100 \le 50.0\%$$

* **Age Calculation from Date of Birth:**
  $$\text{Age} = \text{Today}_{\text{year}} - \text{Birth}_{\text{year}} - (\text{Today} < \text{Birthday})$$

### A.2 Installation and Execution Instructions
To run the project in a local development environment:

1. **Repository:** [https://github.com/Abhi-1840/AI-LoanApproval](https://github.com/Abhi-1840/AI-LoanApproval)
2. **Install required packages:**
   ```powershell
   pip install -r requirements.txt
   ```
3. **Configure credentials:**
   Copy `config.json.example` to `config.json` and enter optional Gemini API key, Firebase URL, and Gmail App Password.
4. **Launch primary chatbot server (Port 5000):**
   ```powershell
   python app.py
   ```
   *Access at:* [http://localhost:5000](http://localhost:5000)
5. **Launch administrative portal (Port 5001):**
   ```powershell
   python form_app.py
   ```
   *Access at:* [http://localhost:5001](http://localhost:5001)
6. **Execute automated test suite:**
   ```powershell
   python -m unittest test_loan_system.py -v
   ```
