"""
Data contracts for the freight billing audit pipeline.
Aligned with Engineering SPEC (master rate table + invoice dataset).
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

# --- Engineering SPEC §3 / §4.1 — Audit outputs ---
#
# AuditFinding: deterministic rule output; violation_type ≡ rule_id;
# expected_value ≡ contract_value; actual_value ≡ charged_value.


class RateContract(BaseModel):
    """
    Ground truth: negotiated contract terms (simulated SAP/ERP export).
    Persists as data/reference/master_rate_table.csv.
    """

    lane_id: str = Field(..., description="Unique ID for origin→destination pair")
    carrier_name: str
    origin_zip: str = Field(..., min_length=5, max_length=5)
    destination_zip: str = Field(..., min_length=5, max_length=5)
    agreed_base_rate_per_lb: float = Field(..., ge=0, description="Contract $/lb")
    fuel_surcharge_pct: float = Field(
        ..., ge=0, le=1, description="Decimal, e.g. 0.142 = 14.2%"
    )
    allowed_accessorials: str = Field(
        ...,
        description="Pipe-delimited list, e.g. inside_delivery|residential",
    )
    effective_date: date
    expiration_date: date

    model_config = {"extra": "forbid"}


class FreightInvoice(BaseModel):
    """
    Raw invoice line as structured table (simulated PDF parse output).
    Persists as data/raw/freight_invoices.csv.
    """

    invoice_id: str
    carrier_name: str
    invoice_date: date
    lane_id: str
    origin_zip: str
    destination_zip: str
    shipment_weight_lbs: float = Field(..., gt=0)
    freight_class: str
    base_rate_charged: float = Field(..., ge=0)
    fuel_surcharge_pct_charged: float = Field(..., ge=0, le=1)
    accessorial_liftgate: float = Field(default=0.0, ge=0)
    accessorial_residential: float = Field(default=0.0, ge=0)
    accessorial_inside_delivery: float = Field(default=0.0, ge=0)
    total_charged: float = Field(..., ge=0)

    model_config = {"extra": "forbid"}

    def accessorial_total(self) -> float:
        return (
            self.accessorial_liftgate
            + self.accessorial_residential
            + self.accessorial_inside_delivery
        )


class AuditFinding(BaseModel):
    """
    Engineering SPEC §4.1 — structured result per rule firing.
    Maps to product columns: violation_type=rule_id, expected_value=contract_value,
    actual_value=charged_value; variance uses variance_pct or rule-specific delta.
    """

    invoice_id: str
    rule_id: str  # e.g. "FUEL_SURCHARGE_OVERAGE", "MISSING_CONTRACT"
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    field_audited: str
    charged_value: float
    contract_value: float
    variance_pct: float  # (charged - contract) / contract when contract != 0
    dollar_impact: float
    description: str

    model_config = {"extra": "forbid"}

    def to_product_dict(self) -> dict:
        """Flat dict with product column names (violation_type, expected, actual)."""
        return {
            "invoice_id": self.invoice_id,
            "violation_type": self.rule_id,
            "expected_value": self.contract_value,
            "actual_value": self.charged_value,
            "variance": self.variance_pct,
            "severity": self.severity,
            "dollar_impact": self.dollar_impact,
            "description": self.description,
        }


class CleanInvoiceRow(BaseModel):
    """
    Normalized / silver layer fields for policy engine consumption.
    Maps to data/processed/invoices_clean.csv (Product SPEC naming).
    """

    invoice_id: str
    carrier: str
    origin: str
    destination: str
    lane_id: str
    shipment_weight_lb: float
    billed_base_rate: float
    billed_fuel_surcharge_pct: float
    billed_accessorial_fee: float
    billed_total_amount: float

    model_config = {"extra": "forbid"}


class LLMExplanation(BaseModel):
    """
    LLM-side explanation of deterministic audit findings for a single invoice.
    The LLM does not compute pass/fail; it only explains existing findings.
    """

    invoice_id: str
    summary: str
    findings_explained: list[str]
    total_recovery_opportunity: float
    dispute_recommended: bool
    dispute_message: str
    confidence: Literal["HIGH", "MEDIUM", "LOW"]

    model_config = {"extra": "forbid"}


class AuditResult(BaseModel):
    """
    Aggregated view per invoice: raw invoice, findings, and optional LLM explanation.
    This is what the service layer returns to the UI.
    """

    invoice: FreightInvoice
    findings: list[AuditFinding]
    explanation: Optional[LLMExplanation] = None

    model_config = {"extra": "forbid"}

    @property
    def total_dollar_impact(self) -> float:
        return sum(f.dollar_impact for f in self.findings)

    @property
    def has_errors(self) -> bool:
        return bool(self.findings)

    @property
    def max_severity(self) -> Optional[str]:
        if not self.findings:
            return None
        order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        return max(self.findings, key=lambda f: order.get(f.severity, 0)).severity


__all__ = [
    "RateContract",
    "FreightInvoice",
    "AuditFinding",
    "CleanInvoiceRow",
    "LLMExplanation",
    "AuditResult",
]
