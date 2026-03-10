# Agentic Freight Billing Auditor

Industrial **DataOps** prototype: synthetic contract rates + raw invoices → validated **silver** CSV → **deterministic policy engine** (no LLM).  
Today’s work establishes the **RAW → structured → audited** path so a future Streamlit UI and LLM explainer can sit on top without changing pass/fail logic.

---

## What this repo does (one paragraph)

You simulate **carrier billing** against a **master rate table**. Data is generated or ingested as CSVs, normalized through Pydantic models, then a **policy engine** compares every invoice to its contract and emits **`AuditFinding`** records (rule id, severity, dollar impact, plain-English description). The engine is **100% deterministic**—no API calls, no randomness inside rules—so results are reproducible and auditable.

---

## High-level layout

```
data/
  raw/              Simulated “PDF parse” or carrier submission CSVs
  reference/        Simulated SAP/ERP contract export (rate table)
  processed/        Silver layer: normalized columns for downstream use
src/
  engine/
    models.py       Pydantic contracts: RateContract, FreightInvoice, AuditFinding, CleanInvoiceRow
    ingestion.py    RAW CSV → validate → CleanInvoiceRow → processed CSV
    policy_engine.py  Deterministic rules → list[AuditFinding] per invoice
  scripts/
    generate_data.py   One-shot: reference rate table + raw freight_invoices (seeded)
    generate_invoices.py  50 invoices from rate table + _error_label cheat sheet
    ingest.py         CLI wrapper: run ingestion only
    validate_data.py  Pre-flight checks before trusting data for the engine
docs/
  POLICY_ENGINE_ARCHITECTURE.md  Data flow + rule_id table + testing strategy
```

---

## Files added and what each does

### Root

| File | Purpose |
|------|--------|
| **README.md** | This file — how the repo fits together and how to run it. |
| **requirements.txt** | Minimal deps: `pydantic>=2`, `pandas>=2` (Streamlit/OpenAI/etc. can be added for later days). |
| **.gitignore** | Keeps `.env`, caches, and generated noise out of version control. |

### `src/engine/`

| File | Purpose |
|------|--------|
| **`models.py`** | Single source of truth for shapes: **`RateContract`** (contract row), **`FreightInvoice`** (raw invoice row with accessorial columns), **`AuditFinding`** (one rule firing), **`CleanInvoiceRow`** (silver naming: `billed_*`, `carrier` instead of `carrier_name`). `AuditFinding.to_product_dict()` maps to product-friendly column names (`violation_type`, `expected_value`, `actual_value`). |
| **`ingestion.py`** | **Ingestion only**: reads `data/raw/freight_invoices.csv`, builds `FreightInvoice` per row (fails loudly on bad rows), maps to `CleanInvoiceRow`, writes **`data/processed/invoices_clean.csv`**. No generation, no policy logic. |
| **`policy_engine.py`** | **The brain**: loads rate table + invoice CSV into `RateContract` / `FreightInvoice`, runs per-invoice rules (base rate, fuel, accessorials, total mismatch, weight inflation, missing contract) plus dataset rules (duplicate ID, duplicate content fingerprint). Outputs `dict[invoice_id, list[AuditFinding]]`. **`__main__`** prints a validation table comparing injected **`_error_label`** counts to caught findings. |
| **`__init__.py`** | Marks `engine` as a package. |

### `src/scripts/`

| File | Purpose |
|------|--------|
| **`generate_data.py`** | **Scaffold generator**: seeded RNG builds **30 contracts** (10 lanes × 3 carriers) → `data/reference/master_rate_table.csv`, and **50 raw invoices** → `data/raw/freight_invoices.csv`. Uses **INV-2025-*** IDs and mixed dates. **No `_error_label`** — errors are implicit for smoke tests. |
| **`generate_invoices.py`** | **Policy-focused generator**: loads existing rate table (`data/master_rate_table.csv` or `data/reference/…`), writes **`data/invoices_sample.csv`** only. **INV-2024-**** IDs, dates 2024-01-15 .. 2024-11-30. Injects **exact counts** per error type (5 fuel, 4 base rate, 4 unauthorized accessorial, 2 duplicate, 3 weight inflation, 2 total mismatch, 30 clean). Adds **`_error_label`** on every row so `validate_data.py` and the engine’s `__main__` can prove correctness. |
| **`ingest.py`** | Thin CLI: calls `run_ingestion()` and prints row count → `data/processed/invoices_clean.csv`. |
| **`validate_data.py`** | **Data contract gate**: checks rate table row count, invoice column set, **`_error_label`** distribution vs `generate_invoices.COUNTS`, and total_charged vs formula for CLEAN rows. Exit **0** = ready for policy engine; optional `--fuel-uniform 0.142` if you normalize the rate table fuel column. |

### `data/` (artifacts you generate or copy)

| Path | Role |
|------|------|
| **`data/reference/master_rate_table.csv`** | Canonical contract export from **`generate_data.py`** (or copy/symlink). Policy engine and `generate_invoices` look for **`data/master_rate_table.csv`** first, then fall back to reference. |
| **`data/reference/gen_data_master_rate_table.csv`** | Alternate name if you saved the generate_data output under a distinct filename; policy engine’s `__main__` tries this path if master isn’t present. |
| **`data/reference/gen_invoice_master_rate_table.csv`** | Same idea — extra copy for experiments; loader tries it automatically. |
| **`data/raw/freight_invoices.csv`** | Raw layer from **`generate_data.py`** — simulated parse output, **no** `_error_label`. |
| **`data/raw/invoices_sample.csv`** | Optional location if you keep labeled samples under `raw/`; policy engine falls back here if `data/invoices_sample.csv` is missing. |
| **`data/invoices_sample.csv`** | **Primary input for the policy engine** when using invoice-only generation — 50 rows with `_error_label`. |
| **`data/processed/invoices_clean.csv`** | **Silver** output from ingestion — normalized columns for any consumer that expects Product SPEC naming. |

### `docs/`

| File | Purpose |
|------|--------|
| **`POLICY_ENGINE_ARCHITECTURE.md`** | ASCII data flow; **rule_id** ↔ user-facing check; `AuditFinding` field meanings; tolerance notes; **WEIGHT_INFLATION** note (generator pattern vs SPEC-only rule); how `__main__` uses `_error_label` as ground truth before UI/agent. |

### `.cursor/` (optional — how you work with AI)

| Area | Purpose |
|------|--------|
| **rules/** | Product vs Engineering vs implementation rules (layer separation, no LLM in engine, etc.). |
| **settings/** | IDE/workflow preferences (models, build order). |
| **SPECs/** | Product / Engineering / Hybrid specs — what to build vs how. |
| **prompts/** | Copy-paste prompts phased by scaffold → models → data → engine → UI. |

These don’t run at runtime; they keep Cursor aligned with the same architecture described in `docs/POLICY_ENGINE_ARCHITECTURE.md`.

---

## Key differences (quick reference)

### `generate_data.py` vs `generate_invoices.py`

| | **generate_data.py** | **generate_invoices.py** |
|--|--|--|
| **Role** | One-shot: **rate table + raw** freight CSV for Day 1 pipeline demo. | **Invoice-only** from existing rate table; simulates **carrier billing** with known error mix. |
| **Outputs** | `data/reference/master_rate_table.csv`, `data/raw/freight_invoices.csv` | `data/invoices_sample.csv` (and may sync/copy master to `data/master_rate_table.csv`) |
| **Inputs** | Hardcoded lane/carrier grid inside script. | **Loads rate table from disk** so every line is grounded in real contract rows. |
| **Labels** | No `_error_label`. | **`_error_label`** per row (`CLEAN`, `FUEL_OVERAGE`, …) for pytest/engine validation. |
| **IDs / dates** | `INV-2025-*`, broader date range. | **`INV-2024-{4-digit}`**, dates **2024-01-15 .. 2024-11-30** as specified. |
| **When to use** | Initial scaffold + ingestion smoke test. | **Policy engine development** — deterministic counts and `TOTAL_MISMATCH` validation. |

### `freight_invoices.csv` vs `invoices_sample.csv`

- **`freight_invoices.csv`**: raw simulation from **generate_data** — no `_error_label`, uses **generate_data**’s error patterns (implicit).
- **`invoices_sample.csv`**: from **generate_invoices** — **same column set plus `_error_label`**; this is what **`validate_data.py`** and **`policy_engine.py`** expect for the “injected vs caught” validation printout.

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

---

## Contracts (CSV ↔ models)

- **RateContract** / master rate table: `lane_id`, `carrier_name`, zips, `agreed_base_rate_per_lb`, `fuel_surcharge_pct`, pipe-delimited `allowed_accessorials`, `effective_date`, `expiration_date`.
- **FreightInvoice** / raw CSV: SPEC invoice fields + `accessorial_liftgate`, `accessorial_residential`, `accessorial_inside_delivery`, `total_charged`.
- **CleanInvoiceRow** / `invoices_clean.csv`: normalized names (`carrier`, `origin`, `billed_base_rate`, …) for downstream policy or UI.
- **AuditFinding**: one row per rule firing with `rule_id`, severity, `charged_value` / `contract_value`, `dollar_impact`, `description`.

---

## Next steps (not in repo yet)

- **Streamlit app** — thin UI calling engine + optional LLM explainer.
- **Agent layer** — LLM explains `AuditFinding` lists only; never computes pass/fail.
- **pytest** — formal tests; today’s `__main__` block is the interim proof table.

---

## See also

- **`docs/POLICY_ENGINE_ARCHITECTURE.md`** — full rule list and data flow.
- **Engineering SPEC** in `.cursor/SPECs/` — canonical rule IDs and schemas.
