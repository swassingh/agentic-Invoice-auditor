from __future__ import annotations

"""
Generate a small set of realistic-looking single-invoice PDFs
under data/example/ for demo and testing.

Usage (from project root, with PYTHONPATH including src/):

    python src/scripts/generate_example_invoices.py
"""

from datetime import date, timedelta
from pathlib import Path
import random

from fpdf import FPDF


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_DIR = ROOT / "data" / "example"


def _ensure_dir() -> None:
    EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)


def _example_invoices() -> list[dict]:
    carriers = ["NorthStar Logistics", "RapidFreight LLC", "Continental Transport"]
    lanes = [
        ("LANE_001", "Seattle, WA 98101", "Chicago, IL 60601"),
        ("LANE_002", "Dallas, TX 75201", "Los Angeles, CA 90001"),
        ("LANE_003", "Newark, NJ 07102", "Atlanta, GA 30301"),
        ("LANE_004", "Denver, CO 80202", "Phoenix, AZ 85001"),
    ]
    base_dates = [date(2026, 1, 15), date(2026, 2, 1)]
    rng = random.Random(2026)

    invoices: list[dict] = []
    for idx in range(1, 11):
        carrier = rng.choice(carriers)
        lane_id, origin, destination = rng.choice(lanes)
        inv_date = rng.choice(base_dates) + timedelta(days=rng.randint(0, 20))
        invoice_id = f"INV-EX-{2026}-{idx:04d}"
        weight = rng.randint(1200, 8000)
        base_rate_per_lb = round(rng.uniform(0.35, 0.75), 2)
        fuel_pct = round(rng.uniform(0.10, 0.18), 3)  # 10–18%
        liftgate = rng.choice([0.0, 85.0, 125.0])
        residential = rng.choice([0.0, 75.0])
        inside = rng.choice([0.0, 65.0])

        base_freight = round(weight * base_rate_per_lb, 2)
        fuel_amt = round(base_freight * fuel_pct, 2)
        accessorial_total = liftgate + residential + inside
        total = round(base_freight + fuel_amt + accessorial_total, 2)

        invoices.append(
            {
                "invoice_id": invoice_id,
                "carrier": carrier,
                "lane_id": lane_id,
                "origin": origin,
                "destination": destination,
                "invoice_date": inv_date.isoformat(),
                "weight_lbs": weight,
                "base_rate_per_lb": base_rate_per_lb,
                "fuel_pct": fuel_pct,
                "base_freight": base_freight,
                "fuel_amt": fuel_amt,
                "liftgate": liftgate,
                "residential": residential,
                "inside": inside,
                "accessorial_total": accessorial_total,
                "total": total,
            }
        )
    return invoices


def _draw_invoice(pdf: FPDF, inv: dict) -> None:
    pdf.add_page()
    pdf.set_auto_page_break(auto=False)

    # Header
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, inv["carrier"], ln=1)
    pdf.set_font("Arial", "", 11)
    pdf.cell(0, 6, "Freight Invoice", ln=1)
    pdf.ln(2)

    # Invoice meta
    pdf.set_font("Arial", "", 10)
    pdf.cell(0, 6, f"Invoice ID: {inv['invoice_id']}", ln=1)
    pdf.cell(0, 6, f"Invoice Date: {inv['invoice_date']}", ln=1)
    pdf.cell(0, 6, f"Lane ID: {inv['lane_id']}", ln=1)
    pdf.cell(0, 6, f"Origin: {inv['origin']}", ln=1)
    pdf.cell(0, 6, f"Destination: {inv['destination']}", ln=1)
    pdf.ln(4)

    # Summary line
    pdf.set_font("Arial", "B", 10)
    pdf.cell(
        0,
        6,
        f"Weight: {inv['weight_lbs']} lbs    Base Rate: ${inv['base_rate_per_lb']:.2f}/lb    Fuel: {inv['fuel_pct']*100:.1f}%",
        ln=1,
    )
    pdf.ln(2)

    # Charges table
    pdf.set_font("Arial", "B", 10)
    pdf.cell(80, 8, "Charge Description", border=1)
    pdf.cell(40, 8, "Amount (USD)", border=1, ln=1, align="R")

    pdf.set_font("Arial", "", 10)
    pdf.cell(80, 7, "Base Freight", border=1)
    pdf.cell(40, 7, f"${inv['base_freight']:.2f}", border=1, ln=1, align="R")

    pdf.cell(80, 7, f"Fuel Surcharge ({inv['fuel_pct']*100:.1f}%)", border=1)
    pdf.cell(40, 7, f"${inv['fuel_amt']:.2f}", border=1, ln=1, align="R")

    if inv["liftgate"] > 0:
        pdf.cell(80, 7, "Accessorial - Liftgate", border=1)
        pdf.cell(40, 7, f"${inv['liftgate']:.2f}", border=1, ln=1, align="R")
    if inv["residential"] > 0:
        pdf.cell(80, 7, "Accessorial - Residential Delivery", border=1)
        pdf.cell(40, 7, f"${inv['residential']:.2f}", border=1, ln=1, align="R")
    if inv["inside"] > 0:
        pdf.cell(80, 7, "Accessorial - Inside Delivery", border=1)
        pdf.cell(40, 7, f"${inv['inside']:.2f}", border=1, ln=1, align="R")

    pdf.set_font("Arial", "B", 10)
    pdf.cell(80, 8, "TOTAL CHARGED", border=1)
    pdf.cell(40, 8, f"${inv['total']:.2f}", border=1, ln=1, align="R")


def main() -> None:
    _ensure_dir()
    invoices = _example_invoices()

    for idx, inv in enumerate(invoices, start=1):
        pdf = FPDF()
        _draw_invoice(pdf, inv)
        out_path = EXAMPLE_DIR / f"example_invoice_{idx:02d}.pdf"
        pdf.output(str(out_path))

    print(f"Generated {len(invoices)} example invoices under {EXAMPLE_DIR}")


if __name__ == "__main__":
    main()

