from __future__ import annotations

"""
Deterministic normalization from PDFExtractionResult → FreightInvoice.

This module is the bridge between the OCR/LLM extraction layer and the
deterministic policy engine. It:
- Applies business rules and fallbacks.
- Produces validated FreightInvoice models or clear normalization errors.
- Does NOT call any LLMs or external services.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from datetime import date
import difflib

from pydantic import BaseModel, ValidationError

from src.engine.models import (
    ExtractionConfidence,
    FreightInvoice,
    PDFExtractionResult,
    RateContract,
)


REQUIRED_FIELDS = [
    "invoice_id",
    "carrier_name",
    "invoice_date",
    "origin_zip",
    "destination_zip",
    "shipment_weight_lbs",
    "base_rate_charged",
    "fuel_surcharge_pct_charged",
    "total_charged",
]


class NormalizationResult(BaseModel):
    invoice: FreightInvoice | None = None
    extraction: PDFExtractionResult
    normalization_warnings: List[str] = []
    normalization_errors: List[str] = []
    ready_for_engine: bool = False


def _has_missing_required(extraction: PDFExtractionResult) -> bool:
    data = extraction.model_dump()
    return any(data.get(field) is None for field in REQUIRED_FIELDS)


def _normalize_carrier_name(
    carrier_name: str | None,
    rate_table: Dict[Tuple[str, str], RateContract],
    warnings: List[str],
) -> str | None:
    if not carrier_name:
        return None
    carriers = {c.carrier_name for c in rate_table.values()}
    if not carriers:
        return carrier_name
    match = difflib.get_close_matches(carrier_name, list(carriers), n=1, cutoff=0.85)
    if match:
        canon = match[0]
        if canon != carrier_name:
            warnings.append(
                f'Carrier name "{carrier_name}" normalized to canonical "{canon}".'
            )
        return canon
    warnings.append(f'Carrier name "{carrier_name}" not found in rate table; using as-is.')
    return carrier_name


def _infer_lane_id_from_zips(
    origin_zip: str | None,
    destination_zip: str | None,
    carrier_name: str | None,
    rate_table: Dict[Tuple[str, str], RateContract],
    warnings: List[str],
    errors: List[str],
) -> str | None:
    if not origin_zip or not destination_zip:
        errors.append("Missing origin_zip or destination_zip; cannot infer lane_id.")
        return None

    # Try to find a matching contract by zip pair (optionally considering carrier).
    candidates: List[RateContract] = []
    for contract in rate_table.values():
        if contract.origin_zip == origin_zip and contract.destination_zip == destination_zip:
            if carrier_name and contract.carrier_name != carrier_name:
                continue
            candidates.append(contract)

    if not candidates:
        errors.append(
            f"No lane in rate table for {origin_zip} → {destination_zip} (carrier={carrier_name or 'ANY'})."
        )
        return None

    lane_id = candidates[0].lane_id
    warnings.append("Lane ID inferred from ZIP pair.")
    return lane_id


def _normalize_fuel_surcharge(
    value: float | None,
    warnings: List[str],
) -> float:
    if value is None:
        warnings.append("Fuel surcharge missing — defaulted to 0.0.")
        return 0.0
    if value > 1.0:
        warnings.append(
            f"Fuel surcharge {value} interpreted as percentage; dividing by 100."
        )
        value = value / 100.0
    if value <= 0:
        warnings.append("Fuel surcharge is zero — verify.")
    return float(value)


def _validate_total_charged(
    weight: float,
    base_rate: float,
    fuel_pct: float,
    liftgate: float,
    residential: float,
    inside_delivery: float,
    extracted_total: float | None,
    warnings: List[str],
) -> None:
    expected = (weight * base_rate) * (1.0 + fuel_pct) + liftgate + residential + inside_delivery
    if extracted_total is None:
        warnings.append("total_charged is missing; cannot compare to expected.")
        return
    delta = abs(extracted_total - expected)
    if delta > 5.0:
        warnings.append(
            f"Total charged ${extracted_total:.2f} differs from expected ${expected:.2f} by ${delta:.2f}."
        )


def normalize_extraction(
    extraction: PDFExtractionResult,
    rate_table: Dict[Tuple[str, str], RateContract],
) -> NormalizationResult:
    """
    Convert extracted PDF fields → validated FreightInvoice.
    Applies business rules and fallbacks before Pydantic validation.
    """
    warnings: List[str] = []
    errors: List[str] = []

    # 1. Block if requires_human_review and any required field is None.
    if extraction.requires_human_review and _has_missing_required(extraction):
        errors.append("Extraction confidence too low for automated processing")
        return NormalizationResult(
            invoice=None,
            extraction=extraction,
            normalization_warnings=warnings,
            normalization_errors=errors,
            ready_for_engine=False,
        )

    data = extraction.model_dump()

    # 2. Carrier name normalization.
    carrier_name = _normalize_carrier_name(
        extraction.carrier_name,
        rate_table,
        warnings,
    )

    # 3. Lane ID resolution.
    lane_id = extraction.lane_id
    if lane_id is None:
        lane_id = _infer_lane_id_from_zips(
            extraction.origin_zip,
            extraction.destination_zip,
            carrier_name,
            rate_table,
            warnings,
            errors,
        )
        if lane_id is None:
            return NormalizationResult(
                invoice=None,
                extraction=extraction,
                normalization_warnings=warnings,
                normalization_errors=errors,
                ready_for_engine=False,
            )

    # 4. Fuel surcharge normalization.
    fuel_pct = _normalize_fuel_surcharge(
        extraction.fuel_surcharge_pct_charged,
        warnings,
    )

    # 5. Accessorial normalization — direct mapping for now.
    liftgate = float(extraction.accessorial_liftgate or 0.0)
    residential = float(extraction.accessorial_residential or 0.0)
    inside_delivery = float(extraction.accessorial_inside_delivery or 0.0)

    # 6. Total charged validation.
    if (
        extraction.shipment_weight_lbs is not None
        and extraction.base_rate_charged is not None
    ):
        _validate_total_charged(
            weight=float(extraction.shipment_weight_lbs),
            base_rate=float(extraction.base_rate_charged),
            fuel_pct=fuel_pct,
            liftgate=liftgate,
            residential=residential,
            inside_delivery=inside_delivery,
            extracted_total=float(extraction.total_charged) if extraction.total_charged is not None else None,
            warnings=warnings,
        )

    # 7. Construct FreightInvoice fields.
    fields = {
        "invoice_id": extraction.invoice_id or "",
        "carrier_name": carrier_name or "",
        "invoice_date": extraction.invoice_date or date.today(),
        "lane_id": lane_id,
        "origin_zip": (extraction.origin_zip or "").zfill(5)[:5],
        "destination_zip": (extraction.destination_zip or "").zfill(5)[:5],
        "shipment_weight_lbs": float(extraction.shipment_weight_lbs or 0.0),
        "freight_class": extraction.freight_class or "UNKNOWN",
        "base_rate_charged": float(extraction.base_rate_charged or 0.0),
        "fuel_surcharge_pct_charged": fuel_pct,
        "accessorial_liftgate": liftgate,
        "accessorial_residential": residential,
        "accessorial_inside_delivery": inside_delivery,
        "total_charged": float(extraction.total_charged or 0.0),
    }
    if not extraction.freight_class:
        warnings.append('Freight class missing; defaulted to "UNKNOWN".')

    try:
        invoice = FreightInvoice(**fields)
    except ValidationError as ve:
        for err in ve.errors():
            loc = ".".join(str(x) for x in err.get("loc", []))
            msg = err.get("msg", "validation error")
            errors.append(f"{loc}: {msg}")
        return NormalizationResult(
            invoice=None,
            extraction=extraction,
            normalization_warnings=warnings,
            normalization_errors=errors,
            ready_for_engine=False,
        )

    return NormalizationResult(
        invoice=invoice,
        extraction=extraction,
        normalization_warnings=warnings,
        normalization_errors=errors,
        ready_for_engine=True,
    )


def normalize_batch(
    extractions: List[PDFExtractionResult],
    rate_table: Dict[Tuple[str, str], RateContract],
) -> List[NormalizationResult]:
    return [normalize_extraction(e, rate_table) for e in extractions]


__all__ = ["NormalizationResult", "normalize_extraction", "normalize_batch"]

