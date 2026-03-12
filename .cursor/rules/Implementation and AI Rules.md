# Cursor Rules — Freight Billing Agentic Auditor
# Author: Swastik Singh
# Project: Agentic Freight Billing Auditor (48-hour prototype)

---

## 🧠 Project Identity

You are helping build a **production-grade prototype** of an AI-powered freight invoice auditing system.
The system replicates what Dow Chemical built with Azure AI + Copilot Studio — but using Python, Pandas, and Streamlit.

This is not a toy. Every decision should reflect how a senior engineer at Palantir or Google would approach it:
- Clean separation of concerns
- Deterministic logic before AI
- Explainability over magic
- Testable, modular, readable code

---

## 🏗️ Architecture Rules

### Layered Architecture — ALWAYS enforce this separation:

```
data/          → raw inputs (CSVs, rate tables)
engine/        → deterministic Policy Engine (pure Python, no LLM)
agent/         → LLM explanation layer (calls OpenAI/Anthropic API)
app/           → Streamlit UI (thin layer, calls engine + agent)
tests/         → unit tests for engine rules
scripts/       → data generation, one-off utilities
```

**Never mix layers.** The Policy Engine must never call the LLM. The UI must never contain business logic.

### Data Flow (enforce strictly):
```
Raw CSV Invoice
    → engine/policy_engine.py (deterministic audit)
    → List[AuditFinding] (structured findings)
    → agent/explainer.py (LLM explains findings)
    → ExplainedFinding (human-readable output)
    → app/dashboard.py (display only)
```

---

## 🐍 Python Rules

- Python 3.11+
- Type hints on **every** function signature
- Pydantic models for all data structures (Invoice, RateContract, AuditFinding)
- No raw dicts passed between layers — use dataclasses or Pydantic models
- All functions must have docstrings
- Max function length: 40 lines. If longer, refactor.
- No hardcoded strings — use constants or config
- Use `pathlib.Path` not `os.path`
- Use `logging` not `print` (except in scripts)

### Error Handling:
- Never use bare `except:`
- Always catch specific exceptions
- Log errors with context: `logger.error("audit_invoice failed", extra={"invoice_id": id, "error": str(e)})`
- Return structured error objects, don't raise through the UI layer

---

## 📊 Data Rules

- All monetary values stored as `float`, displayed as `${:.2f}`
- Percentages stored as decimals (0.142, not 14.2)
- Dates as `datetime.date` objects, never strings internally
- Invoice IDs are strings (allow alphanumeric)
- Weight in lbs (float), freight class as string enum
- Tolerance for rate comparison: 1% (configurable in config.py)

### Master Rate Table schema (enforce):
```python
class RateContract(BaseModel):
    lane_id: str
    carrier_name: str
    origin_zip: str
    destination_zip: str
    agreed_base_rate_per_lb: float
    fuel_surcharge_pct: float        # decimal, e.g. 0.142
    allowed_accessorials: list[str]
    effective_date: date
    expiration_date: date
```

### Invoice schema (enforce):
```python
class FreightInvoice(BaseModel):
    invoice_id: str
    carrier_name: str
    invoice_date: date
    lane_id: str
    origin_zip: str
    destination_zip: str
    shipment_weight_lbs: float
    freight_class: str
    base_rate_charged: float
    fuel_surcharge_pct_charged: float
    accessorial_fees: dict[str, float]   # {"liftgate": 150.0}
    total_charged: float
```

---

## 🔍 Policy Engine Rules

- Each audit rule is a **separate function** with signature:
  ```python
  def check_base_rate(invoice: FreightInvoice, contract: RateContract) -> list[AuditFinding]: ...
  ```
- Rules are registered in a list and iterated — never if/elif chains
- Each finding must include:
  - `rule_id`: string constant (e.g., "BASE_RATE_OVERAGE")
  - `severity`: enum ("HIGH", "MEDIUM", "LOW")
  - `charged_value`: what the carrier billed
  - `contract_value`: what was agreed
  - `dollar_impact`: calculated recovery opportunity
  - `description`: one-sentence plain English description
- Dollar impact must always be calculated — never omit it
- Duplicate detection uses invoice_id hash across the full dataset, not per-row

---

## 🤖 LLM / Agent Rules

- LLM is **never** used for math or rule evaluation — only for explanation and language
- Always pass structured findings to the LLM — never raw invoice data
- System prompt must include: role, context, output format, tone constraints
- Output format from LLM must be structured (JSON with defined keys)
- Temperature: 0.2 (we want consistent, professional output — not creative)
- Max tokens: 800 per invoice explanation
- Always include a fallback if API call fails — show raw findings, never crash
- API key loaded from `.env` via `python-dotenv` — never hardcoded, never committed

### LLM Output Schema (enforce):
```python
class LLMExplanation(BaseModel):
    summary: str                    # 1–2 sentence plain English summary
    findings_explained: list[str]   # one explanation per finding
    total_recovery_opportunity: float
    dispute_recommended: bool
    dispute_message: str            # ready-to-send carrier message
    confidence: str                 # "HIGH" | "MEDIUM" | "LOW"
```

---

## 🖥️ Streamlit UI Rules

- UI is a **thin display layer only** — no business logic
- Page config: wide layout, custom page title, favicon emoji 🔍
- Sidebar: upload invoice CSV + show Master Rate Table stats
- Main panel: audit results table + AI explanation per invoice
- Color coding: HIGH severity = red, MEDIUM = yellow, LOW = blue
- Always show summary metrics at top: invoices audited, errors found, $ recovery opportunity
- Use `st.spinner()` during LLM calls
- Use `st.expander()` for full AI explanation per invoice
- Never show raw stack traces to user — catch and display friendly error messages
- Session state for: uploaded file, audit results, explanations

---

## 🧪 Testing Rules

- Every Policy Engine rule must have at least 2 unit tests:
  1. A passing invoice (no error expected)
  2. A failing invoice (error expected, assert finding details)
- Use `pytest`
- No mocking of the Policy Engine in tests — test real logic
- Mock the LLM API in tests — never make real API calls in CI
- Test data lives in `tests/fixtures/`

---

## 📁 File Naming Conventions

```
engine/policy_engine.py       ✅
engine/policyEngine.py        ❌ (no camelCase for files)
agent/llm_explainer.py        ✅
scripts/generate_invoices.py  ✅
app/dashboard.py              ✅
data/master_rate_table.csv    ✅
data/invoices_sample.csv      ✅
```

---

## 🚫 Hard Rules (Never Violate)

1. Never commit `.env` or any file containing API keys
2. Never put business logic in the Streamlit app file
3. Never call the LLM to determine if an invoice has an error
4. Never use `pd.DataFrame` as a data transfer object between layers — convert to Pydantic models first
5. Never hardcode carrier names, lane IDs, or rate values in engine code
6. Never catch and silently swallow exceptions
7. Never use `global` variables

---

## ✅ When Generating Code, Always:

1. Start with the data model (Pydantic schema)
2. Write the pure logic function
3. Write the unit test
4. Then wire into the layer above
5. Add type hints before returning any code
6. Add a one-line comment above every non-obvious block
