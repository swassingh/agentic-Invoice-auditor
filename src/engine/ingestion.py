"""
INGESTION stage: raw CSV → validated Pydantic → cleaned structured CSV.
Separation: no generation logic here; only parse, validate, normalize, write.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import pandas as pd

from src.engine.models import CleanInvoiceRow, FreightInvoice

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_raw_invoices_csv(path: Path | str) -> List[FreightInvoice]:
    """Read raw freight_invoices CSV and return validated FreightInvoice models."""
    path = Path(path)
    df = pd.read_csv(path)
    # Normalize column names if CSV uses snake_case from SPEC
    invoices: List[FreightInvoice] = []
    for idx, row in df.iterrows():
        try:
            inv = FreightInvoice(
                invoice_id=str(row["invoice_id"]),
                carrier_name=str(row["carrier_name"]),
                invoice_date=pd.to_datetime(row["invoice_date"]).date(),
                lane_id=str(row["lane_id"]),
                origin_zip=str(row["origin_zip"]).zfill(5)[:5],
                destination_zip=str(row["destination_zip"]).zfill(5)[:5],
                shipment_weight_lbs=float(row["shipment_weight_lbs"]),
                freight_class=str(row["freight_class"]),
                base_rate_charged=float(row["base_rate_charged"]),
                fuel_surcharge_pct_charged=float(row["fuel_surcharge_pct_charged"]),
                accessorial_liftgate=float(row.get("accessorial_liftgate", 0) or 0),
                accessorial_residential=float(
                    row.get("accessorial_residential", 0) or 0
                ),
                accessorial_inside_delivery=float(
                    row.get("accessorial_inside_delivery", 0) or 0
                ),
                total_charged=float(row["total_charged"]),
            )
            invoices.append(inv)
        except Exception as e:
            logger.exception("Ingestion failed at row %s invoice_id=%s", idx, row.get("invoice_id", "?"))
            raise RuntimeError(f"Ingestion failed at row {idx}") from e
    return invoices


def invoices_to_clean_rows(invoices: List[FreightInvoice]) -> List[CleanInvoiceRow]:
    """Map raw FreightInvoice → CleanInvoiceRow (silver schema)."""
    return [
        CleanInvoiceRow(
            invoice_id=inv.invoice_id,
            carrier=inv.carrier_name,
            origin=inv.origin_zip,
            destination=inv.destination_zip,
            lane_id=inv.lane_id,
            shipment_weight_lb=inv.shipment_weight_lbs,
            billed_base_rate=inv.base_rate_charged,
            billed_fuel_surcharge_pct=inv.fuel_surcharge_pct_charged,
            billed_accessorial_fee=inv.accessorial_total(),
            billed_total_amount=inv.total_charged,
        )
        for inv in invoices
    ]


def write_processed_csv(rows: List[CleanInvoiceRow], output_path: Path | str) -> None:
    """Write cleaned invoices to data/processed/invoices_clean.csv."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([r.model_dump() for r in rows])
    df.to_csv(output_path, index=False)


def run_ingestion(
    raw_csv: Path | str | None = None,
    processed_csv: Path | str | None = None,
) -> List[CleanInvoiceRow]:
    """
    End-to-end ingestion: raw → models → processed CSV.
    Defaults to repo data/raw/freight_invoices.csv and data/processed/invoices_clean.csv.
    """
    root = _repo_root()
    raw_csv = Path(raw_csv or root / "data" / "raw" / "freight_invoices.csv")
    processed_csv = Path(processed_csv or root / "data" / "processed" / "invoices_clean.csv")

    invoices = load_raw_invoices_csv(raw_csv)
    clean_rows = invoices_to_clean_rows(invoices)
    write_processed_csv(clean_rows, processed_csv)
    return clean_rows
