# SPEC.md — Project Specification
# Agentic Freight Billing Auditor (Lite Prototype)
# Author: Swastik Singh
# Timeline: 48-hour solo build

---

## 1. Problem Statement

Large industrial companies spend billions annually on freight. Carriers routinely overbill —
wrong fuel surcharges, unauthorized accessorial fees, incorrect lane rates, duplicate invoices,
and weight inflation. Manual auditing catches only a fraction of errors.

**This system automates freight invoice auditing end-to-end:**
ingesting invoices → comparing against contract rates → flagging errors → explaining findings in plain English.

---

## 2. System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    STREAMLIT DASHBOARD                   │
│         Upload → Audit → Explain → Recover $            │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │      audit_runner.py    │  ← orchestration layer
          └────────────┬────────────┘
               ┌───────┴───────┐
               ▼               ▼
    ┌──────────────────┐  ┌──────────────────┐
    │  policy_engine   │  │  llm_explainer   │
    │  (deterministic) │  │  (Claude/GPT API)│
    └────────┬─────────┘  └────────┬─────────┘
             │                     │
    ┌────────▼─────────┐  ┌────────▼─────────┐
    │ List[AuditFinding]│  │  LLMExplanation  │
    └──────────────────┘  └──────────────────┘
             │
    ┌────────▼─────────┐
    │   models.py      │  ← Pydantic schemas (shared)
    │   FreightInvoice │
    │   RateContract   │
    │   AuditFinding   │
    └──────────────────┘
             │
    ┌────────▼─────────┐
    │   data/          │
    │   invoices.csv   │
    │   rate_table.csv │
    └──────────────────┘
```

---

## 3. Data Specifications

### 3.1 Master Rate Table (`data/master_rate_table.csv`)

The ground truth. Represents negotiated contract terms between the shipper and each carrier.

| Field | Type | Description |
|---|---|---|
| `lane_id` | string | Unique ID for origin→destination pair (e.g., "LANE_001") |
| `carrier_name` | string | Carrier name (e.g., "FastFreight Inc") |
| `origin_zip` | string | 5-digit origin ZIP |
| `destination_zip` | string | 5-digit destination ZIP |
| `agreed_base_rate_per_lb` | float | Contract rate in $/lb |
| `fuel_surcharge_pct` | float | Decimal (0.142 = 14.2%) |
| `allowed_accessorials` | string | Pipe-delimited list ("inside_delivery\|residential") |
| `effective_date` | date | Contract start date |
| `expiration_date` | date | Contract end date |

**Sample rows:** 10 lanes × 3 carriers = 30 contracts minimum

### 3.2 Invoice Dataset (`data/invoices_sample.csv`)

50 synthetic invoices. ~30% contain intentional billing errors.

| Field | Type | Description |
|---|---|---|
| `invoice_id` | string | Unique invoice ID (some intentionally duplicated) |
| `carrier_name` | string | Must match a carrier in rate table |
| `invoice_date` | date | Date of invoice |
| `lane_id` | string | Must match a lane in rate table |
| `origin_zip` | string | Origin ZIP |
| `destination_zip` | string | Destination ZIP |
| `shipment_weight_lbs` | float | Actual shipment weight |
| `freight_class` | string | NMFC freight class (e.g., "70", "85", "100") |
| `base_rate_charged` | float | What carrier billed per lb |
| `fuel_surcharge_pct_charged` | float | Fuel surcharge as decimal |
| `accessorial_liftgate` | float | Liftgate fee charged (0 if not charged) |
| `accessorial_residential` | float | Residential delivery fee (0 if not charged) |
| `accessorial_inside_delivery` | float | Inside delivery fee (0 if not charged) |
| `total_charged` | float | Total invoice amount |

### 3.3 Error Injection Distribution (for data generation)

| Error Type | # Invoices | Description |
|---|---|---|
| Fuel surcharge overage | 5 | Charged 18–22%, contract says 14.2% |
| Base rate overage | 4 | Charged $0.10–$0.35/lb above contract |
| Unauthorized accessorial | 4 | Liftgate or residential not in contract |
| Duplicate invoice | 2 | Same invoice_id submitted twice |
| Weight inflation | 3 | Weight rounded up >2% from expected |
| Total mismath | 2 | total_charged ≠ sum of line items |
| Clean invoices | 30 | No errors |

---

## 4. Policy Engine Specification

**File:** `engine/policy_engine.py`

### 4.1 Audit Finding Schema

```python
class AuditFinding(BaseModel):
    invoice_id: str
    rule_id: str                    # e.g., "FUEL_SURCHARGE_OVERAGE"
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    field_audited: str              # e.g., "fuel_surcharge_pct_charged"
    charged_value: float
    contract_value: float
    variance_pct: float             # (charged - contract) / contract
    dollar_impact: float            # Recovery opportunity in $
    description: str                # One sentence plain English
```

### 4.2 Audit Rules (implement all 6)

**Rule 1: BASE_RATE_OVERAGE** — Severity: HIGH
```
IF invoice.base_rate_charged > contract.agreed_base_rate_per_lb * (1 + TOLERANCE)
THEN flag with dollar_impact = (charged - contract) * shipment_weight_lbs
```

**Rule 2: FUEL_SURCHARGE_OVERAGE** — Severity: HIGH
```
IF invoice.fuel_surcharge_pct_charged > contract.fuel_surcharge_pct * (1 + TOLERANCE)
THEN flag with dollar_impact = (charged_pct - contract_pct) * base_freight_amount
```

**Rule 3: UNAUTHORIZED_ACCESSORIAL** — Severity: MEDIUM
```
FOR each accessorial in invoice:
    IF accessorial not in contract.allowed_accessorials AND amount > 0:
        flag with dollar_impact = accessorial_amount_charged
```

**Rule 4: DUPLICATE_INVOICE** — Severity: HIGH
```
IF invoice_id appears more than once in the full dataset:
    flag all occurrences after the first
    dollar_impact = total_charged of duplicate
```
*Note: This rule operates on the full dataset, not per-invoice. Run after all invoices loaded.*

**Rule 5: WEIGHT_INFLATION** — Severity: MEDIUM
```
IF shipment_weight_lbs % 100 == 0 (suspiciously round number):
    estimate actual weight = weight * 0.97 (3% rounding assumption)
    IF difference > 2% of charged weight:
        flag with dollar_impact = weight_diff * base_rate_charged
```

**Rule 6: TOTAL_MISMATCH** — Severity: LOW
```
calculated_total = (weight * base_rate) * (1 + fuel_surcharge_pct) + sum(accessorials)
IF abs(invoice.total_charged - calculated_total) > $1.00:
    flag with dollar_impact = abs(difference)
```

### 4.3 Rules Registry Pattern

```python
AUDIT_RULES: list[Callable] = [
    check_base_rate,
    check_fuel_surcharge,
    check_unauthorized_accessorials,
    check_total_mismatch,
    check_weight_inflation,
]

# Duplicate check runs separately on full dataset
DATASET_RULES: list[Callable] = [
    check_duplicate_invoices,
]
```

### 4.4 Main Engine Function

```python
def audit_invoices(
    invoices: list[FreightInvoice],
    rate_table: dict[tuple[str, str], RateContract],
) -> dict[str, list[AuditFinding]]:
    """
    Returns dict mapping invoice_id → list of findings.
    Invoices with no findings are included with empty list.
    """
```

---

## 5. LLM Explainer Specification

**File:** `agent/llm_explainer.py`

### 5.1 Input/Output

```python
def explain_findings(
    invoice: FreightInvoice,
    contract: RateContract,
    findings: list[AuditFinding],
    client: OpenAI | Anthropic,
) -> LLMExplanation:
```

### 5.2 LLM Explanation Schema

```python
class LLMExplanation(BaseModel):
    invoice_id: str
    summary: str                        # 1–2 sentence executive summary
    findings_explained: list[str]       # Plain English per finding
    total_recovery_opportunity: float   # Sum of all dollar_impact
    dispute_recommended: bool           # True if HIGH severity findings exist
    dispute_message: str                # Ready-to-send carrier message
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
```

### 5.3 System Prompt

```
You are an expert freight billing auditor with 20 years of experience in 
transportation logistics. You review flagged invoice errors and explain 
them clearly to non-technical finance managers.

Your output must be valid JSON matching this schema: {schema}

Rules:
- Be factual and specific — always cite the exact values and dollar amounts
- Tone: professional, direct, confident — not accusatory
- Dispute message: addressed to carrier, factual, requests credit or correction
- Confidence: HIGH if rule violation is clear-cut, MEDIUM if ambiguous, LOW if borderline
- Never hallucinate rate values — use only what is provided to you
```

### 5.4 Fallback Behavior

If LLM API call fails:
```python
return LLMExplanation(
    invoice_id=invoice.invoice_id,
    summary="AI explanation unavailable. See raw findings below.",
    findings_explained=[f.description for f in findings],
    total_recovery_opportunity=sum(f.dollar_impact for f in findings),
    dispute_recommended=any(f.severity == "HIGH" for f in findings),
    dispute_message="[Generate manually — AI service unavailable]",
    confidence="LOW"
)
```

---

## 6. Streamlit Dashboard Specification

**File:** `app/dashboard.py`

### 6.1 Page Layout

```
┌─────────────────────────────────────────────────────────┐
│  🔍 Freight Billing Auditor                             │
│  Sidebar: Upload Invoice CSV | Rate Table Stats         │
├─────────────────────────────────────────────────────────┤
│  📊 SUMMARY METRICS ROW                                 │
│  [Invoices Audited] [Errors Found] [$ Recovery Opp]    │
│  [High Severity]    [Clean Invoices]                    │
├─────────────────────────────────────────────────────────┤
│  📋 AUDIT RESULTS TABLE                                 │
│  invoice_id | carrier | total_charged | errors | $      │
│  (color coded by severity)                              │
├─────────────────────────────────────────────────────────┤
│  🤖 AI EXPLANATIONS                                     │
│  ▼ INV-001 [FastFreight Inc] — HIGH — $342 recovery    │
│    Summary: ...                                         │
│    Findings: ...                                        │
│    Dispute Message: ...                                 │
└─────────────────────────────────────────────────────────┘
```

### 6.2 Sidebar Content

- File uploader: accepts `.csv`
- Show master rate table stats: # carriers, # lanes, date range
- Settings expander: toggle AI explanations on/off, set severity filter

### 6.3 Summary Metrics (use `st.metric`)

- **Invoices Audited:** total count
- **Errors Found:** count of invoices with ≥1 finding
- **Recovery Opportunity:** sum of all dollar_impact, formatted as `$XX,XXX`
- **High Severity:** count of HIGH severity findings
- **Clean Invoices:** count with 0 findings

### 6.4 Results Table Columns

```
invoice_id | carrier_name | invoice_date | total_charged | 
findings_count | max_severity | total_dollar_impact | status
```

Color coding:
- HIGH severity row → red background (`#FFCCCC`)
- MEDIUM → yellow (`#FFF3CC`)
- LOW → blue (`#CCE5FF`)
- Clean → green (`#CCFFCC`)

### 6.5 AI Explanation Expanders

For each invoice with findings:
```python
with st.expander(f"🚨 {invoice_id} — {carrier} — ${recovery:,.2f} recovery opportunity"):
    st.write("**Summary:**", explanation.summary)
    st.write("**Findings:**")
    for finding in explanation.findings_explained:
        st.write(f"• {finding}")
    st.divider()
    st.write("**Dispute Message:**")
    st.code(explanation.dispute_message)
    st.button("📋 Copy Dispute Message", key=f"copy_{invoice_id}")
```

---

## 7. File Structure (Final)

```
freight_auditor/
├── .cursorrules                  ← Cursor rules (copy of rules.md)
├── .env                          ← API keys (never commit)
├── .gitignore
├── requirements.txt
├── README.md
│
├── data/
│   ├── master_rate_table.csv
│   └── invoices_sample.csv
│
├── engine/
│   ├── __init__.py
│   ├── models.py                 ← Pydantic schemas
│   └── policy_engine.py          ← Audit rules
│
├── agent/
│   ├── __init__.py
│   └── llm_explainer.py          ← LLM explanation layer
│
├── app/
│   ├── __init__.py
│   ├── audit_runner.py           ← Orchestration (engine + agent)
│   └── dashboard.py              ← Streamlit UI
│
├── tests/
│   ├── fixtures/
│   │   ├── sample_invoices.csv
│   │   └── sample_rate_table.csv
│   ├── test_policy_engine.py
│   └── test_models.py
│
└── scripts/
    └── generate_invoices.py      ← Synthetic data generator
```

---

## 8. Build Order (48-Hour Timeline)

### Day 1 — Data + Engine (Hours 0–12)

| Hour | Task | Deliverable |
|---|---|---|
| 0–1 | Project scaffold + environment | Folder structure, venv, requirements.txt |
| 1–2 | Define Pydantic models | `engine/models.py` complete |
| 2–4 | Generate synthetic data | `data/invoices_sample.csv` (50 rows, errors injected) |
| 4–5 | Build rate table | `data/master_rate_table.csv` |
| 5–9 | Build Policy Engine rules 1–6 | `engine/policy_engine.py` complete |
| 9–11 | Write unit tests | `tests/test_policy_engine.py`, all passing |
| 11–12 | CLI smoke test | `python -m engine.policy_engine` prints findings |

### Day 2 — Agent + UI (Hours 12–24)

| Hour | Task | Deliverable |
|---|---|---|
| 12–14 | Build LLM explainer | `agent/llm_explainer.py`, test with 2 invoices |
| 14–15 | Build audit runner | `app/audit_runner.py` orchestrates engine + agent |
| 15–20 | Build Streamlit dashboard | `app/dashboard.py` — upload, audit, display |
| 20–22 | End-to-end test | Upload all 50 invoices, verify output |
| 22–23 | Polish UI + error handling | Friendly errors, loading states, color coding |
| 23–24 | Write README | 3-paragraph explanation of what it does and why |

---

## 9. Success Criteria

The prototype is complete when:

- [ ] 50 synthetic invoices generated with realistic errors
- [ ] Policy Engine catches all 6 error types correctly
- [ ] Unit tests pass for all rules (pass + fail case each)
- [ ] LLM explains findings in plain English with dispute message
- [ ] Streamlit app: upload CSV → see audit results + AI explanation
- [ ] Summary metrics show: invoices audited, errors found, $ recovery
- [ ] App doesn't crash on clean invoices or LLM API failure
- [ ] No API keys in code or git history
- [ ] You can explain the Raw → Silver → Gold data flow in 60 seconds

---

## 10. Talking Points for Day 1

When asked what you did before starting:

> *"I built a lite prototype of an agentic freight billing auditor — similar to what Dow built with Azure AI and Copilot Studio. The system ingests invoice CSVs, runs a deterministic policy engine against contract rate tables to flag billing errors, then uses an LLM to explain each finding in plain English and generate a dispute message. I used Python, Pydantic, and Streamlit. The key design decision was keeping the AI out of the math — it only does explanation. The policy engine does the auditing. That keeps it auditable and trustworthy."*

That's 10 seconds of credibility with any technical or business stakeholder.
