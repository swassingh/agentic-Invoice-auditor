# Agentic Freight Billing Auditor

Industrial **DataOps** prototype: synthetic contract rates + raw invoices → validated **silver** CSV → **deterministic policy engine** → **LLM explanations in a Streamlit dashboard**.  
Day 1 built the **RAW → structured → audited** path; Day 2 adds a thin **UI + agent layer** that explains, but never changes, deterministic findings.

---

## What this repo does (one paragraph)

You simulate **carrier billing** against a **master rate table**. Data is generated or ingested as CSVs, normalized through Pydantic models, then a **policy engine** compares every invoice to its contract and emits `**AuditFinding`** records (rule id, severity, dollar impact, plain-English description). The engine is **100% deterministic**—no API calls, no randomness inside rules—so results are reproducible and auditable.

---

## High-level layout

```
data/
  raw/              Simulated “PDF parse” or carrier submission CSVs
  reference/        Simulated SAP/ERP contract export (rate table)
  processed/        Silver layer: normalized columns for downstream use
src/
  engine/
    models.py       Pydantic contracts: RateContract, FreightInvoice, AuditFinding, CleanInvoiceRow, LLMExplanation, AuditResult
    ingestion.py    RAW CSV → validate → CleanInvoiceRow → processed CSV
    policy_engine.py  Deterministic rules → list[AuditFinding] per invoice
  agent/
    explainer.py    Gemini-based explainer: AuditFinding list → LLMExplanation JSON
  services/
    audit_service.py  Orchestration: DataFrame → FreightInvoice → AuditResult list + summary stats
  scripts/
    generate_data.py   One-shot: reference rate table + raw freight_invoices (seeded)
    generate_invoices.py  50 invoices from rate table + _error_label cheat sheet
    ingest.py         CLI wrapper: run ingestion only
    validate_data.py  Pre-flight checks before trusting data for the engine
    smoke_test_day2.py  End-to-end (no-LLM) smoke test for Day 2 pipeline
app/
  streamlit_app.py   Streamlit UI: upload → audit → (optional) explain → display
docs/
  POLICY_ENGINE_ARCHITECTURE.md  Data flow + rule_id table + testing strategy
```

---

## Files added and what each does

### Root


| File                 | Purpose                                                                                                |
| -------------------- | ------------------------------------------------------------------------------------------------------ |
| **README.md**        | This file — how the repo fits together and how to run it.                                              |
| **requirements.txt** | Runtime deps: `pydantic`, `pandas`, `streamlit`, `python-dotenv`, `loguru`, `google-genai` for Gemini. |
| **.gitignore**       | Keeps `.env`, caches, and generated noise out of version control.                                      |


### `src/engine/`


| File                   | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `**models.py`**        | Single source of truth for shapes: `**RateContract**` (contract row), `**FreightInvoice**` (raw invoice row with accessorial columns), `**AuditFinding**` (one rule firing), `**CleanInvoiceRow**` (silver naming: `billed_*`, `carrier` instead of `carrier_name`), `**LLMExplanation**` (AI summary + dispute), and `**AuditResult**` (per-invoice aggregate used by the service/UI layer). `AuditFinding.to_product_dict()` maps to product-friendly column names (`violation_type`, `expected_value`, `actual_value`). |
| `**ingestion.py**`     | **Ingestion only**: reads `data/raw/freight_invoices.csv`, builds `FreightInvoice` per row (fails loudly on bad rows), maps to `CleanInvoiceRow`, writes `**data/processed/invoices_clean.csv`**. No generation, no policy logic.                                                                                                                                                                                                                                                                                          |
| `**policy_engine.py**` | **The brain**: loads rate table + invoice CSV into `RateContract` / `FreightInvoice`, runs per-invoice rules (base rate, fuel, accessorials, total mismatch, weight inflation, missing contract) plus dataset rules (duplicate ID, duplicate content fingerprint). Outputs `dict[invoice_id, list[AuditFinding]]`. `**__main__`** prints a validation table comparing injected `**_error_label**` counts to caught findings.                                                                                               |
| `**__init__.py**`      | Marks `engine` as a package.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |


### `src/agent/`


| File               | Purpose                                                                                                                                                                                                                                                                                                                             |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `**explainer.py**` | LLM **explanation** layer. Takes `(FreightInvoice, RateContract, list[AuditFinding])` and calls Gemini (`gemini-3-flash-preview`) with a strict JSON-only prompt to produce an `**LLMExplanation`**. Never re-audits or recalculates; on any failure, returns a deterministic fallback with raw findings and a LOW-confidence flag. |
| `**__init__.py**`  | Re-exports `explain_findings` / `explain_batch`.                                                                                                                                                                                                                                                                                    |


### `src/services/`


| File                   | Purpose                                                                                                                                                                                                                                                                                                              |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `**audit_service.py**` | **Orchestration layer**: converts uploaded `pandas.DataFrame` → list[`FreightInvoice`], loads the rate table, runs `audit_invoices(...)`, optionally calls `agent.explainer.explain_batch(...)`, and returns a sorted list[`AuditResult`] plus summary stats. Also provides `results_to_display_df(...)` for the UI. |
| `**__init__.py`**      | Marks `services` as a package.                                                                                                                                                                                                                                                                                       |


### `src/scripts/`


| File                       | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `**generate_data.py**`     | **Scaffold generator** (Day 1): seeded RNG builds **30 contracts** (10 lanes × 3 carriers) and writes them to `**data/reference/gen_data_master_rate_table.csv`** and `**data/reference/master_rate_table.csv**`, plus **50 raw invoices** to `data/raw/freight_invoices.csv`. Uses **INV-2025-*** IDs and mixed dates. **No `_error_label`** — errors are implicit for smoke tests.                                                                                                                                                                                                                                                                                                                                                           |
| `**generate_invoices.py**` | **Policy-focused generator** (Day 1): loads an existing rate table from one of: `data/reference/gen_invoice_master_rate_table.csv`, `data/reference/gen_data_master_rate_table.csv`, `data/master_rate_table.csv`, or `data/reference/master_rate_table.csv`; writes `**data/reference/gen_invoice_master_rate_table.csv`** as the snapshot used for this run; and produces `**data/raw/invoices_sample.csv**` with **INV-2024-**** IDs, dates 2024-01-15 .. 2024-11-30. Injects **exact counts** per error type (5 fuel, 4 base rate, 4 unauthorized accessorial, 2 duplicate, 3 weight inflation, 2 total mismatch, 30 clean). Adds `**_error_label`** on every row so `validate_data.py`, the policy engine, and the Streamlit app can all rely on the same labeled dataset. |
| `**ingest.py**`            | Thin CLI: calls `run_ingestion()` twice. First ingests `data/raw/freight_invoices.csv` → `data/processed/invoices_clean.csv` (Day 1 RAW → silver), then, if present, ingests `data/raw/invoices_sample.csv` → `data/processed/invoices_sample_clean.csv` so both raw datasets have their own cleaned/silver outputs.                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `**validate_data.py**`     | **Data contract gate**: loads **all** rate tables whose filenames contain `master_rate_table` (from `data/master_rate_table.csv` and `data/reference/*master_rate_table*.csv`) and runs structural checks on each (nulls, row count, date ranges, optional uniform fuel). Then uses a canonical table drawn from the `data/reference/` folder (if present) to check invoice columns, lane+carrier coverage, duplicate behavior, `**_error_label`** distribution vs `generate_invoices.COUNTS`, and CLEAN invoice total math. Exit **0** = ready for policy engine; optional `--fuel-uniform 0.142` if you normalize the rate table fuel column.                                                                                                           |
| `**smoke_test_day2.py`**   | **End-to-end smoke test** (no LLM): loads `data/invoices_sample.csv`, runs `run_full_audit(..., explain=False)`, asserts non-empty results and at least one invoice with findings, verifies summary keys, and prints a ✅/❌ message. Run this before launching Streamlit.                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |


### `data/` (artifacts you generate or copy)


| Path                                                   | Role                                                                                                                                                                                                                                                             |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `**data/reference/master_rate_table.csv`**             | Canonical contract export; written by `**generate_data.py**` and used as a fallback by `generate_invoices.py` and the policy engine when `data/master_rate_table.csv` is missing.                                                                                |
| `**data/reference/gen_data_master_rate_table.csv**`    | Rate table generated by `generate_data.py` (Day 1 scaffold). A copy is also written to `data/reference/master_rate_table.csv`.                                                                                                                                   |
| `**data/reference/gen_invoice_master_rate_table.csv**` | Rate table snapshot used by `generate_invoices.py` when building `invoices_sample.csv` (Day 1 policy dataset).                                                                                                                                                   |
| `**data/raw/freight_invoices.csv**`                    | Raw layer from `**generate_data.py**` — simulated parse output, **no** `_error_label`.                                                                                                                                                                           |
| `**data/raw/invoices_sample.csv`**                     | Labeled policy dataset from `**generate_invoices.py**`; primary location for the 50-row sample with `_error_label`. Some tools (policy engine, validator, smoke test) will also look for a root-level `data/invoices_sample.csv` if you choose to copy it there. |
| `**data/processed/invoices_clean.csv**`                | **Silver** output from ingestion — normalized columns for any consumer that expects Product SPEC naming.                                                                                                                                                         |


### `docs/`


| File                                | Purpose                                                                                                                                                                                                                                |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `**POLICY_ENGINE_ARCHITECTURE.md`** | ASCII data flow; **rule_id** ↔ user-facing check; `AuditFinding` field meanings; tolerance notes; **WEIGHT_INFLATION** note (generator pattern vs SPEC-only rule); how `__main__` uses `_error_label` as ground truth before UI/agent. |


### `.cursor/` (optional — how you work with AI)


| Area          | Purpose                                                                                    |
| ------------- | ------------------------------------------------------------------------------------------ |
| **rules/**    | Product vs Engineering vs implementation rules (layer separation, no LLM in engine, etc.). |
| **settings/** | IDE/workflow preferences (models, build order).                                            |
| **SPECs/**    | Product / Engineering / Hybrid specs — what to build vs how.                               |
| **prompts/**  | Copy-paste prompts phased by scaffold → models → data → engine → UI.                       |


These don’t run at runtime; they keep Cursor aligned with the same architecture described in `docs/POLICY_ENGINE_ARCHITECTURE.md`.

---

## Key differences (quick reference)

### `generate_data.py` vs `generate_invoices.py`


|                 | **generate_data.py**                                                    | **generate_invoices.py**                                                                       |
| --------------- | ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| **Role**        | One-shot: **rate table + raw** freight CSV for Day 1 pipeline demo.     | **Invoice-only** from existing rate table; simulates **carrier billing** with known error mix. |
| **Outputs**     | `data/reference/master_rate_table.csv`, `data/raw/freight_invoices.csv` | `data/invoices_sample.csv` (and may sync/copy master to `data/master_rate_table.csv`)          |
| **Inputs**      | Hardcoded lane/carrier grid inside script.                              | **Loads rate table from disk** so every line is grounded in real contract rows.                |
| **Labels**      | No `_error_label`.                                                      | `**_error_label`** per row (`CLEAN`, `FUEL_OVERAGE`, …) for pytest/engine validation.          |
| **IDs / dates** | `INV-2025-*`, broader date range.                                       | `**INV-2024-{4-digit}`**, dates **2024-01-15 .. 2024-11-30** as specified.                     |
| **When to use** | Initial scaffold + ingestion smoke test.                                | **Policy engine development** — deterministic counts and `TOTAL_MISMATCH` validation.          |


### `freight_invoices.csv` vs `invoices_sample.csv`

- `**freight_invoices.csv`**: raw simulation from **generate_data** — no `_error_label`, uses **generate_data**’s error patterns (implicit).
- `**invoices_sample.csv`**: from **generate_invoices** — **same column set plus `_error_label`**; this is what `**validate_data.py**` and `**policy_engine.py**` expect for the “injected vs caught” validation printout.

### `ingestion.py` vs `policy_engine.py`

- **Ingestion**: parse → validate → normalize → write **processed** CSV only.
- **Policy engine**: read rate table + invoices → **audit** → structured findings only (no file write unless you add it).

---

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

From repo root, ensure `src` is importable (Windows example):

```powershell
set PYTHONPATH=%CD%
```

---

## Run (typical order)

### 1. Generate data (once per dataset)

```powershell
# 1) Generate reference + raw (optional if you already have CSVs)
python src/scripts/generate_data.py

# 2) Optional: generate labeled invoices for engine proof
python src/scripts/generate_invoices.py

# 3) Validate data contract (expects invoices_sample with _error_label)
python src/scripts/validate_data.py

# 4) Raw → silver (reads data/raw/freight_invoices.csv)
python src/scripts/ingest.py

# 5) Deterministic audit (loads master rate table + invoices_sample)
python src/engine/policy_engine.py
```

Module form:

```bash
python -m src.scripts.generate_data
python -m src.scripts.ingest
```

### 2. Day 2 smoke test (no LLM)

```powershell
# From repo root, with src on PYTHONPATH:
set PYTHONPATH=%CD%
python src/scripts/smoke_test_day2.py
```

Or, as a module (no PYTHONPATH tweak):

```bash
python -m src.scripts.smoke_test_day2
```

You should see:

```text
✅ Day 2 pipeline smoke test passed
```

### 3. Run the Streamlit dashboard

Create a `.env` file in the project root for Gemini (optional but recommended for AI explanations):

```bash
GEMINI_API_KEY=your_api_key_here
```

Then, from the repo root:

```bash
streamlit run app/streamlit_app.py
```

In the browser:

- Upload `data/invoices_sample.csv` (or your own CSV matching that schema).
- Toggle **“Enable AI Explanations”** in the sidebar (disabled automatically if `GEMINI_API_KEY` is missing).
- Use **severity filters** to focus on HIGH/MEDIUM/LOW vs CLEAN.
- Use the **expander section** under “🤖 AI Audit Explanations” to see per-invoice summaries and dispute messages.

---

## Contracts (CSV ↔ models)

- **RateContract** / master rate table: `lane_id`, `carrier_name`, zips, `agreed_base_rate_per_lb`, `fuel_surcharge_pct`, pipe-delimited `allowed_accessorials`, `effective_date`, `expiration_date`.
- **FreightInvoice** / raw CSV: SPEC invoice fields + `accessorial_liftgate`, `accessorial_residential`, `accessorial_inside_delivery`, `total_charged`.
- **CleanInvoiceRow** / `invoices_clean.csv`: normalized names (`carrier`, `origin`, `billed_base_rate`, …) for downstream policy or UI.
- **AuditFinding**: one row per rule firing with `rule_id`, severity, `charged_value` / `contract_value`, `dollar_impact`, `description`.
- **LLMExplanation**: AI-side explanation object with `summary`, `findings_explained`, `total_recovery_opportunity`, `dispute_recommended`, `dispute_message`, and `confidence` (HIGH/MEDIUM/LOW).
- **AuditResult**: aggregate per invoice (`invoice`, `findings`, optional `explanation`) with helpers for `total_dollar_impact`, `has_errors`, and `max_severity`.

---

## Next steps

- **pytest** — formal tests around `policy_engine`, `audit_service`, and `explainer` (beyond the Day 2 smoke test).

---

## See also

- `**docs/POLICY_ENGINE_ARCHITECTURE.md`** — full rule list and data flow.
- **Engineering SPEC** in `.cursor/SPECs/` — canonical rule IDs and schemas.

