# SPEC.md — Agentic Freight Billing Auditor (Lite Prototype)
# Timeline: 48-hour solo build

---

## 1. Product Overview & User Story
**Goal:** Demonstrate an end-to-end DataOps workflow that automates freight invoice auditing.

**User Story:** As an operations analyst, I want to upload freight invoices and automatically see whether they violate contract pricing rules, so that I can quickly identify billing leakage and understand the reason for each rejection in plain English.

**The "Raw to Gold" Flow:**
1. **Raw:** Synthetic invoice data representing freight bills.
2. **Structured:** Normalized tabular invoice fields.
3. **Policy Validation:** A deterministic policy engine checks invoice values against contract rates.
4. **Agent Explanation:** An AI explanation layer converts rule violations into plain-English reasoning.
5. **Gold:** A final, audit-ready result showing pass/fail, discrepancy details, and ready-to-send dispute messages.

---

## 2. Scope Constraints
* **In Scope:** Synthetic data generation (CSVs), deterministic Python validation, structured outputs, LLM explanation layer, Streamlit dashboard.
* **Out of Scope:** Real ERP/SAP integration, real PDF OCR, database persistence, multi-agent orchestration frameworks, enterprise authentication.

---

## 3. Data Specifications (Data Contracts)

### 3.1 Master Rate Table (`RateContract`)
The ground truth representing negotiated terms.
* Fields: `lane_id`, `carrier_name`, `origin_zip`, `destination_zip`, `agreed_base_rate_per_lb`, `fuel_surcharge_pct` (decimal), `allowed_accessorials`, `effective_date`, `expiration_date`.

### 3.2 Invoice Dataset (`FreightInvoice`)
50 synthetic invoices. ~30% contain intentional billing errors.
* Fields: `invoice_id`, `carrier_name`, `invoice_date`, `lane_id`, `origin_zip`, `destination_zip`, `shipment_weight_lbs`, `freight_class`, `base_rate_charged`, `fuel_surcharge_pct_charged`, accessorial fee columns, `total_charged`.

---

## 4. Deterministic Policy Engine (The Brain)

### 4.1 Audit Finding Schema (`AuditFinding`)
* `invoice_id` (str)
* `rule_id` (str)
* `severity` ("HIGH", "MEDIUM", "LOW")
* `field_audited` (str)
* `variance_pct` (float)
* `dollar_impact` (float)
* `description` (str)

### 4.2 Core Audit Rules
The engine must iterate through these rules sequentially:
1.  **BASE_RATE_OVERAGE (HIGH):** Charged rate > Contract rate * (1 + tolerance).
2.  **FUEL_SURCHARGE_OVERAGE (HIGH):** Charged fuel % > Contract fuel %.
3.  **UNAUTHORIZED_ACCESSORIAL (MEDIUM):** Billed accessorial not in allowed list.
4.  **DUPLICATE_INVOICE (HIGH):** Same `invoice_id` submitted multiple times (evaluated across full dataset).
5.  **WEIGHT_INFLATION (MEDIUM):** Suspiciously round weights causing >2% variance.
6.  **TOTAL_MISMATCH (LOW):** Line items do not sum to `total_charged`.

---

## 5. LLM Explainer (The Agentic Layer)

### 5.1 System Constraints
* **Role:** The AI is strictly for summarization and explanation. It does *not* calculate pass/fail logic.
* **Input:** Receives only the structured `List[AuditFinding]` and specific contract context.
* **Output:** Must return a JSON matching the `LLMExplanation` Pydantic model.

### 5.2 LLMExplanation Schema
* `summary`: 1-2 sentence executive summary.
* `findings_explained`: Plain English breakdown per finding.
* `total_recovery_opportunity`: Sum of all `dollar_impact`.
* `dispute_recommended`: Boolean.
* `dispute_message`: Ready-to-send email text to the carrier.

### 5.3 Fallback Behavior
If the LLM API fails, the system must degrade gracefully, returning a hardcoded `LLMExplanation` object that displays the raw deterministic findings and flags the AI as unavailable.

---

## 6. Streamlit Dashboard (The UI)
A thin display layer emphasizing clarity and fast feedback.

* **Sidebar:** File uploader and Master Rate Table stats.
* **Metrics Row:** Display "Invoices Audited", "Errors Found", and "$ Recovery Opportunity".
* **Results Table:** Color-coded by severity (High = Red, Medium = Yellow).
* **Agentic Expanders:** Click an invoice to view the AI-generated summary, findings, and a copyable dispute message.

---

## 7. Build Execution Timeline (48 Hours)

**Day 1: Data Ops & Core Logic**
* Hours 0-2: Scaffolding and Pydantic models (`src/engine/models.py`).
* Hours 2-5: Data generation script (`src/scripts/generate_data.py`).
* Hours 5-10: Policy Engine rules and integration (`src/engine/policy.py`).
* Hours 10-12: Unit testing core rules.

**Day 2: The Agentic Vibe & Presentation**
* Hours 12-15: LLM Explainer logic and API integration (`src/agent/explainer.py`).
* Hours 15-20: Streamlit Dashboard UI (`app/dashboard.py`).
* Hours 20-24: End-to-end testing, error handling polish, and README documentation.