# RULES.md

## Purpose
These are the standing engineering rules for this repository. Follow them for every change unless explicitly overridden in SPEC.md.

---

## Project Context
This repository is a lightweight prototype of an Agentic Invoice Auditor.

Goal:
- Simulate an industrial DataOps workflow
- Validate freight invoices against a master rate table
- Detect billing discrepancies using deterministic policy checks
- Provide human-readable AI explanations for why an invoice is rejected
- Expose the workflow through a Streamlit interface

This is a prototype, but it should be built in a way that demonstrates production-minded engineering.

---

## Core Engineering Principles

### 1. Prefer clarity over cleverness
- Write simple, readable Python.
- Avoid overly abstract patterns unless they clearly improve maintainability.
- Make business logic easy to trace.

### 2. Keep logic deterministic first
- The policy engine must be rule-based and deterministic.
- AI should explain decisions, not replace validation logic.
- Never rely on an LLM to determine whether an invoice passed or failed.

### 3. Separate concerns cleanly
Keep these layers separate:
- data generation
- invoice parsing/loading
- policy validation
- explanation generation
- UI rendering

Do not mix validation logic directly into Streamlit UI code.

### 4. Production-minded structure
Even though this is a prototype:
- use modular files
- use typed functions where practical
- add docstrings on important functions
- keep data contracts explicit
- avoid notebook-only logic

### 5. Make business rules explicit
Every policy check should have:
- a clear rule name
- a simple explanation
- measurable comparison logic
- structured output

Bad example:
- "invoice looks suspicious"

Good example:
- "fuel surcharge exceeds contract maximum by 3.0 percentage points"

### 6. Optimize for explainability
Every rejection should be explainable in plain English.
Outputs should be understandable by:
- a business analyst
- an operations manager
- a non-technical stakeholder

### 7. Fail loudly on bad data
If required columns are missing or malformed:
- raise a clear error
- identify the missing field(s)
- do not silently continue

### 8. Use realistic naming
Use business-friendly field names like:
- invoice_id
- carrier
- origin
- destination
- shipment_weight_lb
- contract_base_rate
- billed_base_rate
- contract_fuel_surcharge_pct
- billed_fuel_surcharge_pct
- accessorial_fee
- total_billed_amount

Avoid vague names like:
- x
- val
- temp_data

---

## Architecture Rules

### Directory expectations
Use a structure close to:

src/
  data_generation/
  data_processing/
  policy_engine/
  agent/
  utils/

app/
  streamlit_app.py

data/
  sample/
  generated/

tests/

### File responsibilities
- policy logic lives in src/policy_engine/
- explanation logic lives in src/agent/
- UI logic lives in app/
- generated fake data lives in data/generated/

Do not place core business logic only in app.py.

---

## Python Rules

### Style
- Follow PEP 8
- Use descriptive names
- Prefer small functions
- Avoid functions longer than ~50 lines unless justified

### Typing
Use type hints on public functions whenever practical.

### Data handling
Prefer pandas for tabular transformations.
Do not introduce heavyweight frameworks unless necessary.

### Logging
Use lightweight logging or clear print statements for prototype debugging.
Do not over-engineer observability for this repo.

---

## Validation Rules

The policy engine should support checks such as:
- base rate mismatch
- fuel surcharge mismatch
- lane/route mismatch
- duplicate invoice detection
- accessorial fee anomalies
- total billed amount inconsistency

Each validation result should return structured fields such as:
- invoice_id
- status
- violation_type
- expected_value
- actual_value
- variance
- severity
- explanation

---

## AI / LLM Rules

### Role of AI
The AI layer is for:
- summarization
- explanation
- rejection reasoning in natural language

The AI layer is not for:
- computing pass/fail
- replacing business rules
- inventing contract terms

### Prompting
Prompts should:
- stay grounded in structured validation outputs
- avoid hallucination-prone open-ended instructions
- clearly state the expected explanation format

### Output discipline
AI explanations should:
- be concise
- cite the actual rule violation
- mention expected vs actual values
- avoid legal or compliance claims beyond the provided data

---

## Streamlit Rules

### UI goals
The app should:
- feel clean and credible
- make the workflow obvious
- allow invoice upload or row selection
- show validation results clearly
- display AI explanations separately from raw audit results

### UX priorities
Prioritize:
1. clarity
2. fast feedback
3. interpretable outputs

Do not add flashy UI elements that obscure the core workflow.

---

## Testing Rules

At minimum, test:
- exact match passes
- overcharge is detected
- fuel surcharge violation is detected
- missing columns trigger a clear error
- explanation payloads are generated for failed invoices

Prefer a few strong tests over many shallow tests.

---

## Documentation Rules

README and in-code comments should explain:
- what the system does
- how the DataOps flow works from raw to gold
- why policy logic is deterministic
- where AI is used and where it is not used

This repo should be understandable by someone reviewing it in under 5 minutes.

---

## Non-Goals
Do not overbuild:
- no need for enterprise auth
- no need for distributed processing
- no need for real PDF OCR in v1 unless explicitly requested
- no need for database persistence in v1
- no need for agent orchestration frameworks unless they add obvious value

---

## Definition of Good Output
A good output:
- is correct
- is modular
- is easy to explain
- demonstrates industrial AI/DataOps thinking
- looks credible to an engineering manager or solutions architect