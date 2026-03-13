from __future__ import annotations

"""
Validate PDF extraction accuracy against synthetic manifest ground truth.

Usage (from project root, with PYTHONPATH including src/):

    python src/scripts/validate_pdf_extraction.py

This script:
- Loads data/raw/pdf_invoices/manifest.csv (ground truth).
- Runs extract_invoice_from_pdf() for each PDF.
- Normalizes via normalize_extraction().
- Compares extracted values to manifest and prints a field-wise accuracy report.
- Writes data/processed/extraction_accuracy_report.csv with per-field results.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import sys

import pandas as pd

from src.agent.pdf_extractor import extract_invoice_from_pdf
from src.engine.pdf_normalizer import NormalizationResult, normalize_extraction
from src.engine.policy_engine import load_rate_table_csv


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "data" / "raw" / "pdf_invoices" / "manifest.csv"
PDF_DIR = ROOT / "data" / "raw" / "pdf_invoices"


FIELD_MAP: Dict[str, str] = {
    "invoice_id": "invoice_id",
    "carrier_name": "carrier_name",
    "invoice_date": "invoice_date",
    "origin_zip": "origin_zip",
    "base_rate_charged": "base_rate_charged",
    "fuel_surcharge_pct_charged": "fuel_surcharge_pct_charged",
    "total_charged": "total_charged",
}


@dataclass
class FieldStats:
    extracted: int = 0
    correct: int = 0


def _load_rate_table() -> Dict[Tuple[str, str], "RateContract"]:
    # Prefer gen_invoice_master_rate_table.csv if present.
    ref_dir = ROOT / "data" / "reference"
    candidates = [
        ref_dir / "gen_invoice_master_rate_table.csv",
        ref_dir / "gen_data_master_rate_table.csv",
        ref_dir / "master_rate_table.csv",
    ]
    path = None
    for c in candidates:
        if c.exists():
            path = c
            break
    if path is None:
        raise FileNotFoundError(
            "No rate table found under data/reference. "
            "Expected gen_invoice_master_rate_table.csv or similar."
        )
    return load_rate_table_csv(path)


def _normalize_expected_value(field: str, value):
    if pd.isna(value):
        return None
    if field == "invoice_date":
        # Compare as ISO date strings.
        return str(pd.to_datetime(value).date())
    if field in {"base_rate_charged", "fuel_surcharge_pct_charged", "total_charged"}:
        return float(value)
    return str(value)


def _normalize_extracted_value(field: str, value):
    if value is None:
        return None
    if field == "invoice_date":
        return str(value)
    if field in {"base_rate_charged", "fuel_surcharge_pct_charged", "total_charged"}:
        return float(value)
    return str(value)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Manifest not found at {MANIFEST_PATH}. "
            "Run src/scripts/generate_pdf_invoices.py first."
        )

    manifest_df = pd.read_csv(MANIFEST_PATH)
    rate_table = _load_rate_table()

    stats: Dict[str, FieldStats] = {f: FieldStats() for f in FIELD_MAP.keys()}
    results_rows: List[Dict] = []
    confidence_counts: Dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    normalization_ready = 0
    normalization_blocked = 0
    normalization_warnings_total = 0
    failures: List[str] = []

    for _, row in manifest_df.iterrows():
        pdf_filename = row["pdf_filename"]
        pdf_path = PDF_DIR / pdf_filename
        extraction = extract_invoice_from_pdf(pdf_path)
        norm = normalize_extraction(extraction, rate_table)

        conf = extraction.overall_confidence.value
        confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

        if norm.ready_for_engine:
            normalization_ready += 1
        else:
            normalization_blocked += 1
        normalization_warnings_total += len(norm.normalization_warnings)

        for field, manifest_col in FIELD_MAP.items():
            expected = _normalize_expected_value(field, row[manifest_col])
            extracted_val = getattr(extraction, field)
            extracted = _normalize_extracted_value(field, extracted_val)

            if extracted is not None:
                stats[field].extracted += 1
                correct = extracted == expected
                if correct:
                    stats[field].correct += 1
                else:
                    failures.append(
                        f"{row['invoice_id']}: {field} extracted as {extracted} expected {expected}"
                    )
            else:
                correct = False

            results_rows.append(
                {
                    "invoice_id": row["invoice_id"],
                    "field": field,
                    "extracted_value": extracted,
                    "expected_value": expected,
                    "correct": int(correct),
                }
            )

    total_extracted = sum(s.extracted for s in stats.values())
    total_correct = sum(s.correct for s in stats.values())
    overall_accuracy = (total_correct / total_extracted * 100.0) if total_extracted else 0.0

    # Print field accuracy table.
    print("Field Extraction Accuracy:")
    print("─────────────────────────────────────────────────────")
    print("Field                    | Extracted | Correct | Accuracy")
    print("─────────────────────────────────────────────────────")
    for field, s in stats.items():
        acc = (s.correct / s.extracted * 100.0) if s.extracted else 0.0
        print(
            f"{field:<24} | {s.extracted:>8} | {s.correct:>7} | {acc:6.0f}%"
        )
    print("─────────────────────────────────────────────────────")
    print(
        f"OVERALL                  | {total_extracted:>8} | {total_correct:>7} | {overall_accuracy:6.0f}%"
    )
    print()

    total_invoices = len(manifest_df)
    for label in ["HIGH", "MEDIUM", "LOW"]:
        count = confidence_counts.get(label, 0)
        pct = (count / total_invoices * 100.0) if total_invoices else 0.0
        confidence_counts[label] = (count, pct)

    print("Confidence Distribution:")
    for label in ["HIGH", "MEDIUM", "LOW"]:
        count, pct = confidence_counts[label]
        print(f"  {label:<6}: {count:3d} invoices ({pct:3.0f}%)")
    print()

    print("Normalization Results:")
    print(f"  Ready for engine:       {normalization_ready}/{total_invoices}")
    print(f"  Blocked (low conf):     {normalization_blocked}")
    print(f"  Warnings issued:        {normalization_warnings_total} total across all invoices")
    print()

    if failures:
        print("Failures (if any):")
        for msg in failures[:50]:
            print(f"  {msg}")
        if len(failures) > 50:
            print(f"  ... and {len(failures) - 50} more")
    else:
        print("Failures (if any):")
        print("  None")
    print()

    if overall_accuracy >= 85.0:
        verdict = "✅ EXTRACTION PIPELINE READY"
    elif overall_accuracy >= 70.0:
        verdict = "⚠️  NEEDS TUNING"
    else:
        verdict = "❌ NOT READY"
    print("Overall verdict:")
    print(f"  {verdict}")

    # Write detailed CSV report.
    processed_dir = ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    report_path = processed_dir / "extraction_accuracy_report.csv"
    pd.DataFrame.from_records(results_rows).to_csv(report_path, index=False)
    print(f"\nSaved detailed report to {report_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"❌ validate_pdf_extraction failed: {exc}")
        sys.exit(1)

