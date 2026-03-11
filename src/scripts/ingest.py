"""
CLI: RAW → INGESTION → processed CSV.
Run after generate_data.py / generate_invoices.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.engine.ingestion import run_ingestion


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    root = _ROOT

    # 1) Ingest freight_invoices.csv → invoices_clean.csv
    raw_freight = root / "data" / "raw" / "freight_invoices.csv"
    processed_freight = root / "data" / "processed" / "freight_invoices_clean.csv"
    if raw_freight.exists():
        rows_freight = run_ingestion(raw_csv=raw_freight, processed_csv=processed_freight)
        print(
            f"✅ Ingestion complete: {len(rows_freight)} rows → "
            f"{processed_freight.as_posix()}"
        )
    else:
        print(f"ℹ️ Skipping ingestion for {raw_freight.as_posix()} (file not found)")

    # 2) Ingest invoices_sample.csv (if present) → invoices_sample_clean.csv
    raw_sample = root / "data" / "raw" / "invoices_sample.csv"
    processed_sample = root / "data" / "processed" / "invoices_sample_clean.csv"
    if raw_sample.exists():
        rows_sample = run_ingestion(raw_csv=raw_sample, processed_csv=processed_sample)
        print(
            f"✅ Ingestion complete: {len(rows_sample)} rows → "
            f"{processed_sample.as_posix()}"
        )
    else:
        print(f"ℹ️ Skipping ingestion for {raw_sample.as_posix()} (file not found)")


if __name__ == "__main__":
    main()
