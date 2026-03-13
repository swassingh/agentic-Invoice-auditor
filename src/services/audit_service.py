"""
Orchestration layer between the deterministic policy engine and the LLM explainer.

Responsibilities:
- Convert uploaded invoice DataFrames into FreightInvoice models.
- Load the master rate table.
- Run the policy engine.
- Optionally call the agent layer to explain findings.
- Return AuditResult objects plus summary statistics and tabular views.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
from loguru import logger

from src.agent.explainer import explain_batch
from src.engine.models import AuditResult, AuditFinding, FreightInvoice, RateContract
from src.engine.policy_engine import audit_invoices, load_rate_table_csv


def parse_invoices_from_df(df: pd.DataFrame) -> List[FreightInvoice]:
    """
    Convert raw uploaded DataFrame rows into validated FreightInvoice models.

    - Expects the same columns as data/invoices_sample.csv.
    - Logs and skips rows that cannot be parsed.
    """
    required_cols = [
        "invoice_id",
        "carrier_name",
        "invoice_date",
        "lane_id",
        "origin_zip",
        "destination_zip",
        "shipment_weight_lbs",
        "freight_class",
        "base_rate_charged",
        "fuel_surcharge_pct_charged",
        "accessorial_liftgate",
        "accessorial_residential",
        "accessorial_inside_delivery",
        "total_charged",
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(
            f"Uploaded CSV is missing required columns: {', '.join(missing)}"
        )

    invoices: List[FreightInvoice] = []
    for idx, row in df.iterrows():
        try:
            invoice = FreightInvoice(
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
                accessorial_liftgate=float(row.get("accessorial_liftgate", 0) or 0.0),
                accessorial_residential=float(
                    row.get("accessorial_residential", 0) or 0.0
                ),
                accessorial_inside_delivery=float(
                    row.get("accessorial_inside_delivery", 0) or 0.0
                ),
                total_charged=float(row["total_charged"]),
            )
            invoices.append(invoice)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Skipping row {} due to parse error: {}", idx, e, exc_info=True
            )
    return invoices


def _build_rate_index(
    rate_table: Iterable[RateContract],
) -> Dict[Tuple[str, str], RateContract]:
    return {(r.lane_id, r.carrier_name): r for r in rate_table}


def _default_rate_table_path(root: Path) -> Path:
    """
    Choose a canonical rate table from the data/reference folder.

    Priority:
      1) data/reference/gen_invoice_master_rate_table.csv
      2) data/reference/gen_data_master_rate_table.csv
      3) data/reference/master_rate_table.csv
      4) first file matching data/reference/*master_rate_table*.csv
    """
    ref_dir = root / "data" / "reference"
    candidates = [
        ref_dir / "gen_invoice_master_rate_table.csv",
        ref_dir / "gen_data_master_rate_table.csv",
        ref_dir / "master_rate_table.csv",
    ]
    for p in candidates:
        if p.exists():
            return p

    if ref_dir.exists():
        extra = sorted(ref_dir.glob("*master_rate_table*.csv"))
        if extra:
            return extra[0]

    raise FileNotFoundError(
        "No rate table found under data/reference. "
        "Expected at least one file matching data/reference/*master_rate_table*.csv"
    )


def run_full_audit(
    invoices_df: pd.DataFrame,
    rate_table_path: Path | None = None,
    explain: bool = True,
) -> tuple[List[AuditResult], Dict]:
    """
    End-to-end audit:
    - DataFrame → FreightInvoice models
    - Load rate table once
    - Run deterministic policy engine
    - Optionally call LLM explainer
    - Aggregate into AuditResult list and summary stats
    """
    invoices = parse_invoices_from_df(invoices_df)
    if not invoices:
        raise ValueError("No valid invoices found in uploaded CSV.")

    root = Path(__file__).resolve().parents[2]
    # Resolve rate table path relative to project root, defaulting to any
    # *master_rate_table* under data/reference when not explicitly provided.
    if rate_table_path is None:
        rate_table_path = _default_rate_table_path(root)
    elif not rate_table_path.is_absolute():
        rate_table_path = root / rate_table_path

    rate_index = load_rate_table_csv(rate_table_path)
    findings_by_invoice: Dict[str, List[AuditFinding]] = audit_invoices(
        invoices, rate_index
    )

    explanations: Dict[str, "LLMExplanation"] = {}
    if explain:
        tuples: List[tuple[FreightInvoice, RateContract, List[AuditFinding]]] = []
        for inv in invoices:
            findings = findings_by_invoice.get(inv.invoice_id, [])
            contract = rate_index.get((inv.lane_id, inv.carrier_name))
            if contract is None:
                continue
            tuples.append((inv, contract, findings))
        explanations = explain_batch(tuples)

    results: List[AuditResult] = []
    for inv in invoices:
        inv_findings = findings_by_invoice.get(inv.invoice_id, [])
        explanation = explanations.get(inv.invoice_id)
        results.append(
            AuditResult(invoice=inv, findings=inv_findings, explanation=explanation)
        )

    # Sort by dollar impact descending
    results.sort(key=lambda r: r.total_dollar_impact, reverse=True)

    summary = get_summary_stats(results)
    return results, summary


def run_full_audit_from_invoices(
    invoices: List[FreightInvoice],
    rate_index: Dict[Tuple[str, str], RateContract],
    explain: bool = True,
) -> tuple[List[AuditResult], Dict]:
    """
    End-to-end audit starting from in-memory FreightInvoice models.

    This is used by the PDF ingestion pipeline, where invoices are
    produced by the normalization layer instead of CSV parsing.
    """
    if not invoices:
        raise ValueError("No invoices provided for audit.")

    findings_by_invoice: Dict[str, List[AuditFinding]] = audit_invoices(
        invoices, rate_index
    )

    explanations: Dict[str, "LLMExplanation"] = {}
    if explain:
        tuples: List[tuple[FreightInvoice, RateContract, List[AuditFinding]]] = []
        for inv in invoices:
            findings = findings_by_invoice.get(inv.invoice_id, [])
            contract = rate_index.get((inv.lane_id, inv.carrier_name))
            if contract is None:
                continue
            tuples.append((inv, contract, findings))
        explanations = explain_batch(tuples)

    results: List[AuditResult] = []
    for inv in invoices:
        inv_findings = findings_by_invoice.get(inv.invoice_id, [])
        explanation = explanations.get(inv.invoice_id)
        results.append(
            AuditResult(invoice=inv, findings=inv_findings, explanation=explanation)
        )

    results.sort(key=lambda r: r.total_dollar_impact, reverse=True)
    summary = get_summary_stats(results)
    return results, summary


def get_summary_stats(results: List[AuditResult]) -> Dict:
    total_invoices = len(results)
    invoices_with_errors = sum(1 for r in results if r.has_errors)
    clean_invoices = total_invoices - invoices_with_errors

    all_findings: List[AuditFinding] = [f for r in results for f in r.findings]
    total_findings = len(all_findings)
    total_recovery = sum(f.dollar_impact for f in all_findings)
    high_severity_count = sum(1 for f in all_findings if f.severity == "HIGH")

    findings_by_rule: Dict[str, int] = Counter(f.rule_id for f in all_findings)

    carrier_totals: Dict[str, float] = defaultdict(float)
    for r in results:
        for f in r.findings:
            carrier_totals[r.invoice.carrier_name] += f.dollar_impact
    top_offending_carriers = sorted(
        carrier_totals.items(), key=lambda kv: kv[1], reverse=True
    )[:3]

    return {
        "total_invoices": total_invoices,
        "invoices_with_errors": invoices_with_errors,
        "clean_invoices": clean_invoices,
        "total_findings": total_findings,
        "total_recovery_opportunity": total_recovery,
        "high_severity_count": high_severity_count,
        "findings_by_rule": dict(findings_by_rule),
        "top_offending_carriers": top_offending_carriers,
    }


def results_to_display_df(results: List[AuditResult]) -> pd.DataFrame:
    """
    Build a flat DataFrame with one row per invoice for UI display.
    """
    records = []
    for r in results:
        invoice = r.invoice
        max_severity = r.max_severity or "CLEAN"
        findings_count = len(r.findings)
        dispute_recommended = (
            r.explanation.dispute_recommended
            if r.explanation is not None
            else any(f.severity == "HIGH" for f in r.findings)
        )

        if max_severity == "HIGH":
            status = "🚨 HIGH"
        elif max_severity == "MEDIUM":
            status = "⚠️ MEDIUM"
        elif max_severity == "LOW":
            status = "🔵 LOW"
        else:
            status = "✅ CLEAN"

        records.append(
            {
                "invoice_id": invoice.invoice_id,
                "carrier_name": invoice.carrier_name,
                "invoice_date": invoice.invoice_date,
                "total_charged": invoice.total_charged,
                "findings_count": findings_count,
                "max_severity": max_severity,
                "total_dollar_impact": r.total_dollar_impact,
                "dispute_recommended": dispute_recommended,
                "status": status,
            }
        )

    return pd.DataFrame.from_records(records)

