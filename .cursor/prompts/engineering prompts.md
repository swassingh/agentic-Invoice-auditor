# PROMPTS.md — Cursor Prompt Playbook
# Agentic Freight Billing Auditor
# Author: Swastik Singh
#
# HOW TO USE THIS FILE:
# Each prompt is ready to copy-paste directly into Cursor Chat or Composer.
# Prompts are ordered by build sequence — follow top to bottom.
# Variables in [BRACKETS] = replace with your actual values.
# Composer prompts = multi-file edits. Chat prompts = single file / Q&A.

---

## PHASE 0 — Project Scaffold

### P0-01 | Generate Full Project Structure
> **Use:** Cursor Composer (`Cmd+I`)

```
Scaffold a Python project called freight_auditor with this exact folder structure:

freight_auditor/
├── data/
├── engine/
│   └── __init__.py
├── agent/
│   └── __init__.py
├── app/
│   └── __init__.py
├── tests/
│   └── fixtures/
└── scripts/

Also create:
- requirements.txt with: pydantic, pandas, streamlit, openai, anthropic, python-dotenv, loguru, pytest
- .gitignore that excludes: .env, __pycache__, .pytest_cache, *.pyc, .streamlit/
- .env.example with placeholder keys: OPENAI_API_KEY, ANTHROPIC_API_KEY, RATE_TOLERANCE_PCT=0.01, LOG_LEVEL=INFO
- A minimal README.md with title "Agentic Freight Billing Auditor" and one-line description

Do not write any application code yet.
```

---

## PHASE 1 — Data Models

### P1-01 | Generate All Pydantic Models
> **Use:** Cursor Composer (`Cmd+I`) → target `engine/models.py`

```
Create engine/models.py with the following Pydantic V2 models.
Use `from pydantic import BaseModel` and `from datetime import date`.
Add a docstring to every model and every field.

Models to create:

1. FreightClass — string enum with values: "50", "55", "60", "65", "70", "77.5", 
   "85", "92.5", "100", "110", "125", "150", "175", "200", "250", "300", "400", "500"

2. Severity — string enum with values: HIGH, MEDIUM, LOW

3. RateContract:
   - lane_id: str
   - carrier_name: str
   - origin_zip: str
   - destination_zip: str
   - agreed_base_rate_per_lb: float ($/lb)
   - fuel_surcharge_pct: float (decimal, e.g. 0.142)
   - allowed_accessorials: list[str] (e.g. ["liftgate", "residential"])
   - effective_date: date
   - expiration_date: date

4. FreightInvoice:
   - invoice_id: str
   - carrier_name: str
   - invoice_date: date
   - lane_id: str
   - origin_zip: str
   - destination_zip: str
   - shipment_weight_lbs: float
   - freight_class: FreightClass
   - base_rate_charged: float
   - fuel_surcharge_pct_charged: float (decimal)
   - accessorial_fees: dict[str, float] (e.g. {"liftgate": 150.0})
   - total_charged: float

5. AuditFinding:
   - invoice_id: str
   - rule_id: str (e.g. "FUEL_SURCHARGE_OVERAGE")
   - severity: Severity
   - field_audited: str
   - charged_value: float
   - contract_value: float
   - variance_pct: float
   - dollar_impact: float
   - description: str (one sentence plain English)

6. LLMExplanation:
   - invoice_id: str
   - summary: str
   - findings_explained: list[str]
   - total_recovery_opportunity: float
   - dispute_recommended: bool
   - dispute_message: str
   - confidence: Severity

7. AuditResult:
   - invoice: FreightInvoice
   - findings: list[AuditFinding]
   - explanation: LLMExplanation | None
   
   Add a computed property:
   - total_dollar_impact: float → sum of all finding.dollar_impact
   - has_errors: bool → len(findings) > 0
   - max_severity: Severity | None → highest severity across findings

Add a module-level __all__ list.
```

### P1-02 | Validate Models Work
> **Use:** Cursor Chat (`Cmd+L`)

```
Write a small test in tests/test_models.py that:
1. Instantiates one FreightInvoice with realistic fake data
2. Instantiates one RateContract
3. Instantiates one AuditFinding with HIGH severity
4. Asserts that AuditResult.total_dollar_impact computes correctly
5. Asserts that AuditResult.max_severity returns HIGH

Use pytest. No mocking needed — just test the models directly.
Run with: pytest tests/test_models.py -v
```

---

## PHASE 2 — Synthetic Data Generation

### P2-01 | Generate Master Rate Table
> **Use:** Cursor Composer → target `scripts/generate_rate_table.py`

```
Create scripts/generate_rate_table.py that generates and saves 
data/master_rate_table.csv.

Requirements:
- 3 carriers: "FastFreight Inc", "PrimeHaul LLC", "TransCore Logistics"
- 10 lanes (origin_zip → destination_zip pairs using real US zip codes 
  for cities like Chicago, Dallas, Atlanta, LA, Seattle, NYC, Miami, Denver, Phoenix, Boston)
- Each carrier covers all 10 lanes = 30 total contracts
- agreed_base_rate_per_lb: realistic range $2.50–$4.50
- fuel_surcharge_pct: 0.142 (14.2%) for all — this is the "correct" rate 
  we'll use to inject errors in invoices
- allowed_accessorials: vary by lane — some have ["liftgate", "residential"], 
  some have ["inside_delivery"], some have [] (no accessorials allowed)
- effective_date: 2024-01-01
- expiration_date: 2025-12-31

Output columns must exactly match the RateContract Pydantic model fields.
allowed_accessorials should be stored as pipe-delimited string in CSV: "liftgate|residential"

Print: "Generated [N] rate contracts → data/master_rate_table.csv"
```

### P2-02 | Generate Synthetic Invoices with Errors
> **Use:** Cursor Composer → target `scripts/generate_invoices.py`

```
Create scripts/generate_invoices.py that generates data/invoices_sample.csv.

This script generates 50 synthetic freight invoices.
Load the rate table from data/master_rate_table.csv first.
Base each invoice on a real contract from the rate table (pick randomly).

Error injection rules — inject exactly these errors:
- 5 invoices: fuel_surcharge_pct_charged = random.uniform(0.18, 0.22) instead of 0.142
- 4 invoices: base_rate_charged = contract_rate * random.uniform(1.08, 1.15)
- 4 invoices: charge an accessorial not in the contract's allowed list ($75–$200)
- 2 invoices: duplicate — copy an existing invoice_id exactly (different row)
- 3 invoices: weight inflated — round up to nearest 100 lbs, add 3–8%
- 2 invoices: total_charged ≠ calculated total (off by $15–$80)
- 30 invoices: perfectly clean — match contract exactly

For clean invoices:
- total_charged = (weight * base_rate) * (1 + fuel_surcharge_pct) + sum(accessorials)
- accessorials: 60% of clean invoices have $0 accessorials, 40% have one allowed accessorial

invoice_id format: "INV-{year}-{4-digit-sequence}" e.g. "INV-2024-0001"
invoice_date: random dates in 2024

Shuffle the 50 rows before saving so errors aren't all at the bottom.

Print summary:
"Generated 50 invoices → data/invoices_sample.csv"
"Error breakdown: {error_type: count}"
```

---

## PHASE 3 — Policy Engine

### P3-01 | Build Policy Engine Core
> **Use:** Cursor Composer → target `engine/policy_engine.py`

```
Create engine/policy_engine.py — the deterministic audit engine.

Import models from engine/models.py.
Load RATE_TOLERANCE_PCT from environment variable (default 0.01).

Implement these 6 audit rule functions. Each must:
- Accept (invoice: FreightInvoice, contract: RateContract) 
- Return list[AuditFinding] (empty list if no violation)
- Have a full docstring explaining the rule
- Use a RULE_ID string constant at the top of each function

Rule 1 — check_base_rate:
  RULE_ID = "BASE_RATE_OVERAGE"  
  Severity: HIGH
  If base_rate_charged > agreed_base_rate_per_lb * (1 + tolerance):
    dollar_impact = (base_rate_charged - agreed_base_rate_per_lb) * shipment_weight_lbs

Rule 2 — check_fuel_surcharge:
  RULE_ID = "FUEL_SURCHARGE_OVERAGE"
  Severity: HIGH
  If fuel_surcharge_pct_charged > fuel_surcharge_pct * (1 + tolerance):
    base_freight = weight * base_rate_charged
    dollar_impact = (charged_pct - contract_pct) * base_freight

Rule 3 — check_unauthorized_accessorials:
  RULE_ID = "UNAUTHORIZED_ACCESSORIAL"
  Severity: MEDIUM
  For each key in invoice.accessorial_fees where value > 0:
    If key not in contract.allowed_accessorials:
      dollar_impact = accessorial amount charged
      Create one AuditFinding per unauthorized accessorial

Rule 4 — check_total_mismatch:
  RULE_ID = "TOTAL_MISMATCH"
  Severity: LOW
  calculated = (weight * base_rate_charged) * (1 + fuel_surcharge_pct_charged) + sum(accessorial_fees.values())
  If abs(total_charged - calculated) > 1.00:
    dollar_impact = abs(total_charged - calculated)

Rule 5 — check_weight_inflation:
  RULE_ID = "WEIGHT_INFLATION"
  Severity: MEDIUM
  If weight % 100 == 0 (suspiciously round):
    estimated_actual = weight * 0.97
    if (weight - estimated_actual) / weight > 0.02:
      dollar_impact = (weight - estimated_actual) * base_rate_charged

Then implement:

check_duplicate_invoices(invoices: list[FreightInvoice]) -> dict[str, list[AuditFinding]]:
  RULE_ID = "DUPLICATE_INVOICE"
  Severity: HIGH
  Find invoice_ids that appear more than once
  Flag all occurrences after the first
  dollar_impact = total_charged of the duplicate invoice
  Return dict mapping invoice_id → findings

AUDIT_RULES = [check_base_rate, check_fuel_surcharge, check_unauthorized_accessorials, 
               check_total_mismatch, check_weight_inflation]

Main function:
def audit_invoices(
    invoices: list[FreightInvoice],
    rate_table: dict[tuple[str, str], RateContract],
) -> dict[str, list[AuditFinding]]:
  For each invoice, lookup contract by (lane_id, carrier_name).
  Run all AUDIT_RULES.
  Run duplicate check across full invoice list.
  Return dict: invoice_id → list[AuditFinding]
  Log a warning if no contract found for an invoice (skip it).

Also add:
def load_rate_table(path: Path) -> dict[tuple[str, str], RateContract]:
  Load CSV, parse allowed_accessorials by splitting on "|"
  Return dict keyed by (lane_id, carrier_name)

def load_invoices(path: Path) -> list[FreightInvoice]:
  Load CSV, parse accessorial columns into accessorial_fees dict
  Return list[FreightInvoice]
```

### P3-02 | Unit Tests for Policy Engine
> **Use:** Cursor Composer → target `tests/test_policy_engine.py`

```
Create tests/test_policy_engine.py with pytest unit tests for the Policy Engine.

Load fixture helpers from tests/fixtures/ — create minimal fixture CSVs as needed.

For each of the 6 rules, write exactly 2 tests:
  test_[rule]_clean: invoice matches contract → assert empty findings list
  test_[rule]_violation: invoice violates contract → assert:
    - exactly 1 finding returned (or expected count for accessorials)
    - finding.rule_id == correct RULE_ID constant
    - finding.severity == correct severity
    - finding.dollar_impact > 0
    - finding.dollar_impact is approximately correct (within $0.01)

Additional tests:
  test_duplicate_detection: 3 invoices, 2 with same ID → 1 finding, first not flagged
  test_audit_invoices_full: load fixtures, run full audit, assert correct error count
  test_no_contract_found: invoice with unknown lane_id → logged warning, no crash

Use pytest fixtures for reusable invoice/contract objects.
All tests must pass with: pytest tests/test_policy_engine.py -v
```

### P3-03 | CLI Smoke Test
> **Use:** Cursor Chat

```
Add an if __name__ == "__main__": block to engine/policy_engine.py that:
1. Loads data/master_rate_table.csv
2. Loads data/invoices_sample.csv
3. Runs audit_invoices()
4. Prints a summary table to terminal:
   - Total invoices audited
   - Total findings
   - Findings by rule_id and count
   - Total dollar impact
   - Top 5 invoices by dollar impact

Format dollar amounts as $XX,XXX.XX
Use loguru for all logging (not print except for the summary table).
```

---

## PHASE 4 — LLM Explainer

### P4-01 | Build LLM Explainer
> **Use:** Cursor Composer → target `agent/llm_explainer.py`

```
Create agent/llm_explainer.py — the LLM explanation layer.

Import: LLMExplanation, AuditFinding, FreightInvoice, RateContract from engine/models.py
Use OpenAI client (openai>=1.0.0 SDK). Load OPENAI_API_KEY from environment via dotenv.

SYSTEM_PROMPT = """
You are an expert freight billing auditor with 20 years of experience.
You review flagged invoice errors and explain them to non-technical finance managers.
Be factual, specific, and always cite exact dollar amounts and rate values.
Tone: professional, direct. Not accusatory toward carriers — state facts only.
Your dispute message should be addressed to the carrier, factual, and request a credit or correction.
Respond ONLY with valid JSON. No markdown, no backticks, no preamble.
"""

USER_PROMPT_TEMPLATE — build dynamically with:
- Invoice ID, carrier, lane, date, total charged
- Contract terms (base rate, fuel surcharge, allowed accessorials)
- Each finding: rule_id, charged_value, contract_value, dollar_impact, description
- Requested output schema (paste LLMExplanation fields as JSON schema)

Main function:
def explain_findings(
    invoice: FreightInvoice,
    contract: RateContract,
    findings: list[AuditFinding],
) -> LLMExplanation:
  - Model: gpt-4o-mini (fast, cheap, good enough for structured output)
  - Temperature: 0.2
  - Max tokens: 800
  - Parse response as JSON → validate against LLMExplanation schema
  - On ANY exception: return fallback LLMExplanation with:
      summary = "AI explanation unavailable. See raw findings below."
      findings_explained = [f.description for f in findings]
      total_recovery_opportunity = sum(f.dollar_impact for f in findings)
      dispute_recommended = any(f.severity == "HIGH" for f in findings)
      dispute_message = "[Generate manually — AI service unavailable]"
      confidence = "LOW"
  - Log all API calls with invoice_id and token usage

Also add:
def explain_batch(
    audit_results: dict[str, list[AuditFinding]],
    invoices: list[FreightInvoice],
    rate_table: dict[tuple[str, str], RateContract],
) -> dict[str, LLMExplanation]:
  Only call LLM for invoices with findings (skip clean invoices).
  Return dict: invoice_id → LLMExplanation
```

### P4-02 | Test LLM Explainer with Mock
> **Use:** Cursor Chat

```
Write a pytest test in tests/test_llm_explainer.py that tests explain_findings()
without making a real API call.

Mock the OpenAI client using unittest.mock.patch.
The mock should return a realistic LLMExplanation JSON string as the API response.

Test cases:
1. test_explain_valid_findings: mock returns valid JSON → assert LLMExplanation parsed correctly
2. test_explain_api_failure: mock raises openai.APIError → assert fallback returned, no crash
3. test_explain_invalid_json: mock returns malformed JSON → assert fallback returned, no crash
4. test_explain_clean_invoice: findings=[] → function should return None or skip (your design choice, be consistent)

Assert that the fallback always has dispute_recommended based on severity logic, not hardcoded.
```

---

## PHASE 5 — Orchestration Layer

### P5-01 | Build Audit Runner
> **Use:** Cursor Composer → target `app/audit_runner.py`

```
Create app/audit_runner.py — the orchestration layer between engine, agent, and UI.

This module has zero UI code and zero business logic. 
It only coordinates calls between the Policy Engine and LLM Explainer.

Implement:

def run_full_audit(
    invoices_path: Path,
    rate_table_path: Path,
    explain: bool = True,
) -> list[AuditResult]:
  1. Load invoices and rate table using engine/policy_engine.py loaders
  2. Run audit_invoices() → findings dict
  3. If explain=True: run explain_batch() → explanations dict
  4. Assemble list[AuditResult] — one per invoice
  5. Sort by total_dollar_impact descending
  6. Return list

def get_summary_stats(results: list[AuditResult]) -> dict:
  Return:
  {
    "total_invoices": int,
    "invoices_with_errors": int,
    "clean_invoices": int,
    "total_findings": int,
    "total_recovery_opportunity": float,
    "findings_by_severity": {"HIGH": int, "MEDIUM": int, "LOW": int},
    "findings_by_rule": {rule_id: count},
    "top_carriers_by_error_amount": [(carrier_name, total_$), ...]  # top 3
  }

def results_to_dataframe(results: list[AuditResult]) -> pd.DataFrame:
  Return a flat DataFrame with one row per invoice:
  invoice_id, carrier_name, invoice_date, total_charged, 
  findings_count, max_severity, total_dollar_impact, 
  dispute_recommended, status ("FLAGGED" | "CLEAN")

Use loguru for logging. No streamlit imports here.
```

---

## PHASE 6 — Streamlit Dashboard

### P6-01 | Build Streamlit Dashboard
> **Use:** Cursor Composer → target `app/dashboard.py`

```
Create app/dashboard.py — the Streamlit UI layer.

Import only from: app/audit_runner.py, engine/models.py, standard libs.
No business logic here.

Page config:
  st.set_page_config(page_title="Freight Billing Auditor", page_icon="🔍", layout="wide")

Sidebar:
  - App title + subtitle
  - st.file_uploader for invoice CSV (type=["csv"])
  - Toggle: "Enable AI Explanations" (default: True)
  - Severity filter: multiselect ["HIGH", "MEDIUM", "LOW"] (default: all selected)
  - Show rate table stats: # carriers, # lanes, date range
  - "Run Audit" button (primary)

Main area — show only after audit runs:

Section 1: Summary Metrics (use st.columns(5))
  - Invoices Audited
  - Errors Found  
  - 💰 Recovery Opportunity ($XX,XXX)
  - 🚨 High Severity Count
  - ✅ Clean Invoices

Section 2: Audit Results Table
  - Use results_to_dataframe() from audit_runner
  - Filter by selected severities
  - Color rows: HIGH=red bg, MEDIUM=yellow, LOW=blue, CLEAN=green
  - Use st.dataframe with column config for dollar formatting

Section 3: AI Explanations
  - For each flagged invoice (sorted by dollar_impact desc):
    st.expander with:
      - Header: "{invoice_id} | {carrier} | ${impact:,.2f} recovery | {severity} severity"
      - Summary text
      - Findings as bullet list
      - Divider
      - Dispute message in st.code block
      - st.button("📋 Copy", key=f"copy_{invoice_id}") 
        → st.toast("Copied!") + st.session_state clipboard trick

State management:
  - Use st.session_state to store: audit_results, summary_stats, last_upload_name
  - Don't re-run audit if same file is uploaded again

Error handling:
  - If no rate table found at data/master_rate_table.csv: show st.error with instructions
  - If uploaded CSV has wrong columns: show st.error with expected column list
  - If LLM API key missing: show st.warning, disable AI toggle, still show raw findings

Add a footer: "Built by Swastik Singh | Agentic Freight Billing Auditor Prototype"
```

### P6-02 | Polish Dashboard Styling
> **Use:** Cursor Chat

```
Add custom CSS to app/dashboard.py using st.markdown with unsafe_allow_html=True.

Style these elements:
1. Metric cards: add subtle border and rounded corners
2. Table rows: apply background colors based on severity column value
   HIGH = rgba(255, 99, 99, 0.15)
   MEDIUM = rgba(255, 193, 7, 0.15)  
   LOW = rgba(13, 110, 253, 0.15)
   CLEAN = rgba(25, 135, 84, 0.10)
3. Expander headers for HIGH severity: bold red text
4. The dispute message code block: monospace, slightly larger font
5. Footer: centered, muted gray text

Keep it minimal and professional — this is an enterprise tool, not a marketing page.
Do not add any animations or decorative elements.
```

---

## PHASE 7 — Debugging & Fixes

### P7-01 | Debug a Failing Test
> **Use:** Cursor Chat

```
Here is a failing pytest test:

[PASTE TEST NAME AND FUNCTION]

Here is the traceback:

[PASTE FULL TRACEBACK]

Here is the relevant source function:

[PASTE FUNCTION]

Do not rewrite the entire function.
1. Identify the exact root cause (one sentence)
2. Show me the minimal code change to fix it
3. Explain why your fix is correct
4. Check if this same bug could affect any other rules in the engine
```

### P7-02 | Fix a Data Loading Issue
> **Use:** Cursor Chat

```
My invoice CSV is loading incorrectly. Here is the issue:

[DESCRIBE WHAT'S WRONG — e.g., "accessorial_fees dict is empty for all rows"]

Here is my load_invoices() function:

[PASTE FUNCTION]

Here is a sample of the CSV (first 3 rows):

[PASTE CSV ROWS]

Fix only the loading logic. Do not change the Pydantic model or anything else.
```

### P7-03 | Fix LLM JSON Parsing Error
> **Use:** Cursor Chat

```
My LLM explainer is failing to parse the API response as JSON.

Here is the raw API response content:

[PASTE RESPONSE]

Here is my current parsing code:

[PASTE PARSING BLOCK]

Here is the error:

[PASTE ERROR]

Fix the parsing. Make it robust to:
- Extra whitespace or newlines
- JSON wrapped in ```json ... ``` markdown code fences
- Missing optional fields (use defaults)
- Slightly wrong key names (use fuzzy match if needed)

Do not change the LLMExplanation Pydantic model.
```

---

## PHASE 8 — Enhancement Prompts (Post-MVP)

### P8-01 | Add PDF Invoice Support
> **Use:** Cursor Composer

```
Add PDF invoice parsing to the ingestion layer.

Create engine/pdf_parser.py using pdfplumber (add to requirements.txt).

Implement:
def parse_pdf_invoice(path: Path) -> FreightInvoice:
  Extract these fields from a typical carrier invoice PDF:
  - Invoice number (usually labeled "Invoice #" or "Invoice No.")
  - Carrier name (usually in header/letterhead)
  - Invoice date
  - Origin and destination (look for "Ship From" / "Ship To" or "Origin" / "Destination")
  - Weight
  - Freight charges line item
  - Fuel surcharge line item
  - Any accessorial line items
  - Total amount due

Return a FreightInvoice Pydantic model.
Raise ValueError with descriptive message if required fields cannot be extracted.
Add a test in tests/test_pdf_parser.py using a small synthetic PDF created with reportlab.
```

### P8-02 | Add Carrier Performance Analytics
> **Use:** Cursor Composer

```
Add a new tab to the Streamlit dashboard called "Carrier Analytics".

Create app/analytics.py with:

def carrier_error_summary(results: list[AuditResult]) -> pd.DataFrame:
  Columns: carrier_name, total_invoices, error_rate_pct, 
           total_recovery_$, most_common_error, avg_error_per_invoice

def plot_recovery_by_carrier(df: pd.DataFrame) -> plotly figure:
  Horizontal bar chart: carrier on Y axis, total recovery $ on X axis
  Color bars by error_rate (red=high, green=low)

def plot_error_trend(results: list[AuditResult]) -> plotly figure:
  Line chart: invoice_date on X axis, cumulative recovery $ on Y axis
  One line per carrier

In dashboard.py, add a second tab using st.tabs(["🔍 Audit Results", "📈 Carrier Analytics"])
Render the analytics tab using the functions above.
Use plotly (add to requirements.txt).
```

### P8-03 | Add Export to Excel
> **Use:** Cursor Chat

```
Add an "Export to Excel" button to the Streamlit dashboard.

When clicked, generate an Excel file with 3 sheets:
1. "Summary" — the summary stats dict as a formatted table
2. "Audit Results" — the full results DataFrame
3. "Dispute Messages" — one row per flagged invoice with:
   invoice_id, carrier_name, total_charged, dollar_impact, dispute_message

Use openpyxl (add to requirements.txt).
Format dollar columns with $ and 2 decimal places.
Highlight HIGH severity rows in red, MEDIUM in yellow.
Use st.download_button to trigger the download — do not save to disk.
```

### P8-04 | Add Confidence Scoring to Policy Engine
> **Use:** Cursor Composer

```
Add a confidence_score field (float, 0.0–1.0) to AuditFinding.

For each rule, calculate confidence based on:
- BASE_RATE_OVERAGE: 1.0 if variance > 5%, 0.8 if 2–5%, 0.6 if 1–2%
- FUEL_SURCHARGE_OVERAGE: same thresholds
- UNAUTHORIZED_ACCESSORIAL: 1.0 always (binary — either it's in the contract or not)
- TOTAL_MISMATCH: 0.7 always (could be rounding)
- WEIGHT_INFLATION: 0.6 always (heuristic, not definitive)
- DUPLICATE_INVOICE: 1.0 always (exact ID match)

Update the LLM system prompt to include confidence_score in findings context.
Update the Streamlit table to show a confidence column with a colored badge.
Update unit tests to assert confidence_score is set correctly.
```

---

## UTILITY PROMPTS — Use Anytime

### PU-01 | Add Type Hints to Existing Function
```
Add complete Python type hints to this function.
Use modern syntax (list[x] not List[x], dict[k,v] not Dict[k,v]).
Do not change any logic.

[PASTE FUNCTION]
```

### PU-02 | Add Docstring
```
Write a Google-style docstring for this function.
Include: one-line summary, Args section with types and descriptions, 
Returns section, Raises section if applicable.

[PASTE FUNCTION]
```

### PU-03 | Refactor Long Function
```
This function is too long. Refactor it into smaller functions.
Rules:
- Each sub-function should do exactly one thing
- Keep the original function as the public interface — just have it call the sub-functions
- Do not change any logic or return values
- Add type hints and docstrings to each new function
- Keep all sub-functions in the same file unless they clearly belong elsewhere

[PASTE FUNCTION]
```

### PU-04 | Write a Quick README Section
```
Write a README.md section called "How It Works" for this project.

Audience: a technical hiring manager or senior engineer at a data/AI company.
Tone: confident, concise, no fluff.
Format: 3 paragraphs max + one ASCII architecture diagram.

Cover:
1. The business problem (freight invoice overbilling)
2. The technical approach (Policy Engine → LLM explainer → Streamlit UI)
3. The key design decision (deterministic rules, not AI, for audit logic)

Do not use bullet points. Write in prose.
```

### PU-05 | Generate Sample Data for a New Lane
```
Generate 5 rows of CSV data for invoices_sample.csv for a new lane:
Origin: [ZIP]
Destination: [ZIP]  
Carrier: [NAME]
Base rate: $[X.XX]/lb
Fuel surcharge: 14.2%

Include:
- 3 clean invoices
- 1 with a fuel surcharge overage (charge 17%)
- 1 with an unauthorized liftgate fee of $125

Match the exact column format of the existing invoices_sample.csv.
```

---

## DAY 1 TALKING POINTS PROMPT

### PT-01 | Prepare Your 60-Second Explanation
```
I built a prototype of an agentic freight billing auditor this week before starting 
a new job at an industrial company doing DataOps and AI work.

Here is what I built:
[PASTE your final README or architecture description]

Write me three versions of a 60-second verbal explanation of this project:
1. For a technical peer (senior engineer / data scientist)
2. For a business stakeholder (finance manager / operations VP)  
3. For an executive (CTO / CDO)

Each version should emphasize what matters to that audience:
- Technical: architecture, design decisions, tech stack
- Business: problem solved, dollar impact, workflow improvement
- Executive: ROI potential, scalability, risk reduction

Keep each version under 120 words. Use confident, natural language — not buzzwords.
```