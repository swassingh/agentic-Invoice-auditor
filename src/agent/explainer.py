"""
LLM explainer for deterministic audit findings.

Design rules:
- Receives findings the engine already produced.
- Explains them in natural language for finance users.
- Never re-audits, re-computes math, or decides pass/fail.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Tuple

from dotenv import load_dotenv
from google import genai
from google.genai.types import GenerationConfig
from loguru import logger

from src.engine.models import (
    AuditFinding,
    FreightInvoice,
    LLMExplanation,
    RateContract,
)


load_dotenv()

GEMINI_MODEL_NAME = "gemini-3-flash-preview"

SYSTEM_PROMPT = """
You are a senior freight billing auditor with 20 years of experience 
in transportation logistics and contract compliance.

You have been given structured audit findings produced by a deterministic 
policy engine. Your job is to explain each finding clearly to a 
non-technical finance manager who needs to decide whether to dispute 
the invoice with the carrier.

Rules:
- Be factual and specific. Always cite exact dollar amounts and rates.
- Never invent numbers — use only what is given to you.
- Tone: professional and direct. Not accusatory — state facts only.
- The dispute message must be addressed to the carrier, reference the 
  invoice number, cite the contract violation, and request a credit.
- Respond ONLY with valid JSON. No markdown. No backticks. No preamble.
""".strip()


def _build_user_prompt(
    invoice: FreightInvoice,
    contract: RateContract,
    findings: List[AuditFinding],
) -> str:
    allowed_accessorials = str(contract.allowed_accessorials or "")
    findings_lines = []
    for f in findings:
        findings_lines.append(
            f"- Rule: {f.rule_id}; Field: {f.field_audited}; "
            f"Charged: {f.charged_value}; Contract: {f.contract_value}; "
            f"Dollar impact: {f.dollar_impact}; Description: {f.description}"
        )
    findings_block = "\n".join(findings_lines) or "None"

    requested_output = {
        "invoice_id": invoice.invoice_id,
        "summary": "1-2 sentence plain English executive summary",
        "findings_explained": [
            "one explanation per finding, specific and dollar-quantified"
        ],
        "total_recovery_opportunity": 0.0,
        "dispute_recommended": False,
        "dispute_message": "full ready-to-send message to carrier",
        "confidence": "HIGH | MEDIUM | LOW",
    }

    prompt = f"""
INVOICE DETAILS:
- Invoice ID: {invoice.invoice_id}
- Carrier: {invoice.carrier_name}
- Lane: {invoice.lane_id} ({invoice.origin_zip} → {invoice.destination_zip})
- Invoice Date: {invoice.invoice_date}
- Total Charged: {invoice.total_charged}

CONTRACT TERMS:
- Base rate ($/lb): {contract.agreed_base_rate_per_lb}
- Fuel surcharge (% as decimal): {contract.fuel_surcharge_pct}
- Allowed accessorials (pipe-delimited): {allowed_accessorials}

AUDIT FINDINGS:
{findings_block}

REQUESTED OUTPUT FORMAT (JSON schema example):
{json.dumps(requested_output, indent=2)}
""".strip()
    return prompt


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in environment/.env")
    return genai.Client(api_key=api_key)


def explain_findings(
    invoice: FreightInvoice,
    contract: RateContract,
    findings: List[AuditFinding],
) -> LLMExplanation:
    """
    Call Gemini to explain deterministic audit findings for a single invoice.
    Falls back to a safe deterministic explanation on any failure.
    """
    if not findings:
        # No findings to explain; callers should generally skip clean invoices.
        return LLMExplanation(
            invoice_id=invoice.invoice_id,
            summary="Invoice passed all deterministic checks. No discrepancies to explain.",
            findings_explained=[],
            total_recovery_opportunity=0.0,
            dispute_recommended=False,
            dispute_message="",
            confidence="HIGH",
        )

    try:
        client = _get_client()
    except Exception as e:  # noqa: BLE001
        logger.error("Gemini client init failed for invoice {}: {}", invoice.invoice_id, e)
        return _fallback_explanation(invoice, findings)

    user_prompt = _build_user_prompt(invoice, contract, findings)

    try:
        logger.info(
            "Calling Gemini for invoice_id={} with {} findings",
            invoice.invoice_id,
            len(findings),
        )
        model = client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=[
                {"role": "system", "parts": [{"text": SYSTEM_PROMPT}]},
                {"role": "user", "parts": [{"text": user_prompt}]},
            ],
            generation_config=GenerationConfig(
                temperature=0.2,
                max_output_tokens=800,
            ),
        )

        # google-genai returns a response with candidates; take first text block.
        text = model.candidates[0].content.parts[0].text  # type: ignore[assignment]
        data = json.loads(text)
        explanation = LLMExplanation.model_validate(data)

        total_tokens = getattr(model.usage_metadata, "total_token_count", None)
        logger.info(
            "Gemini explanation succeeded for invoice_id={} (findings={}, tokens={})",
            invoice.invoice_id,
            len(findings),
            total_tokens,
        )
        return explanation
    except Exception as e:  # noqa: BLE001
        logger.error(
            "Gemini explanation failed for invoice_id={} with error: {}",
            invoice.invoice_id,
            e,
        )
        return _fallback_explanation(invoice, findings)


def _fallback_explanation(
    invoice: FreightInvoice,
    findings: List[AuditFinding],
) -> LLMExplanation:
    return LLMExplanation(
        invoice_id=invoice.invoice_id,
        summary="AI explanation unavailable. Raw findings shown below.",
        findings_explained=[f.description for f in findings],
        total_recovery_opportunity=sum(f.dollar_impact for f in findings),
        dispute_recommended=any(f.severity == "HIGH" for f in findings),
        dispute_message="[AI unavailable — draft dispute manually using findings above]",
        confidence="LOW",
    )


def explain_batch(
    invoices_with_findings: List[Tuple[FreightInvoice, RateContract, List[AuditFinding]]],
) -> Dict[str, LLMExplanation]:
    """
    Explain only invoices that have findings. Clean invoices are skipped.
    """
    flagged = [t for t in invoices_with_findings if t[2]]
    skipped = len(invoices_with_findings) - len(flagged)
    logger.info(
        "Explaining {} flagged invoices, skipping {} clean ones",
        len(flagged),
        skipped,
    )
    results: Dict[str, LLMExplanation] = {}
    for invoice, contract, findings in flagged:
        results[invoice.invoice_id] = explain_findings(invoice, contract, findings)
    return results

