"""
Generate official invoice PDFs using the same layout as data/example/
from the manifest in data/raw/pdf_invoices. Output goes to
data/raw/invoice_pdfs_official/.

Usage (from project root, with PYTHONPATH including src/):

    python src/scripts/generate_official_invoice_pdfs.py

Requires: data/raw/pdf_invoices/manifest.csv (run generate_pdf_invoices.py first
if missing).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from fpdf import FPDF
from fpdf.enums import XPos, YPos


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "data" / "raw" / "pdf_invoices" / "manifest.csv"
OUT_DIR = ROOT / "data" / "raw" / "invoice_pdfs_official"


def _ensure_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def _row_to_inv(row: pd.Series) -> dict:
    """Map manifest row to the invoice dict expected by _draw_invoice (example layout)."""
    weight = float(row["shipment_weight_lbs"])
    base_rate = float(row["base_rate_charged"])
    fuel_pct = float(row["fuel_surcharge_pct_charged"])
    liftgate = float(row.get("accessorial_liftgate", 0) or 0)
    residential = float(row.get("accessorial_residential", 0) or 0)
    inside = float(row.get("accessorial_inside_delivery", 0) or 0)

    base_freight = round(weight * base_rate, 2)
    fuel_amt = round(base_freight * fuel_pct, 2)
    accessorial_total = liftgate + residential + inside
    total = round(base_freight + fuel_amt + accessorial_total, 2)

    return {
        "invoice_id": str(row["invoice_id"]),
        "carrier": str(row["carrier_name"]),
        "lane_id": str(row["lane_id"]),
        "origin": f"ZIP {row['origin_zip']}",
        "destination": f"ZIP {row['destination_zip']}",
        "invoice_date": str(row["invoice_date"]),
        "weight_lbs": int(round(weight)),
        "base_rate_per_lb": base_rate,
        "fuel_pct": fuel_pct,
        "base_freight": base_freight,
        "fuel_amt": fuel_amt,
        "liftgate": liftgate,
        "residential": residential,
        "inside": inside,
        "accessorial_total": accessorial_total,
        "total": total,
    }


def _draw_invoice(pdf: FPDF, inv: dict) -> None:
    """Same layout as generate_example_invoices.py (Freight Invoice header + table)."""
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)

    # Header
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, inv["carrier"], new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, "Freight Invoice", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    # Invoice meta
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Invoice ID: {inv['invoice_id']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Invoice Date: {inv['invoice_date']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Lane ID: {inv['lane_id']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Origin: {inv['origin']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 6, f"Destination: {inv['destination']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    # Summary line
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(
        0,
        6,
        f"Weight: {inv['weight_lbs']} lbs    Base Rate: ${inv['base_rate_per_lb']:.2f}/lb    Fuel: {inv['fuel_pct']*100:.1f}%",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(2)

    # Charges table
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(80, 8, "Charge Description", border=1)
    pdf.cell(40, 8, "Amount (USD)", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(80, 7, "Base Freight", border=1)
    pdf.cell(40, 7, f"${inv['base_freight']:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

    pdf.cell(80, 7, f"Fuel Surcharge ({inv['fuel_pct']*100:.1f}%)", border=1)
    pdf.cell(40, 7, f"${inv['fuel_amt']:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

    if inv["liftgate"] > 0:
        pdf.cell(80, 7, "Accessorial - Liftgate", border=1)
        pdf.cell(40, 7, f"${inv['liftgate']:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
    if inv["residential"] > 0:
        pdf.cell(80, 7, "Accessorial - Residential Delivery", border=1)
        pdf.cell(40, 7, f"${inv['residential']:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")
    if inv["inside"] > 0:
        pdf.cell(80, 7, "Accessorial - Inside Delivery", border=1)
        pdf.cell(40, 7, f"${inv['inside']:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(80, 8, "TOTAL CHARGED", border=1)
    pdf.cell(40, 8, f"${inv['total']:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="R")


def main() -> None:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Manifest not found: {MANIFEST_PATH}\n"
            "Run: python src/scripts/generate_pdf_invoices.py"
        )

    _ensure_dir()
    manifest_df = pd.read_csv(MANIFEST_PATH)

    for _, row in manifest_df.iterrows():
        inv = _row_to_inv(row)
        pdf = FPDF()
        _draw_invoice(pdf, inv)
        out_path = OUT_DIR / f"{inv['invoice_id']}.pdf"
        pdf.output(str(out_path))

    # Copy manifest so mock extractor / validation can use this folder
    out_manifest = OUT_DIR / "manifest.csv"
    manifest_df.to_csv(out_manifest, index=False)

    print(f"Generated {len(manifest_df)} official invoice PDFs under {OUT_DIR}")
    print(f"Manifest: {out_manifest}")


if __name__ == "__main__":
    main()
