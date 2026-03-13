from __future__ import annotations

"""
Provider interfaces and implementations for PDF → structured invoice extraction.

This layer is intentionally backend-agnostic so we can plug in different
OCR / Document AI systems (Gemini Vision, Azure Document Intelligence, mock).

Design rules:
- Providers perform OCR and field extraction only.
- They NEVER perform auditing, pricing validation, or policy decisions.
- They always return a PDFExtractionResult, even on failure.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Protocol
import base64
import os
import json
from decimal import Decimal

from dotenv import load_dotenv
from google import genai
from google.cloud import documentai_v1 as documentai
from loguru import logger
from PIL import Image
from pdf2image import convert_from_path

from src.engine.models import (
    ExtractionConfidence,
    PDFExtractionResult,
)


load_dotenv()


SYSTEM_PROMPT = """
You are a freight invoice data extraction specialist.
You will be shown an image of a freight carrier invoice.
Extract structured data and return ONLY valid JSON — no markdown, no backticks.

For each field:
- Extract the value exactly as it appears, then normalize it
- If a field is missing or unclear, return null
- Never invent or estimate values you cannot clearly read

Field normalization rules:
- Dates: return as "YYYY-MM-DD"
- Dollar amounts: return as float, no $ sign (e.g. 1250.75)
- Fuel surcharge: if shown as percentage like "14.2%", return 0.142 as float
- Weight: return numeric value only, no "lbs" suffix
- ZIP codes: 5 digits only
- Lane ID: look for a field labeled "Lane ID", "Lane", or "Route ID"

Confidence scoring per field (include in your response):
- 1.0: field clearly labeled and value unambiguous
- 0.7: field found but label was non-standard or value required inference
- 0.4: field inferred from context, not explicitly labeled
- 0.0: field not found

After extracting all fields, assess overall_confidence:
- HIGH: all required fields found with confidence >= 0.7
- MEDIUM: 1-2 required fields missing or confidence < 0.7
- LOW: 3+ required fields missing or total_charged unreadable

Required fields: invoice_id, carrier_name, invoice_date, 
origin_zip, destination_zip, shipment_weight_lbs, 
base_rate_charged, fuel_surcharge_pct_charged, total_charged
""".strip()


def _pdf_extraction_schema_json() -> str:
    """
    Hand-authored JSON schema description for the user prompt.

    We keep this separate so it is easy to tweak without changing
    the Pydantic models or the system prompt.
    """
    schema = {
        "pdf_path": "string path to the PDF file (for reference)",
        "invoice_id": "string or null — invoice number from the PDF",
        "carrier_name": "string or null — carrier name exactly as shown, normalized",
        "invoice_date": 'string "YYYY-MM-DD" or null — invoice date',
        "lane_id": "string or null — lane/route identifier if present",
        "origin_zip": "string or null — 5-digit origin ZIP code",
        "destination_zip": "string or null — 5-digit destination ZIP code",
        "shipment_weight_lbs": "number or null — total shipment weight in lbs",
        "freight_class": "string or null — freight class label if present",
        "base_rate_charged": "number or null — base rate per lb charged on invoice",
        "fuel_surcharge_pct_charged": "number or null — decimal fuel surcharge (0.142 for 14.2%)",
        "accessorial_liftgate": "number — total $ liftgate fees (0 if none)",
        "accessorial_residential": "number — total $ residential delivery fees (0 if none)",
        "accessorial_inside_delivery": "number — total $ inside delivery fees (0 if none)",
        "total_charged": "number or null — total billed amount on the invoice",
        "overall_confidence": 'one of "HIGH", "MEDIUM", "LOW"',
        "missing_fields": "array of strings — any required fields that are null",
        "low_confidence_fields": "array of strings — fields with confidence < 0.7",
        "extraction_notes": "string — free-form notes about ambiguities",
        "requires_human_review": "boolean — true if overall_confidence != HIGH",
    }
    return json.dumps(schema, indent=2)


class InvoiceExtractionProvider(Protocol):
    """
    Backend-agnostic contract for invoice extraction from PDFs.

    Implementations must:
    - Accept PDF file paths and page numbers.
    - Return PDFExtractionResult objects.
    - Never raise for individual extraction failures; instead, encode errors
      in the returned PDFExtractionResult (LOW confidence + notes).
    """

    def extract_invoice(self, pdf_path: Path, page_number: int = 0) -> PDFExtractionResult:
        ...

    def extract_batch(self, pdf_paths: List[Path]) -> List[PDFExtractionResult]:
        ...


@dataclass
class GeminiVisionProvider:
    """
    Vision-capable LLM provider using Google Gemini.

    This class owns:
    - pdf2image conversion from PDF page → PIL.Image
    - base64 encoding of the image for Gemini
    - building prompts and parsing JSON into PDFExtractionResult
    """

    model_name: str = "gemini-2.0-flash"

    def __post_init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not found in environment/.env")
        self._client = genai.Client(api_key=api_key)

    def _render_page(self, pdf_path: Path, page_number: int) -> Image.Image:
        poppler_path = os.getenv("POPPLER_PATH")  # points to folder with pdftoppm.exe
        pages = convert_from_path(
            str(pdf_path),
            first_page=page_number + 1,
            last_page=page_number + 1,
            poppler_path=poppler_path,
        )
        if not pages:
            raise ValueError(f"No pages rendered for {pdf_path}")
        return pages[0]

    def _image_to_base64(self, image: Image.Image) -> str:
        import io

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        data = buf.getvalue()
        return base64.b64encode(data).decode("utf-8")

    def extract_invoice(self, pdf_path: Path, page_number: int = 0) -> PDFExtractionResult:
        try:
            image = self._render_page(pdf_path, page_number)
            b64 = self._image_to_base64(image)

            user_prompt = (
                "Extract all freight invoice fields from this invoice image.\n"
                "Return JSON matching exactly this schema (keys and types):\n"
                f"{_pdf_extraction_schema_json()}"
            )

            logger.info("Calling Gemini vision model for PDF: {}", pdf_path)
            resp = self._client.models.generate_content(
                model=self.model_name,
                contents=[
                    {"role": "model", "parts": [{"text": SYSTEM_PROMPT}]},
                    {
                        "role": "user",
                        "parts": [
                            {"text": user_prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/png",
                                    "data": b64,
                                }
                            },
                        ],
                    },
                ],
            )

            text = resp.candidates[0].content.parts[0].text  # type: ignore[assignment]
            raw = json.loads(text)
            # Ensure pdf_path is set to the actual path used.
            raw.setdefault("pdf_path", str(pdf_path))

            extraction = PDFExtractionResult.model_validate(raw)

            # The provider focuses on primary fields; derived metadata is computed
            # in the orchestrator, but we can pre-populate notes here.
            usage = getattr(resp, "usage_metadata", None)
            token_total = getattr(usage, "total_token_count", None)
            logger.info(
                "Gemini extraction ok for {} (overall_confidence={}, tokens={})",
                pdf_path,
                extraction.overall_confidence,
                token_total,
            )
            return extraction
        except Exception as e:  # noqa: BLE001
            logger.error("Gemini extraction failed for {}: {}", pdf_path, e)
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
                missing_fields=[],
                low_confidence_fields=[],
                extraction_notes=f"Extraction failed: {e}",
                requires_human_review=True,
            )

    def extract_batch(self, pdf_paths: List[Path]) -> List[PDFExtractionResult]:
        results: List[PDFExtractionResult] = []
        total = len(pdf_paths)
        for idx, p in enumerate(pdf_paths, start=1):
            logger.info("Extracting {}/{}: {}", idx, total, p.name)
            results.append(self.extract_invoice(p))
        return results


@dataclass
class MockManifestProvider:
    """
    Mock provider that simulates perfect extraction from a manifest CSV.

    This is used for:
    - Offline / test runs without LLM calls
    - Measuring the normalizer and policy engine in isolation
    """

    manifest_path: Path

    def __post_init__(self) -> None:
        import pandas as pd

        if not self.manifest_path.exists():
            raise FileNotFoundError(
                f"Mock manifest not found at {self.manifest_path}. "
                "Generate synthetic PDFs and manifest first."
            )
        df = pd.read_csv(self.manifest_path)
        # Index rows by pdf_filename for quick lookup.
        self._by_pdf: dict[str, dict] = {}
        for _, row in df.iterrows():
            record = row.to_dict()
            pdf_name = str(record.get("pdf_filename") or record.get("pdf_path"))
            if pdf_name:
                self._by_pdf[pdf_name] = record

    def _row_to_extraction(self, pdf_path: Path, row: dict) -> PDFExtractionResult:
        return PDFExtractionResult(
            pdf_path=str(pdf_path),
            invoice_id=str(row.get("invoice_id")) if row.get("invoice_id") is not None else None,
            carrier_name=str(row.get("carrier_name")) if row.get("carrier_name") is not None else None,
            invoice_date=row.get("invoice_date"),
            lane_id=str(row.get("lane_id")) if row.get("lane_id") is not None else None,
            origin_zip=str(row.get("origin_zip")) if row.get("origin_zip") is not None else None,
            destination_zip=str(row.get("destination_zip")) if row.get("destination_zip") is not None else None,
            shipment_weight_lbs=float(row.get("shipment_weight_lbs")) if row.get("shipment_weight_lbs") is not None else None,
            freight_class=str(row.get("freight_class")) if row.get("freight_class") is not None else None,
            base_rate_charged=float(row.get("base_rate_charged")) if row.get("base_rate_charged") is not None else None,
            fuel_surcharge_pct_charged=float(row.get("fuel_surcharge_pct_charged")) if row.get("fuel_surcharge_pct_charged") is not None else None,
            accessorial_liftgate=float(row.get("accessorial_liftgate") or 0.0),
            accessorial_residential=float(row.get("accessorial_residential") or 0.0),
            accessorial_inside_delivery=float(row.get("accessorial_inside_delivery") or 0.0),
            total_charged=float(row.get("total_charged")) if row.get("total_charged") is not None else None,
            overall_confidence=ExtractionConfidence.HIGH,
            missing_fields=[],
            low_confidence_fields=[],
            extraction_notes="Mock extraction from manifest.csv",
            requires_human_review=False,
        )

    def extract_invoice(self, pdf_path: Path, page_number: int = 0) -> PDFExtractionResult:  # noqa: ARG002
        key = pdf_path.name
        row = self._by_pdf.get(key)
        if row is None:
            logger.warning("No manifest row found for {}; returning LOW confidence.", key)
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
                missing_fields=[],
                low_confidence_fields=[],
                extraction_notes="Extraction failed: no manifest row for PDF",
                requires_human_review=True,
            )
        return self._row_to_extraction(pdf_path, row)

    def extract_batch(self, pdf_paths: List[Path]) -> List[PDFExtractionResult]:
        results: List[PDFExtractionResult] = []
        total = len(pdf_paths)
        for idx, p in enumerate(pdf_paths, start=1):
            logger.info("Mock extracting {}/{}: {}", idx, total, p.name)
            results.append(self.extract_invoice(p))
        return results


@dataclass
class GoogleDocumentAIProvider:
    """
    Provider that uses Google Cloud Document AI to extract fields from PDFs.

    This implementation assumes you have:
    - DOC_AI_PROJECT_ID
    - DOC_AI_LOCATION (e.g. 'us')
    - DOC_AI_PROCESSOR_ID (processor configured for invoices/forms)
    - GOOGLE_APPLICATION_CREDENTIALS pointing to a service account JSON.
    """

    project_id: str | None = None
    location: str | None = None
    processor_id: str | None = None

    def __post_init__(self) -> None:
        project_id = self.project_id or os.getenv("DOC_AI_PROJECT_ID")
        location = self.location or os.getenv("DOC_AI_LOCATION", "us")
        processor_id = self.processor_id or os.getenv("DOC_AI_PROCESSOR_ID")

        if not project_id or not processor_id:
            raise RuntimeError(
                "Document AI configuration missing. "
                "Set DOC_AI_PROJECT_ID, DOC_AI_LOCATION, DOC_AI_PROCESSOR_ID."
            )

        self.project_id = project_id
        self.location = location
        self.processor_id = processor_id

        self._client = documentai.DocumentProcessorServiceClient()
        self._processor_name = self._client.processor_path(
            project_id, location, processor_id
        )
        logger.info(
            "Initialized GoogleDocumentAIProvider with processor {}",
            self._processor_name,
        )

    # --- Helpers to extract structured values from Document AI responses ---

    @staticmethod
    def _get_entity_text(doc: documentai.Document, type_candidates: List[str]) -> str | None:
        """
        Find the first entity whose type matches any of the candidate strings.
        """
        if not getattr(doc, "entities", None):
            return None
        types = {t.lower() for t in type_candidates}
        for ent in doc.entities:
            ent_type = getattr(ent, "type_", "") or getattr(ent, "type", "")
            if ent_type and ent_type.lower() in types:
                text = ent.mention_text or ent.normalized_value.text
                return text or None
        return None

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            # Strip common symbols like $ or % if present.
            cleaned = value.replace("$", "").replace(",", "").strip()
            if cleaned.endswith("%"):
                cleaned = cleaned[:-1]
            return float(Decimal(cleaned))
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _parse_date(value: str | None) -> str | None:
        if not value:
            return None
        # Rely on Document AI normalization or pass through; the normalizer will parse.
        return value

    def extract_invoice(self, pdf_path: Path, page_number: int = 0) -> PDFExtractionResult:  # noqa: ARG002
        try:
            with pdf_path.open("rb") as f:
                content = f.read()

            logger.info("Calling Document AI for PDF: {}", pdf_path)
            request = documentai.ProcessRequest(
                name=self._processor_name,
                raw_document=documentai.RawDocument(
                    content=content,
                    mime_type="application/pdf",
                ),
            )
            result = self._client.process_document(request=request)
            doc = result.document

            # Heuristic mapping: assumes the processor is configured to label
            # entities with intuitive type names like 'invoice_id', 'vendor',
            # 'total_amount', etc. These can be tuned to your processor.
            invoice_id_text = self._get_entity_text(doc, ["invoice_id", "invoice-id"])
            carrier_text = self._get_entity_text(doc, ["carrier_name", "vendor", "supplier"])
            date_text = self._get_entity_text(doc, ["invoice_date", "date"])
            origin_zip_text = self._get_entity_text(doc, ["origin_zip", "ship_from_zip"])
            dest_zip_text = self._get_entity_text(doc, ["destination_zip", "ship_to_zip"])
            weight_text = self._get_entity_text(doc, ["shipment_weight_lbs", "weight"])
            base_rate_text = self._get_entity_text(doc, ["base_rate_charged", "base_rate"])
            fuel_text = self._get_entity_text(doc, ["fuel_surcharge_pct_charged", "fuel_surcharge"])
            total_text = self._get_entity_text(doc, ["total_charged", "total_amount"])

            liftgate_text = self._get_entity_text(doc, ["accessorial_liftgate", "liftgate"])
            residential_text = self._get_entity_text(doc, ["accessorial_residential", "residential"])
            inside_text = self._get_entity_text(doc, ["accessorial_inside_delivery", "inside_delivery"])

            extraction = PDFExtractionResult(
                pdf_path=str(pdf_path),
                invoice_id=invoice_id_text,
                carrier_name=carrier_text,
                invoice_date=self._parse_date(date_text),
                lane_id=None,  # can be inferred later from zips/rate table
                origin_zip=origin_zip_text,
                destination_zip=dest_zip_text,
                shipment_weight_lbs=self._parse_float(weight_text),
                freight_class=None,
                base_rate_charged=self._parse_float(base_rate_text),
                fuel_surcharge_pct_charged=self._parse_float(fuel_text),
                accessorial_liftgate=self._parse_float(liftgate_text) or 0.0,
                accessorial_residential=self._parse_float(residential_text) or 0.0,
                accessorial_inside_delivery=self._parse_float(inside_text) or 0.0,
                total_charged=self._parse_float(total_text),
                overall_confidence=ExtractionConfidence.MEDIUM,  # refined by normalizer/metadata
                missing_fields=[],
                low_confidence_fields=[],
                extraction_notes="Extracted via Google Document AI",
                requires_human_review=True,  # updated later by metadata computation
            )

            logger.info(
                "Document AI extraction ok for {} (invoice_id={}, total={})",
                pdf_path,
                extraction.invoice_id,
                extraction.total_charged,
            )
            return extraction
        except Exception as e:  # noqa: BLE001
            logger.error("Document AI extraction failed for {}: {}", pdf_path, e)
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
                missing_fields=[],
                low_confidence_fields=[],
                extraction_notes=f"Extraction failed: {e}",
                requires_human_review=True,
            )

    def extract_batch(self, pdf_paths: List[Path]) -> List[PDFExtractionResult]:
        results: List[PDFExtractionResult] = []
        total = len(pdf_paths)
        for idx, p in enumerate(pdf_paths, start=1):
            logger.info("DocAI extracting {}/{}: {}", idx, total, p.name)
            results.append(self.extract_invoice(p))
        return results


__all__ = [
    "InvoiceExtractionProvider",
    "GeminiVisionProvider",
    "MockManifestProvider",
    "GoogleDocumentAIProvider",
]

