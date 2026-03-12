# Gemini Rules — Agentic Freight Auditor (48-Hour MVP)

## 🎯 Problem Definition & Impact
* **Problem:** Manual auditing of freight P&L against massive contract datasets is slow, error-prone, and causes financial leakage.
* **Beneficiary:** Finance Operations & P&L Owners.
* **Impact:** Reclaim lost capital through scalable, automated discrepancy detection.
* **MVP:** A deterministic Python Policy Engine wrapped in a Streamlit UI, utilizing an LLM to explain billing rejections in plain English.
* **Risks:** LLM hallucinations regarding contract terms; UI state bleeding into core logic.

## 🏗️ Architecture & Data Flow
The system operates on a strict "Raw to Gold" DataOps pipeline.

1.  **Strict Layer Isolation:** * `data/` -> Synthetic generation and static rate tables.
    * `src/engine/` -> Deterministic Python Policy Engine. **Zero LLM calls here.**
    * `src/agent/` -> LLM explanation layer. Consumes structured findings.
    * `app/` -> Streamlit UI. Thin display layer only.
2.  **Data Contracts First:** Never pass raw dictionaries or `pd.DataFrame` between layers. All data traversing layers MUST be cast to Pydantic models (`FreightInvoice`, `AuditFinding`, `LLMExplanation`).
3.  **One-Way Flow:** UI -> Engine -> Agent -> UI. The UI must never contain business logic.

## 🐍 Operational Excellence & Maintainability
1.  **Clarity over Cleverness:** Write modular, typed Python (3.11+). Maximum function length is 40 lines.
2.  **Explicit Business Rules:** Policy checks must return measurable logic. 
    * *Bad:* "Invoice rejected."
    * *Good:* "Fuel surcharge (0.18) exceeds contract maximum (0.14)."
3.  **Fail Loudly:** If required columns are missing during ingestion, raise a clear error identifying the missing fields. Do not silently continue.
4.  **Logging:** Catch specific exceptions and log with context (e.g., `logger.error("audit failed", extra={"invoice_id": id})`). Return structured error objects to the UI.

## 🧠 Verification & The Agentic Layer
1.  **AI Boundaries:** The LLM is for explanation, summarization, and human-readable formatting ONLY. It is strictly prohibited from computing pass/fail logic or calculating dollar impacts.
2.  **Prompt Constraints:** Pass structured JSON findings to the LLM. Set temperature to 0.2 for professional, grounded outputs.
3.  **Output Schema:** The LLM must return a structured JSON response matching the `LLMExplanation` Pydantic model:
    * `summary`: 1-2 sentence plain English explanation.
    * `findings_explained`: List of explanations per violation.
    * `dispute_message`: Ready-to-send carrier message.

## 🖥️ UI / Streamlit Standards
1.  **Purpose:** Make the workflow obvious. Upload -> Audit -> Explain.
2.  **Visuals:** Use clear color coding for severity (High = Red, Medium = Yellow). Display summary metrics (Invoices Audited, Total Recovery Opportunity) at the top.
3.  **Resilience:** Use `st.spinner()` for LLM calls. Never expose raw stack traces to the user.

## 📁 Required Directory Structure
```text
├── app/
│   └── dashboard.py          # Thin UI layer
├── data/
│   ├── generated_invoices.csv
│   └── master_rates.csv
├── src/
│   ├── agent/
│   │   └── explainer.py      # LLM API calls & schemas
│   ├── engine/
│   │   ├── models.py         # Pydantic data contracts
│   │   └── policy.py         # Deterministic rules
│   └── scripts/
│       └── generate_data.py  # Synthetic data creator
└── tests/
    └── test_policy.py        # Unit tests for exact matches and overcharges