"""
Day 2 pipeline smoke test (no LLM calls).

Usage (from project root, with PYTHONPATH set to include src/):

    python src/scripts/smoke_test_day2.py

This script:
- Loads the real CSVs.
- Reads both gen_data_master_rate_table and gen_invoice_master_rate_table snapshots.
- Runs run_full_audit() with explain=False.
- Asserts basic invariants about results and summary stats.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from src.services.audit_service import run_full_audit


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    invoices_path = root / "data" / "invoices_sample.csv"
    if not invoices_path.exists():
        # Fallback to raw location if user keeps sample under data/raw
        invoices_path = root / "data" / "raw" / "invoices_sample.csv"

    if not invoices_path.exists():
        raise FileNotFoundError(
            f"invoices_sample.csv not found at {invoices_path}. "
            "Generate it with src/scripts/generate_invoices.py first."
        )

    df = pd.read_csv(invoices_path)

    # Ensure both reference rate tables are readable (if present)
    ref_dir = root / "data" / "reference"
    gen_data_rate = ref_dir / "gen_data_master_rate_table.csv"
    gen_invoice_rate = ref_dir / "gen_invoice_master_rate_table.csv"
    if gen_data_rate.exists():
        pd.read_csv(gen_data_rate)  # will raise if malformed
    if gen_invoice_rate.exists():
        pd.read_csv(gen_invoice_rate)  # will raise if malformed

    results, summary = run_full_audit(
        invoices_df=df,
        # Prefer the gen_invoice snapshot if it exists; otherwise let the
        # service layer resolve the canonical rate table.
        rate_table_path=gen_invoice_rate if gen_invoice_rate.exists() else Path("data/master_rate_table.csv"),
        explain=False,  # critical: no LLM/API call during smoke test
    )

    if not results:
        raise AssertionError("Expected non-empty results list from run_full_audit()")

    if not any(r.findings for r in results):
        raise AssertionError("Expected at least one invoice to have findings.")

    required_keys = {
        "total_invoices",
        "invoices_with_errors",
        "clean_invoices",
        "total_findings",
        "total_recovery_opportunity",
        "high_severity_count",
        "findings_by_rule",
        "top_offending_carriers",
    }
    missing = required_keys - set(summary.keys())
    if missing:
        raise AssertionError(f"Summary stats missing keys: {', '.join(sorted(missing))}")

    print("✅ Day 2 pipeline smoke test passed")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Day 2 pipeline smoke test failed: {exc}")
        sys.exit(1)

