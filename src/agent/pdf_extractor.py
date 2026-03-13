from __future__ import annotations

"""
PDF → structured invoice extraction layer.

Public API:
- extract_invoice_from_pdf(pdf_path: Path, page_number: int = 0) -> PDFExtractionResult
- extract_batch(pdf_paths: list[Path]) -> list[PDFExtractionResult]

This module:
- Selects an underlying InvoiceExtractionProvider (Gemini vs mock) based on
  environment configuration.
- Post-processes the provider output to compute missing_fields,
  low_confidence_fields, and requires_human_review.
- Never performs auditing or business-rule validation.
"""

from pathlib import Path
from typing import List
import os
import re

from loguru import logger
import pdfplumber

from src.agent.pdf_providers import (
    GeminiVisionProvider,
    GoogleDocumentAIProvider,
    InvoiceExtractionProvider,
    MockManifestProvider,
)
from src.engine.models import ExtractionConfidence, PDFExtractionResult


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


def _select_gemini_provider() -> InvoiceExtractionProvider:
    """Primary vision provider: Gemini (vision-capable LLM)."""
    logger.info("Using GeminiVisionProvider (model=gemini-2.5-flash)")
    return GeminiVisionProvider(model_name="gemini-2.5-flash")


def _select_mock_provider() -> InvoiceExtractionProvider:
    """Mock provider backed by synthetic manifest CSV."""
    root = Path(__file__).resolve().parents[2]
    manifest = root / "data" / "raw" / "pdf_invoices" / "manifest.csv"
    logger.info("Using MockManifestProvider with manifest at {}", manifest)
    return MockManifestProvider(manifest_path=manifest)


def _select_docai_provider() -> InvoiceExtractionProvider:
    """Primary document intelligence provider: Google Cloud Document AI."""
    logger.info("Using GoogleDocumentAIProvider (mode=docai)")
    return GoogleDocumentAIProvider()


def _compute_metadata(extraction: PDFExtractionResult) -> PDFExtractionResult:
    """
    Derive missing_fields, low_confidence_fields, and requires_human_review.

    The ExtractionConfidence is expected to be set by the provider / LLM,
    but requires_human_review is enforced here as overall_confidence != HIGH.
    """
    data = extraction.model_dump()

    missing: list[str] = []
    low_conf: list[str] = []

    for field in REQUIRED_FIELDS:
        if data.get(field) is None:
            missing.append(field)

    # We do not have per-field confidence objects in the schema; instead,
    # we rely on the LLM to populate low_confidence_fields when applicable.
    # If that list is already set, respect it; otherwise keep our computed one.
    existing_low = list(extraction.low_confidence_fields or [])
    if existing_low:
        low_conf = existing_low

    requires_review = extraction.overall_confidence != ExtractionConfidence.HIGH

    return extraction.model_copy(
        update={
            "missing_fields": missing,
            "low_confidence_fields": low_conf,
            "requires_human_review": requires_review,
        }
    )


def _failure_result(pdf_path: Path, error: Exception) -> PDFExtractionResult:
    return PDFExtractionResult(
        pdf_path=str(pdf_path),
        invoice_id=None,
        carrier_name=None,
        invoice_date=None,
        lane_id=None,
        origin_zip=None,
        destination_zip=None,
        shipment_weight_lbs=None,
        freight_class=None,
        base_rate_charged=None,
        fuel_surcharge_pct_charged=None,
        accessorial_liftgate=0.0,
        accessorial_residential=0.0,
        accessorial_inside_delivery=0.0,
        total_charged=None,
        overall_confidence=ExtractionConfidence.LOW,
        missing_fields=REQUIRED_FIELDS.copy(),
        low_confidence_fields=[],
        extraction_notes=f"Extraction failed: {error}",
        requires_human_review=True,
    )


def extract_invoice_from_pdf(
    pdf_path: Path,
    page_number: int = 0,
) -> PDFExtractionResult:
    """
    Convert a single PDF page into a structured PDFExtractionResult.

    Steps:
    1. Delegate PDF → image → LLM call to the active provider.
    2. Parse and validate the JSON into PDFExtractionResult.
    3. Compute metadata (missing_fields, low_confidence_fields, requires_human_review).
    4. If the selected AI provider fails and PDF_EXTRACTOR_MODE is not "mock",
       fall back to the manifest-backed mock provider.
    5. If all providers fail, return a LOW-confidence result with notes.
    """
    # Default to Document AI when no explicit mode is set.
    mode = os.getenv("PDF_EXTRACTOR_MODE", "docai").lower()

    # Hard override: always use the mock provider (no LLM calls).
    if mode == "mock":
        try:
            provider = _select_mock_provider()
            extraction = provider.extract_invoice(pdf_path, page_number=page_number)
            extraction = _compute_metadata(extraction)
            logger.info(
                "PDF extraction (mock) complete for {}: overall_confidence={}, missing_fields={}",
                pdf_path,
                extraction.overall_confidence,
                extraction.missing_fields,
            )
            return extraction
        except Exception as e:  # noqa: BLE001
            logger.error("Mock extraction pipeline failed for {}: {}", pdf_path, e)
            return _failure_result(pdf_path, e)

    # Mode: docai — try Document AI first, then fall back to mock.
    if mode == "docai":
        try:
            docai = _select_docai_provider()
            extraction = docai.extract_invoice(pdf_path, page_number=page_number)
            extraction = _compute_metadata(extraction)
            logger.info(
                "PDF extraction (DocAI) complete for {}: overall_confidence={}, missing_fields={}",
                pdf_path,
                extraction.overall_confidence,
                extraction.missing_fields,
            )
            return extraction
        except Exception as e:  # noqa: BLE001
            logger.error(
                "Document AI extraction failed for {}: {}. Falling back to mock provider.",
                pdf_path,
                e,
            )
            try:
                mock = _select_mock_provider()
                extraction = mock.extract_invoice(pdf_path, page_number=page_number)
                extraction = _compute_metadata(extraction)
                logger.info(
                    "PDF extraction (mock fallback) complete for {}: overall_confidence={}, missing_fields={}",
                    pdf_path,
                    extraction.overall_confidence,
                    extraction.missing_fields,
                )
                return extraction
            except Exception as mock_err:  # noqa: BLE001
                logger.error(
                    "Mock fallback extraction also failed for {}: {}", pdf_path, mock_err
                )
                return _failure_result(pdf_path, mock_err)

    # Default mode: try Gemini first, then fall back to mock on failure.
    try:
        gemini = _select_gemini_provider()
        extraction = gemini.extract_invoice(pdf_path, page_number=page_number)
        extraction = _compute_metadata(extraction)
        logger.info(
            "PDF extraction (Gemini) complete for {}: overall_confidence={}, missing_fields={}",
            pdf_path,
            extraction.overall_confidence,
            extraction.missing_fields,
        )
        return extraction
    except Exception as e:  # noqa: BLE001
        logger.error(
            "Gemini extraction failed for {}: {}. Falling back to mock provider.",
            pdf_path,
            e,
        )
        try:
            mock = _select_mock_provider()
            extraction = mock.extract_invoice(pdf_path, page_number=page_number)
            extraction = _compute_metadata(extraction)
            logger.info(
                "PDF extraction (mock fallback) complete for {}: overall_confidence={}, missing_fields={}",
                pdf_path,
                extraction.overall_confidence,
                extraction.missing_fields,
            )
            return extraction
        except Exception as mock_err:  # noqa: BLE001
            logger.error(
                "Mock fallback extraction also failed for {}: {}", pdf_path, mock_err
            )
            return _failure_result(pdf_path, mock_err)


def extract_batch(
    pdf_paths: List[Path],
) -> List[PDFExtractionResult]:
    """
    Process a list of PDFs sequentially.

    - Never raises; failures are encoded as LOW-confidence results.
    - Returns results in the same order as input.
    """
    results: List[PDFExtractionResult] = []
    total = len(pdf_paths)
    for idx, pdf_path in enumerate(pdf_paths, start=1):
        logger.info("Extracting {}/{}: {}", idx, total, pdf_path.name)
        extraction = extract_invoice_from_pdf(pdf_path, page_number=0)
        results.append(extraction)
    return results


def extract_invoices_from_pdf(
    pdf_path: Path,
    page_number: int = 0,
) -> List[PDFExtractionResult]:
    """
    Extract zero or more invoices from a single PDF file.

    For generic invoices, this delegates to extract_invoice_from_pdf and
    returns a single-element list. For simple batch PDFs generated by
    generate_pdf_and_csv_invoices.py (e.g. invoices_sample.pdf), it will
    parse each invoice line and return one PDFExtractionResult per row.
    """
    # Special-case: handle realistic single-invoice examples generated under data/example
    if pdf_path.name.lower().startswith("example_invoice_") and pdf_path.suffix.lower() == ".pdf":
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                page = pdf.pages[page_number]
                text = page.extract_text() or ""

            # Simple regex-based parsing tailored to generate_example_invoices.py layout
            def _search(pattern: str) -> str | None:
                m = re.search(pattern, text, re.MULTILINE)
                return m.group(1).strip() if m else None

            invoice_id = _search(r"Invoice ID:\s*(\S+)")
            invoice_date = _search(r"Invoice Date:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})")
            lane_id = _search(r"Lane ID:\s*(\S+)")

            origin_line = _search(r"Origin:\s*(.+)")
            dest_line = _search(r"Destination:\s*(.+)")
            origin_zip = None
            destination_zip = None
            if origin_line:
                m = re.search(r"(\d{5})", origin_line)
                if m:
                    origin_zip = m.group(1)
            if dest_line:
                m = re.search(r"(\d{5})", dest_line)
                if m:
                    destination_zip = m.group(1)

            # Weight / base / fuel summary
            weight_str = _search(r"Weight:\s*([\d,]+)\s*lbs")
            base_rate_str = _search(r"Base Rate:\s*\$?([\d\.]+)")
            fuel_pct_str = _search(r"Fuel:\s*([\d\.]+)%")

            def _to_float(val: str | None) -> float | None:
                if not val:
                    return None
                try:
                    return float(val.replace(",", ""))
                except ValueError:
                    return None

            shipment_weight_lbs = _to_float(weight_str)
            base_rate_per_lb = _to_float(base_rate_str)
            fuel_pct = _to_float(fuel_pct_str)
            fuel_pct_decimal = fuel_pct / 100.0 if fuel_pct is not None else None

            # Charges table amounts
            def _charge(label: str) -> float:
                m = re.search(rf"{re.escape(label)}.*\$\s*([\d,]+\.\d+)", text)
                if not m:
                    return 0.0
                try:
                    return float(m.group(1).replace(",", ""))
                except ValueError:
                    return 0.0

            base_freight = _charge("Base Freight")
            fuel_amt = _charge("Fuel Surcharge")
            liftgate = _charge("Accessorial - Liftgate")
            residential = _charge("Accessorial - Residential Delivery")
            inside = _charge("Accessorial - Inside Delivery")
            total = _charge("TOTAL CHARGED")

            extraction = PDFExtractionResult(
                pdf_path=str(pdf_path),
                invoice_id=invoice_id,
                carrier_name=_search(r"^(.*)$"),  # first line is carrier name
                invoice_date=invoice_date,
                lane_id=lane_id,
                origin_zip=origin_zip,
                destination_zip=destination_zip,
                shipment_weight_lbs=shipment_weight_lbs,
                freight_class="CLASS_70",
                base_rate_charged=base_rate_per_lb,
                fuel_surcharge_pct_charged=fuel_pct_decimal,
                accessorial_liftgate=liftgate,
                accessorial_residential=residential,
                accessorial_inside_delivery=inside,
                total_charged=total if total != 0.0 else None,
                overall_confidence=ExtractionConfidence.MEDIUM,
                missing_fields=[],
                low_confidence_fields=[],
                extraction_notes="Parsed from example invoice layout",
                requires_human_review=True,
            )
            logger.info(
                "Parsed example invoice from {}: invoice_id={}, total={}",
                pdf_path.name,
                extraction.invoice_id,
                extraction.total_charged,
            )
            return [_compute_metadata(extraction)]
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to parse example invoice PDF {}: {}", pdf_path, e)

    # Special-case: handle synthetic batch PDF created by generate_pdf_and_csv_invoices.py
    if pdf_path.name.lower().startswith("invoices_sample") and pdf_path.suffix.lower() == ".pdf":
        extractions: List[PDFExtractionResult] = []
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                pattern = re.compile(
                    r"^(?P<invoice_id>INV-\d{4}-\d{4}) \| Lane: (?P<lane_id>\S+) \| Total: \$?(?P<total_charged>[\d\.]+)"
                )
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    for line in text.splitlines():
                        m = pattern.match(line.strip())
                        if not m:
                            continue
                        invoice_id = m.group("invoice_id")
                        lane_id = m.group("lane_id")
                        total_str = m.group("total_charged")
                        try:
                            total_val = float(total_str)
                        except ValueError:
                            total_val = None
                        extractions.append(
                            PDFExtractionResult(
                                pdf_path=str(pdf_path),
                                invoice_id=invoice_id,
                                carrier_name=None,
                                invoice_date=None,
                                lane_id=lane_id,
                                origin_zip=None,
                                destination_zip=None,
                                shipment_weight_lbs=None,
                                freight_class=None,
                                base_rate_charged=None,
                                fuel_surcharge_pct_charged=None,
                                accessorial_liftgate=0.0,
                                accessorial_residential=0.0,
                                accessorial_inside_delivery=0.0,
                                total_charged=total_val,
                                overall_confidence=ExtractionConfidence.LOW,
                                missing_fields=[],
                                low_confidence_fields=[],
                                extraction_notes="Parsed from batch PDF line",
                                requires_human_review=True,
                            )
                        )
            if extractions:
                logger.info(
                    "Parsed {} invoice rows from batch PDF {}",
                    len(extractions),
                    pdf_path.name,
                )
                # Compute metadata (missing fields, requires review) for each extraction
                return [_compute_metadata(e) for e in extractions]
        except Exception as e:  # noqa: BLE001
            logger.error("Failed to parse batch PDF {}: {}", pdf_path, e)

    # Fallback: single-invoice behavior.
    single = extract_invoice_from_pdf(pdf_path, page_number=page_number)
    return [single]


__all__ = ["extract_invoice_from_pdf", "extract_batch", "extract_invoices_from_pdf"]

