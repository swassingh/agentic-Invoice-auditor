"""
CLI: RAW → INGESTION → processed CSV.
Run after generate_data.py.
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
    rows = run_ingestion()
    print(f"✅ Ingestion complete: {len(rows)} rows → data/processed/invoices_clean.csv")


if __name__ == "__main__":
    main()
