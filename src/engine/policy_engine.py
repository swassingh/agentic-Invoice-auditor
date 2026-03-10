"""
Deterministic Policy Engine — invoice vs contract → AuditFinding list.
No LLM, no randomness, no I/O inside rule functions.

Engineering SPEC §4: BASE_RATE_OVERAGE, FUEL_SURCHARGE_OVERAGE,
UNAUTHORIZED_ACCESSORIAL, DUPLICATE_INVOICE, WEIGHT_INFLATION, TOTAL_MISMATCH.
Extended: MISSING_CONTRACT when (lane_id, carrier) not in rate table.
"""

from __future__ import annotations

import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import pandas as pd

from src.engine.models import AuditFinding, FreightInvoice, RateContract

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path and "__file__" in dir():
    pass  # imported as package

# SPEC: tolerance on rate comparisons (0 = strict)
TOLERANCE = 0.0
TOTAL_MISMATCH_THRESHOLD = 1.0


def _variance_pct(charged: float, contract: float) -> float:
    if contract == 0:
        return 0.0 if charged == 0 else 1.0
    return round((charged - contract) / contract, 6)


def _allowed_set(allowed_pipe: str) -> set[str]:
    return {x.strip() for x in str(allowed_pipe).split("|") if x.strip()}


def calc_line_total(inv: FreightInvoice) -> float:
    """SPEC Rule 6: freight * (1 + fuel) + accessorials."""
    freight = inv.shipment_weight_lbs * inv.base_rate_charged
    return round(
        freight * (1.0 + inv.fuel_surcharge_pct_charged)
        + inv.accessorial_liftgate
        + inv.accessorial_residential
        + inv.accessorial_inside_delivery,
        2,
    )


def check_missing_contract(
    inv: FreightInvoice,
    contract: RateContract | None,
) -> List[AuditFinding]:
    if contract is not None:
        return []
    return [
        AuditFinding(
            invoice_id=inv.invoice_id,
            rule_id="MISSING_CONTRACT",
            severity="HIGH",
            field_audited="lane_id+carrier_name",
            charged_value=1.0,
            contract_value=0.0,
            variance_pct=1.0,
            dollar_impact=inv.total_charged,
            description=f"No contract for lane_id={inv.lane_id} carrier={inv.carrier_name}.",
        )
    ]


def check_base_rate(
    inv: FreightInvoice,
    contract: RateContract | None,
) -> List[AuditFinding]:
    if contract is None:
        return []
    cap = contract.agreed_base_rate_per_lb * (1.0 + TOLERANCE)
    if inv.base_rate_charged <= cap:
        return []
    diff_per_lb = inv.base_rate_charged - contract.agreed_base_rate_per_lb
    dollar = round(diff_per_lb * inv.shipment_weight_lbs, 2)
    return [
        AuditFinding(
            invoice_id=inv.invoice_id,
            rule_id="BASE_RATE_OVERAGE",
            severity="HIGH",
            field_audited="base_rate_charged",
            charged_value=inv.base_rate_charged,
            contract_value=contract.agreed_base_rate_per_lb,
            variance_pct=_variance_pct(inv.base_rate_charged, contract.agreed_base_rate_per_lb),
            dollar_impact=dollar,
            description=(
                f"Base rate ${inv.base_rate_charged}/lb exceeds contract "
                f"${contract.agreed_base_rate_per_lb}/lb on {inv.shipment_weight_lbs} lbs."
            ),
        )
    ]


def check_fuel_surcharge(
    inv: FreightInvoice,
    contract: RateContract | None,
) -> List[AuditFinding]:
    if contract is None:
        return []
    cap = contract.fuel_surcharge_pct * (1.0 + TOLERANCE)
    if inv.fuel_surcharge_pct_charged <= cap:
        return []
    base_freight = inv.shipment_weight_lbs * inv.base_rate_charged
    pct_diff = inv.fuel_surcharge_pct_charged - contract.fuel_surcharge_pct
    dollar = round(pct_diff * base_freight, 2)
    return [
        AuditFinding(
            invoice_id=inv.invoice_id,
            rule_id="FUEL_SURCHARGE_OVERAGE",
            severity="HIGH",
            field_audited="fuel_surcharge_pct_charged",
            charged_value=inv.fuel_surcharge_pct_charged,
            contract_value=contract.fuel_surcharge_pct,
            variance_pct=_variance_pct(
                inv.fuel_surcharge_pct_charged, contract.fuel_surcharge_pct
            ),
            dollar_impact=dollar,
            description=(
                f"Fuel surcharge {inv.fuel_surcharge_pct_charged:.4f} exceeds contract "
                f"{contract.fuel_surcharge_pct:.4f}."
            ),
        )
    ]


def check_unauthorized_accessorials(
    inv: FreightInvoice,
    contract: RateContract | None,
) -> List[AuditFinding]:
    if contract is None:
        return []
    allowed = _allowed_set(contract.allowed_accessorials)
    findings: List[AuditFinding] = []
    checks = [
        ("accessorial_liftgate", "liftgate", inv.accessorial_liftgate),
        ("accessorial_residential", "residential", inv.accessorial_residential),
        (
            "accessorial_inside_delivery",
            "inside_delivery",
            inv.accessorial_inside_delivery,
        ),
    ]
    for field, name, amount in checks:
        if amount <= 0:
            continue
        if name in allowed:
            continue
        findings.append(
            AuditFinding(
                invoice_id=inv.invoice_id,
                rule_id="UNAUTHORIZED_ACCESSORIAL",
                severity="MEDIUM",
                field_audited=field,
                charged_value=amount,
                contract_value=0.0,
                variance_pct=1.0,
                dollar_impact=amount,
                description=(
                    f"${amount} charged for {name}; not in contract allowed_accessorials."
                ),
            )
        )
    return findings


def check_total_mismatch(
    inv: FreightInvoice,
    contract: RateContract | None,
) -> List[AuditFinding]:
    calculated = calc_line_total(inv)
    delta = abs(inv.total_charged - calculated)
    if delta <= TOTAL_MISMATCH_THRESHOLD:
        return []
    return [
        AuditFinding(
            invoice_id=inv.invoice_id,
            rule_id="TOTAL_MISMATCH",
            severity="LOW",
            field_audited="total_charged",
            charged_value=inv.total_charged,
            contract_value=calculated,
            variance_pct=_variance_pct(inv.total_charged, calculated),
            dollar_impact=round(delta, 2),
            description=(
                f"total_charged ${inv.total_charged} != calculated ${calculated} (diff ${delta:.2f})."
            ),
        )
    ]


def check_weight_inflation(
    inv: FreightInvoice,
    contract: RateContract | None,
) -> List[AuditFinding]:
    """
    SPEC Rule 5: suspiciously round weight + >2% variance vs 97% estimate.
    Supplemental: generator WEIGHT_INFLATION uses ceil(true/100)*100*1.04 — so
    implied_true ≈ weight/1.04; if that is within 1 lb of a multiple of 100,
    flag as inflated billing weight (deterministic).
    """
    w = inv.shipment_weight_lbs
    implied_true = w / 1.04
    near_hundred = abs(implied_true - round(implied_true / 100) * 100) <= 1.0
    if near_hundred and w > 500 and implied_true >= 500:
        # Dollar impact: overcharge vs using implied_true as weight at same rates
        dollar = round((w - implied_true) * inv.base_rate_charged * (1 + inv.fuel_surcharge_pct_charged), 2)
        if dollar > 1.0:
            return [
                AuditFinding(
                    invoice_id=inv.invoice_id,
                    rule_id="WEIGHT_INFLATION",
                    severity="MEDIUM",
                    field_audited="shipment_weight_lbs",
                    charged_value=w,
                    contract_value=round(implied_true, 2),
                    variance_pct=_variance_pct(w, implied_true),
                    dollar_impact=dollar,
                    description=(
                        f"Billed weight {w} lbs consistent with ~4% inflation over "
                        f"~{round(implied_true/100)*100} lbs base."
                    ),
                )
            ]
    if w % 100 != 0:
        return []
    estimated = w * 0.97
    if abs(w - estimated) <= 0.02 * w:
        return []
    weight_diff = w - estimated
    dollar = round(weight_diff * inv.base_rate_charged, 2)
    return [
        AuditFinding(
            invoice_id=inv.invoice_id,
            rule_id="WEIGHT_INFLATION",
            severity="MEDIUM",
            field_audited="shipment_weight_lbs",
            charged_value=w,
            contract_value=round(estimated, 2),
            variance_pct=_variance_pct(w, estimated),
            dollar_impact=dollar,
            description=(
                f"Weight {w} lbs is round; estimated actual {estimated:.0f} lbs "
                f"implies overcharge ~${dollar}."
            ),
        )
    ]


AUDIT_RULES: List[Callable[[FreightInvoice, RateContract | None], List[AuditFinding]]] = [
    check_missing_contract,
    check_base_rate,
    check_fuel_surcharge,
    check_unauthorized_accessorials,
    check_total_mismatch,
    check_weight_inflation,
]


def check_duplicate_invoice_ids(
    invoices: List[FreightInvoice],
) -> Dict[str, List[AuditFinding]]:
    """
    SPEC Rule 4: same invoice_id more than once — flag occurrences after first.
    """
    by_id: Dict[str, List[FreightInvoice]] = defaultdict(list)
    for inv in invoices:
        by_id[inv.invoice_id].append(inv)
    findings_map: Dict[str, List[AuditFinding]] = defaultdict(list)
    for iid, group in by_id.items():
        if len(group) <= 1:
            continue
        for inv in group[1:]:
            findings_map[inv.invoice_id].append(
                AuditFinding(
                    invoice_id=inv.invoice_id,
                    rule_id="DUPLICATE_INVOICE",
                    severity="HIGH",
                    field_audited="invoice_id",
                    charged_value=float(len(group)),
                    contract_value=1.0,
                    variance_pct=float(len(group) - 1),
                    dollar_impact=inv.total_charged,
                    description=f"Duplicate invoice_id {iid} ({len(group)} occurrences).",
                )
            )
    return findings_map


def _fingerprint(inv: FreightInvoice) -> Tuple:
    """Billing fingerprint for content-duplicate detection (ids may differ)."""
    return (
        inv.lane_id,
        inv.carrier_name,
        round(inv.shipment_weight_lbs, 2),
        round(inv.base_rate_charged, 4),
        round(inv.fuel_surcharge_pct_charged, 4),
        round(inv.accessorial_liftgate, 2),
        round(inv.accessorial_residential, 2),
        round(inv.accessorial_inside_delivery, 2),
        round(inv.total_charged, 2),
    )


def check_duplicate_content(
    invoices: List[FreightInvoice],
) -> Dict[str, List[AuditFinding]]:
    """
    When invoice_ids are unique but billing payload repeats (generator DUPLICATE rows).
    Group by fingerprint; if group size >= 2, flag every member so validation
    (_error_label DUPLICATE) always has a finding regardless of CSV order.
    """
    groups: Dict[Tuple, List[FreightInvoice]] = defaultdict(list)
    for inv in invoices:
        groups[_fingerprint(inv)].append(inv)
    findings_map: Dict[str, List[AuditFinding]] = defaultdict(list)
    for fp, group in groups.items():
        if len(group) < 2:
            continue
        ids = [i.invoice_id for i in group]
        for inv in group:
            others = [x for x in ids if x != inv.invoice_id]
            findings_map[inv.invoice_id].append(
                AuditFinding(
                    invoice_id=inv.invoice_id,
                    rule_id="DUPLICATE_INVOICE",
                    severity="HIGH",
                    field_audited="billing_fingerprint",
                    charged_value=float(len(group)),
                    contract_value=1.0,
                    variance_pct=float(len(group) - 1),
                    dollar_impact=inv.total_charged,
                    description=(
                        f"Duplicate billing content ({len(group)} occurrences); "
                        f"peer invoice_ids: {others[:3]}."
                    ),
                )
            )
    return findings_map


def load_rate_table_csv(path: Path | str) -> Dict[Tuple[str, str], RateContract]:
    df = pd.read_csv(path)
    out: Dict[Tuple[str, str], RateContract] = {}
    for _, row in df.iterrows():
        c = RateContract(
            lane_id=str(row["lane_id"]),
            carrier_name=str(row["carrier_name"]),
            origin_zip=str(row["origin_zip"]).zfill(5)[:5],
            destination_zip=str(row["destination_zip"]).zfill(5)[:5],
            agreed_base_rate_per_lb=float(row["agreed_base_rate_per_lb"]),
            fuel_surcharge_pct=float(row["fuel_surcharge_pct"]),
            allowed_accessorials=str(row["allowed_accessorials"]),
            effective_date=pd.to_datetime(row["effective_date"]).date(),
            expiration_date=pd.to_datetime(row["expiration_date"]).date(),
        )
        out[(c.lane_id, c.carrier_name)] = c
    return out


def load_invoices_csv(path: Path | str) -> Tuple[List[FreightInvoice], Dict[str, str]]:
    """Returns invoices and invoice_id -> _error_label (validation only)."""
    df = pd.read_csv(path)
    labels: Dict[str, str] = {}
    invoices: List[FreightInvoice] = []
    for _, row in df.iterrows():
        label = str(row.get("_error_label", "UNKNOWN"))
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
            accessorial_residential=float(row.get("accessorial_residential", 0) or 0),
            accessorial_inside_delivery=float(
                row.get("accessorial_inside_delivery", 0) or 0
            ),
            total_charged=float(row["total_charged"]),
        )
        invoices.append(inv)
        labels[inv.invoice_id] = label
    return invoices, labels


def audit_invoices(
    invoices: List[FreightInvoice],
    rate_table: Dict[Tuple[str, str], RateContract],
) -> Dict[str, List[AuditFinding]]:
    """
    Returns dict mapping invoice_id → list of findings.
    Invoices with no findings appear with empty list only if we include all ids —
    here we only attach keys when findings exist, except caller can merge.
    """
    results: Dict[str, List[AuditFinding]] = defaultdict(list)

    for inv in invoices:
        key = (inv.lane_id, inv.carrier_name)
        contract = rate_table.get(key)
        for rule in AUDIT_RULES:
            try:
                findings = rule(inv, contract)
                if findings:
                    results[inv.invoice_id].extend(findings)
            except Exception as e:
                logger.exception("Rule failed invoice_id=%s", inv.invoice_id)
                raise RuntimeError(f"Rule failed for {inv.invoice_id}") from e

    dup_id_map = check_duplicate_invoice_ids(invoices)
    dup_fp_map = check_duplicate_content(invoices)
    for m in (dup_id_map, dup_fp_map):
        for iid, finds in m.items():
            results[iid].extend(finds)

    return dict(results)


def findings_by_invoice_all(
    invoices: List[FreightInvoice],
    findings_map: Dict[str, List[AuditFinding]],
) -> Dict[str, List[AuditFinding]]:
    """Ensure every invoice_id has a list (empty if clean)."""
    out: Dict[str, List[AuditFinding]] = {}
    for inv in invoices:
        out[inv.invoice_id] = findings_map.get(inv.invoice_id, [])
    return out


# --- Injected label → rule_id(s) that must fire for validation ---
LABEL_TO_RULES = {
    "FUEL_OVERAGE": ["FUEL_SURCHARGE_OVERAGE"],
    "BASE_RATE_OVERAGE": ["BASE_RATE_OVERAGE"],
    "UNAUTHORIZED_ACCESSORIAL": ["UNAUTHORIZED_ACCESSORIAL"],
    "DUPLICATE": ["DUPLICATE_INVOICE"],
    "WEIGHT_INFLATION": ["WEIGHT_INFLATION"],
    "TOTAL_MISMATCH": ["TOTAL_MISMATCH"],
    "CLEAN": [],
    "MISSING_CONTRACT": ["MISSING_CONTRACT"],
}

EXPECTED_INJECTED_COUNTS = {
    "FUEL_OVERAGE": 5,
    "BASE_RATE_OVERAGE": 4,
    "UNAUTHORIZED_ACCESSORIAL": 4,
    "DUPLICATE": 2,
    "WEIGHT_INFLATION": 3,
    "TOTAL_MISMATCH": 2,
    "CLEAN": 30,
}


def _invoice_has_any_rule(inv_id: str, rule_ids: List[str], findings_map: Dict[str, List[AuditFinding]]) -> bool:
    if not rule_ids:
        return True
    finds = findings_map.get(inv_id, [])
    fired = {f.rule_id for f in finds}
    return any(r in fired for r in rule_ids)


def run_validation_report(
    invoices: List[FreightInvoice],
    labels: Dict[str, str],
    findings_map: Dict[str, List[AuditFinding]],
) -> None:
    """Print Injected | Caught | Miss table grouped by _error_label."""
    by_label: Dict[str, List[str]] = defaultdict(list)
    for inv in invoices:
        by_label[labels.get(inv.invoice_id, "UNKNOWN")].append(inv.invoice_id)

    print("_error_label       | Injected | Caught | Miss")
    print("-" * 55)
    for label in [
        "FUEL_OVERAGE",
        "BASE_RATE_OVERAGE",
        "UNAUTHORIZED_ACCESSORIAL",
        "DUPLICATE",
        "WEIGHT_INFLATION",
        "TOTAL_MISMATCH",
        "CLEAN",
    ]:
        injected = EXPECTED_INJECTED_COUNTS.get(label, len(by_label.get(label, [])))
        ids = by_label.get(label, [])
        if label == "CLEAN":
            caught = sum(
                1
                for iid in ids
                if not findings_map.get(iid)
            )
            miss = injected - caught
            ok = miss == 0
        else:
            rules = LABEL_TO_RULES[label]
            caught = sum(
                1
                for iid in ids
                if _invoice_has_any_rule(iid, rules, findings_map)
            )
            miss = injected - caught
            ok = miss == 0
        icon = "✅" if ok else "❌"
        print(f"{label:<18} | {injected:^8} | {caught:^6} | {miss:^4} {icon}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    root = Path(__file__).resolve().parents[2]
    rate_candidates = [
        root / "data" / "master_rate_table.csv",
        root / "data" / "reference" / "master_rate_table.csv",
        root / "data" / "reference" / "gen_invoice_master_rate_table.csv",
        root / "data" / "reference" / "gen_data_master_rate_table.csv",
    ]
    rate_path = next((p for p in rate_candidates if p.exists()), None)
    if rate_path is None:
        for p in root.glob("**/master_rate_table.csv"):
            rate_path = p
            break
    if rate_path is None or not rate_path.exists():
        print("❌ FAIL: master rate CSV not found (tried data/master_rate_table.csv and reference/*)")
        sys.exit(1)
    inv_path = root / "data" / "invoices_sample.csv"
    if not inv_path.exists():
        inv_path = root / "data" / "raw" / "invoices_sample.csv"
    if not inv_path.exists():
        print("❌ FAIL: data/invoices_sample.csv not found")
        sys.exit(1)

    rate_table = load_rate_table_csv(rate_path)
    invoices, labels = load_invoices_csv(inv_path)
    findings_map = audit_invoices(invoices, rate_table)
    full = findings_by_invoice_all(invoices, findings_map)

    print(f"Loaded rate table: {len(rate_table)} contracts")
    print(f"Loaded invoices: {len(invoices)}")
    print(f"Invoices with ≥1 finding: {sum(1 for v in full.values() if v)}")
    print()
    run_validation_report(invoices, labels, findings_map)
