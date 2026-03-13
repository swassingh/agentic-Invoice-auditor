from __future__ import annotations

"""
Generate synthetic carrier invoice PDFs plus a manifest CSV.

Usage (from project root, with PYTHONPATH including src/):

    python src/scripts/generate_pdf_invoices.py

Outputs:
- data/raw/pdf_invoices/<invoice_id>.pdf
- data/raw/pdf_invoices/manifest.csv  (ground-truth fields per invoice)

The PDFs are simple but consistent layouts designed for the OCR / LLM
extraction pipeline. The manifest serves as ground truth for
validate_pdf_extraction.py and for the mock extraction provider.
"""

import sys
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = ROOT / "data" / "raw" / "pdf_invoices"


def _load_invoices_df() -> pd.DataFrame:
    """
    Load synthetic invoices from the existing CSV generator output.

    Priority:
    - data/raw/invoices_sample.csv
    - data/invoices_sample.csv
    - data/raw/freight_invoices.csv
    """
    candidates = [
        ROOT / "data" / "raw" / "invoices_sample.csv",
        ROOT / "data" / "invoices_sample.csv",
        ROOT / "data" / "raw" / "freight_invoices.csv",
    ]
    for p in candidates:
        if p.exists():
            return pd.read_csv(p)
    raise FileNotFoundError(
        "Could not find a base invoices CSV. Expected one of:\n"
        "  - data/raw/invoices_sample.csv\n"
        "  - data/invoices_sample.csv\n"
        "  - data/raw/freight_invoices.csv\n"
    )


def _ensure_pdf_dir() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)


def _draw_invoice_image(row: pd.Series) -> Image.Image:
    """
    Render a simple, readable invoice layout into a single-page image.
    """
    width, height = 1240, 1754  # roughly A4 at 150–200 DPI
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)

    # Basic fonts; rely on default PIL font for portability.
    title = f"{row['carrier_name']} — FREIGHT INVOICE"
    draw.text((60, 60), title, fill="black")

    y = 140
    line_h = 32

    fields = [
        f"Invoice ID: {row['invoice_id']}",
        f"Invoice Date: {row['invoice_date']}",
        f"Lane ID: {row['lane_id']}",
        f"Origin ZIP: {row['origin_zip']}",
        f"Destination ZIP: {row['destination_zip']}",
        "",
        f"Shipment Weight (lbs): {row['shipment_weight_lbs']}",
        f"Freight Class: {row['freight_class']}",
        "",
        f"Base Rate Charged ($/lb): {row['base_rate_charged']}",
        f"Fuel Surcharge (% as decimal): {row['fuel_surcharge_pct_charged']}",
        "",
        f"Liftgate Fee: ${row.get('accessorial_liftgate', 0):.2f}",
        f"Residential Fee: ${row.get('accessorial_residential', 0):.2f}",
        f"Inside Delivery Fee: ${row.get('accessorial_inside_delivery', 0):.2f}",
        "",
        f"TOTAL CHARGED: ${row['total_charged']:.2f}",
    ]

    for text in fields:
        draw.text((80, y), text, fill="black")
        y += line_h

    return img


def _build_manifest(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a manifest DataFrame aligned with PDFExtractionResult fields.
    """
    records = []
    for _, row in df.iterrows():
        pdf_filename = f"{row['invoice_id']}.pdf"
        records.append(
            {
                "pdf_filename": pdf_filename,
                "invoice_id": row["invoice_id"],
                "carrier_name": row["carrier_name"],
                "invoice_date": row["invoice_date"],
                "lane_id": row["lane_id"],
                "origin_zip": row["origin_zip"],
                "destination_zip": row["destination_zip"],
                "shipment_weight_lbs": row["shipment_weight_lbs"],
                "freight_class": row["freight_class"],
                "base_rate_charged": row["base_rate_charged"],
                "fuel_surcharge_pct_charged": row["fuel_surcharge_pct_charged"],
                "accessorial_liftgate": row.get("accessorial_liftgate", 0),
                "accessorial_residential": row.get("accessorial_residential", 0),
                "accessorial_inside_delivery": row.get(
                    "accessorial_inside_delivery", 0
                ),
                "total_charged": row["total_charged"],
            }
        )
    return pd.DataFrame.from_records(records)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    df = _load_invoices_df()
    _ensure_pdf_dir()

    manifest_rows = []
    for _, row in df.iterrows():
        img = _draw_invoice_image(row)
        pdf_filename = f"{row['invoice_id']}.pdf"
        pdf_path = PDF_DIR / pdf_filename
        img.save(pdf_path, "PDF")
        manifest_rows.append(row)

    manifest_df = _build_manifest(df)
    manifest_path = PDF_DIR / "manifest.csv"
    manifest_df.to_csv(manifest_path, index=False)

    print(
        f"✅ Generated {len(df)} invoice PDFs under {PDF_DIR} "
        f"and manifest at {manifest_path}"
    )


if __name__ == "__main__":
    main()

