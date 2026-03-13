import pandas as pd
import random
import uuid
from fpdf import FPDF
from pathlib import Path

# Setup Project Structure
Path("data").mkdir(exist_ok=True)

# 1. Define Master Rate Table (The Contract)
lanes = [
    {"lane_id": "LANE_SEA_SFO", "origin": "Seattle", "destination": "San Francisco", "base_rate": 1200, "fuel_cap": 0.15, "accessorials": ["liftgate"]},
    {"lane_id": "LANE_NYC_CHI", "origin": "New York", "destination": "Chicago", "base_rate": 1800, "fuel_cap": 0.12, "accessorials": ["detention"]},
    {"lane_id": "LANE_DAL_LAX", "origin": "Dallas", "destination": "Los Angeles", "base_rate": 2100, "fuel_cap": 0.14, "accessorials": []},
]

# 2. Generation Logic
invoices = []
random.seed(42)

def create_invoice(lane, error_type="CLEAN", inv_id=None):
    inv_id = inv_id or f"INV-2026-{len(invoices)+1:04d}"
    weight = random.randint(2000, 10000)
    base_rate = lane["base_rate"]
    fuel_pct = lane["fuel_cap"]
    accessorial_fee = 0
    accessorial_name = ""
    freight_class = "CLASS_70"
    
    # Apply Error Logic
    if error_type == "FUEL_OVERAGE":
        fuel_pct = round(random.uniform(0.185, 0.22), 3)
    elif error_type == "BASE_RATE_OVERAGE":
        base_rate = round(base_rate * random.uniform(1.08, 1.14), 2)
    elif error_type == "UNAUTHORIZED_ACCESSORIAL":
        accessorial_name = "inside_delivery"
        accessorial_fee = random.randint(125, 175)
    elif error_type == "WEIGHT_INFLATION":
        billed_weight = (round(weight / 100) * 100) * 1.04
        weight = billed_weight # Inflate the billed weight
    
    fuel_charge = base_rate * fuel_pct
    total = base_rate + fuel_charge + accessorial_fee
    
    if error_type == "TOTAL_MISMATCH":
        total += random.choice([-65, -25, 25, 65])

    # Map single accessorial_fee into the three structured accessorial fields
    accessorial_liftgate = accessorial_fee if accessorial_name == "liftgate" else 0.0
    accessorial_residential = accessorial_fee if accessorial_name == "residential" else 0.0
    accessorial_inside_delivery = accessorial_fee if accessorial_name == "inside_delivery" else 0.0

    return {
        "invoice_id": inv_id,
        # Fields aligned with FreightInvoice / extraction expectations
        "carrier_name": "Demo Carrier",
        "invoice_date": "2026-01-15",
        "origin_zip": "00000",
        "destination_zip": "99999",
        "shipment_weight_lbs": weight,
        "freight_class": freight_class,
        "base_rate_charged": base_rate,
        "fuel_surcharge_pct_charged": fuel_pct,
        "accessorial_liftgate": accessorial_liftgate,
        "accessorial_residential": accessorial_residential,
        "accessorial_inside_delivery": accessorial_inside_delivery,
        "total_charged": total,
        # Existing sample-specific fields
        "lane_id": lane["lane_id"],
        "weight_lbs": weight,
        "fuel_surcharge_charged": fuel_charge,
        "accessorial_fee": accessorial_fee,
        "accessorial_name": accessorial_name,
        "error_label": error_type
    }

# 3. Build the Dataset
# Note: You requested 10 total but listed 50 total in the breakdown prompts. 
# Following the explicit error counts provided in your prompt.
error_counts = {
    "FUEL_OVERAGE": 5, "BASE_RATE_OVERAGE": 4, "UNAUTHORIZED_ACCESSORIAL": 4,
    "DUPLICATE": 2, "WEIGHT_INFLATION": 3, "TOTAL_MISMATCH": 2, "CLEAN": 30
}

for err, count in error_counts.items():
    if err == "DUPLICATE": continue
    for _ in range(count):
        invoices.append(create_invoice(random.choice(lanes), err))

# Handle Duplicates
inv_0003 = next(i for i in invoices if i["invoice_id"] == "INV-2026-0003")
inv_0007 = next(i for i in invoices if i["invoice_id"] == "INV-2026-0007")
invoices.append({**inv_0003, "invoice_id": "INV-2026-9998", "error_label": "DUPLICATE"})
invoices.append({**inv_0007, "invoice_id": "INV-2026-9999", "error_label": "DUPLICATE"})

df = pd.DataFrame(invoices).sample(frac=1).reset_index(drop=True)
df.to_csv("data/invoices_sample.csv", index=False)

# 4. Generate PDF Documents
# 4a) Simple list-style batch view
pdf = FPDF()
pdf.add_page()
pdf.set_font("Arial", size=10)
pdf.cell(200, 10, txt="Agentic Auditor - Raw Invoice Batch", ln=True, align='C')
for _, row in df.iterrows():
    pdf.cell(
        0,
        10,
        txt=f"{row['invoice_id']} | Lane: {row['lane_id']} | Total: ${row['total_charged']:.2f}",
        ln=True,
    )
pdf.output("data/invoices_sample.pdf")

# 4b) Tabular view in a separate PDF (invoice_sample_tbl.pdf)
table_pdf = FPDF()
table_pdf.add_page()
table_pdf.set_font("Arial", size=9)
table_pdf.cell(0, 8, txt="Agentic Auditor - Invoice Table", ln=True, align="C")
table_pdf.ln(4)

# Define columns for the table
columns = [
    ("Invoice ID", "invoice_id", 30),
    ("Lane", "lane_id", 28),
    ("Weight (lbs)", "weight_lbs", 26),
    ("Base Rate", "base_rate_charged", 25),
    ("Fuel Surcharge", "fuel_surcharge_charged", 30),
    ("Accessorial", "accessorial_fee", 24),
    ("Total", "total_charged", 25),
]

# Header row
for header, _field, width in columns:
    table_pdf.cell(width, 8, header, border=1, align="C")
table_pdf.ln()

# Data rows (limit to keep the table readable)
max_rows = 25
for _, row in df.head(max_rows).iterrows():
    for _header, field, width in columns:
        value = row[field]
        if isinstance(value, float):
            cell_text = f"{value:.2f}"
        else:
            cell_text = str(value)
        table_pdf.cell(width, 8, cell_text, border=1, align="C")
    table_pdf.ln()

table_pdf.output("data/invoices_sample_tbl.pdf")

# 5. Validation Summary
print("\n--- Error Breakdown ---")
print(df['error_label'].value_counts())
mismatches = df[df.apply(lambda r: round(r.base_rate_charged + r.fuel_surcharge_charged + r.accessorial_fee, 2) != round(r.total_charged, 2), axis=1)]
print(f"\n⚠️ Validation: {len(mismatches)} invoices where total_charged doesn't match calculated (Expected 2 for TOTAL_MISMATCH)")