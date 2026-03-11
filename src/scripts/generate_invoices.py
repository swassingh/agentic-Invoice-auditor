"""
Generate the invoice dataset (carrier billing simulation) from the master rate table.

Loads contract ground truth first, then builds 50 invoices with intentional errors
and a cheat-sheet _error_label column for engine validation.

Run from repo root with PYTHONPATH set:
  python src/scripts/generate_invoices.py
"""

from __future__ import annotations

import math
import random
import sys
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SEED = 42
NUM_INVOICES = 50
INVOICE_DATE_START = date(2024, 1, 15)
INVOICE_DATE_END = date(2024, 11, 30)
WEIGHT_MIN, WEIGHT_MAX = 500.0, 9500.0
FREIGHT_CLASSES = ["70", "85", "100", "125"]

# Exact error counts (sum = 50)
COUNTS = {
    "FUEL_OVERAGE": 5,
    "BASE_RATE_OVERAGE": 4,
    "UNAUTHORIZED_ACCESSORIAL": 4,
    "DUPLICATE": 2,
    "WEIGHT_INFLATION": 3,
    "TOTAL_MISMATCH": 2,
    "CLEAN": 30,
}

COLUMNS = [
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
    "_error_label",
]


def _repo_root() -> Path:
    return _ROOT


def load_rate_table() -> pd.DataFrame:
    """
    Load the rate table used for invoice generation.

    Priority:
      1) data/reference/gen_invoice_master_rate_table.csv
      2) data/reference/gen_data_master_rate_table.csv
      3) data/master_rate_table.csv
      4) data/reference/master_rate_table.csv
    """
    root = _repo_root()
    master = root / "data" / "master_rate_table.csv"
    reference_master = root / "data" / "reference" / "master_rate_table.csv"
    gen_invoice = root / "data" / "reference" / "gen_invoice_master_rate_table.csv"
    gen_data = root / "data" / "reference" / "gen_data_master_rate_table.csv"

    if gen_invoice.exists():
        path = gen_invoice
    elif gen_data.exists():
        path = gen_data
    elif master.exists():
        path = master
    elif reference_master.exists():
        path = reference_master
    else:
        raise FileNotFoundError(
            "No rate table found. Expected one of:\n"
            "  - data/master_rate_table.csv\n"
            "  - data/reference/master_rate_table.csv\n"
            "  - data/reference/gen_invoice_master_rate_table.csv\n"
            "  - data/reference/gen_data_master_rate_table.csv"
        )
    return pd.read_csv(path)


def calc_total(
    weight_lb: float,
    base_rate: float,
    fuel_pct: float,
    acc_lift: float,
    acc_res: float,
    acc_inside: float,
) -> float:
    freight = weight_lb * base_rate
    return round(freight * (1.0 + fuel_pct) + acc_lift + acc_res + acc_inside, 2)


def allowed_set(allowed_pipe: str) -> set[str]:
    return {x.strip() for x in str(allowed_pipe).split("|") if x.strip()}


ALL_ACCESSORIALS = ["liftgate", "residential", "inside_delivery"]


def pick_unauthorized_accessorial(allowed: str) -> str:
    s = allowed_set(allowed)
    for name in ALL_ACCESSORIALS:
        if name not in s:
            return name
    return "residential"


def accessorial_amount(rng: random.Random) -> float:
    return round(rng.uniform(125, 175), 2)


def inflate_weight(weight: float, rng: random.Random) -> float:
    """Round up to nearest 100, add 4% (billed weight for inflated total)."""
    rounded_100 = math.ceil(weight / 100.0) * 100.0
    return round(rounded_100 * 1.04, 2)


def _row_dict(
    invoice_id: str,
    contract: pd.Series,
    invoice_date: date,
    weight: float,
    fclass: str,
    base: float,
    fuel: float,
    acc_l: float,
    acc_r: float,
    acc_i: float,
    total: float,
    label: str,
) -> dict[str, Any]:
    return {
        "invoice_id": invoice_id,
        "carrier_name": contract["carrier_name"],
        "invoice_date": invoice_date.isoformat(),
        "lane_id": contract["lane_id"],
        "origin_zip": str(contract["origin_zip"]).zfill(5)[:5],
        "destination_zip": str(contract["destination_zip"]).zfill(5)[:5],
        "shipment_weight_lbs": weight,
        "freight_class": fclass,
        "base_rate_charged": base,
        "fuel_surcharge_pct_charged": fuel,
        "accessorial_liftgate": acc_l,
        "accessorial_residential": acc_r,
        "accessorial_inside_delivery": acc_i,
        "total_charged": total,
        "_error_label": label,
    }


def build_row(
    idx: int,
    contract: pd.Series,
    rng: random.Random,
    error_label: str,
) -> dict[str, Any]:
    invoice_id = f"INV-2024-{idx:04d}"
    invoice_date = INVOICE_DATE_START + timedelta(
        days=rng.randint(0, (INVOICE_DATE_END - INVOICE_DATE_START).days)
    )
    weight = round(rng.uniform(WEIGHT_MIN, WEIGHT_MAX), 2)
    fclass = rng.choice(FREIGHT_CLASSES)
    base = float(contract["agreed_base_rate_per_lb"])
    fuel = float(contract["fuel_surcharge_pct"])
    allowed = str(contract["allowed_accessorials"])

    if error_label == "CLEAN":
        acc_l = acc_r = acc_i = 0.0
        if rng.random() < 0.15 and "liftgate" in allowed_set(allowed):
            acc_l = rng.choice([0.0, 75.0, 125.0])
        elif rng.random() < 0.1 and "residential" in allowed_set(allowed):
            acc_r = rng.choice([0.0, 50.0, 95.0])
        total = calc_total(weight, base, fuel, acc_l, acc_r, acc_i)
        return _row_dict(
            invoice_id, contract, invoice_date, weight, fclass,
            base, fuel, acc_l, acc_r, acc_i, total, "CLEAN",
        )

    if error_label == "FUEL_OVERAGE":
        fuel_charged = round(rng.uniform(0.185, 0.22), 3)
        total = calc_total(weight, base, fuel_charged, 0, 0, 0)
        return _row_dict(
            invoice_id, contract, invoice_date, weight, fclass,
            base, fuel_charged, 0, 0, 0, total, "FUEL_OVERAGE",
        )

    if error_label == "BASE_RATE_OVERAGE":
        mult = round(rng.uniform(1.08, 1.14), 3)
        base_charged = round(base * mult, 4)
        total = calc_total(weight, base_charged, fuel, 0, 0, 0)
        return _row_dict(
            invoice_id, contract, invoice_date, weight, fclass,
            base_charged, fuel, 0, 0, 0, total, "BASE_RATE_OVERAGE",
        )

    if error_label == "UNAUTHORIZED_ACCESSORIAL":
        kind = pick_unauthorized_accessorial(allowed)
        amt = accessorial_amount(rng)
        acc_l = acc_r = acc_i = 0.0
        if kind == "liftgate":
            acc_l = amt
        elif kind == "residential":
            acc_r = amt
        else:
            acc_i = amt
        total = calc_total(weight, base, fuel, acc_l, acc_r, acc_i)
        return _row_dict(
            invoice_id, contract, invoice_date, weight, fclass,
            base, fuel, acc_l, acc_r, acc_i, total, "UNAUTHORIZED_ACCESSORIAL",
        )

    if error_label == "WEIGHT_INFLATION":
        billed_weight = inflate_weight(weight, rng)
        total = calc_total(billed_weight, base, fuel, 0, 0, 0)
        return _row_dict(
            invoice_id, contract, invoice_date, billed_weight, fclass,
            base, fuel, 0, 0, 0, total, "WEIGHT_INFLATION",
        )

    if error_label == "TOTAL_MISMATCH":
        total_correct = calc_total(weight, base, fuel, 0, 0, 0)
        delta = round(rng.uniform(25, 65), 2)
        total_correct = round(total_correct + (delta if rng.random() < 0.5 else -delta), 2)
        total_correct = max(total_correct, 0.01)
        return _row_dict(
            invoice_id, contract, invoice_date, weight, fclass,
            base, fuel, 0, 0, 0, total_correct, "TOTAL_MISMATCH",
        )

    raise ValueError(f"Unknown error_label: {error_label}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    rng = random.Random(SEED)
    contracts_df = load_rate_table()

    # Persist the rate table snapshot used for this invoice run
    root = _repo_root()
    ref_dir = root / "data" / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    gen_invoice_path = ref_dir / "gen_invoice_master_rate_table.csv"
    contracts_df.to_csv(gen_invoice_path, index=False)

    # Exact label list (50 entries)
    labels: list[str] = []
    for label, n in COUNTS.items():
        labels.extend([label] * n)
    assert len(labels) == NUM_INVOICES

    # DUPLICATE must come after slots 3 and 7 exist — assign DUPLICATE only to slots >= 8
    dup_indices = [i for i, L in enumerate(labels) if L == "DUPLICATE"]
    if any(i < 7 for i in dup_indices):  # 0-based index 6 = slot 7
        # Swap DUPLICATE labels toward end
        safe_slots = [i for i in range(len(labels)) if i not in (2, 6) and labels[i] != "DUPLICATE"]
        for dup_i in dup_indices:
            if dup_i < 7:
                swap_j = rng.choice([s for s in safe_slots if s >= 7])
                labels[dup_i], labels[swap_j] = labels[swap_j], labels[dup_i]
                safe_slots.remove(swap_j)

    rows: list[dict[str, Any] | None] = [None] * NUM_INVOICES

    for slot in range(NUM_INVOICES):
        idx = slot + 1
        label = labels[slot]
        contract = contracts_df.iloc[rng.randint(0, len(contracts_df) - 1)]
        if label == "DUPLICATE":
            continue
        rows[slot] = build_row(idx, contract, rng, label)

    # Force slots 3 and 7 to exist and be CLEAN sources for duplicates
    for must_slot, must_label in ((2, "CLEAN"), (6, "CLEAN")):
        if rows[must_slot] is None:
            c = contracts_df.iloc[rng.randint(0, len(contracts_df) - 1)]
            rows[must_slot] = build_row(must_slot + 1, c, rng, must_label)
        else:
            # Ensure we have well-formed sources (optional: keep as-is if already built)
            pass

    # Fill DUPLICATE: copy row 3 and 7 content, new sequential IDs
    dup_slot_indices = [i for i in range(NUM_INVOICES) if labels[i] == "DUPLICATE"]
    source_rows = [deepcopy(rows[2]), deepcopy(rows[6])]
    for i, slot_idx in enumerate(dup_slot_indices[:2]):
        r = source_rows[i]
        r["invoice_id"] = f"INV-2024-{slot_idx + 1:04d}"
        r["_error_label"] = "DUPLICATE"
        rows[slot_idx] = r

    assert all(r is not None for r in rows)
    ordered = rows  # type: ignore

    rng.shuffle(ordered)

    out_df = pd.DataFrame(ordered)
    out_df = out_df[COLUMNS]

    root = _repo_root()
    out_raw = root / "data" / "raw" / "invoices_sample.csv"
    out_raw.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_raw, index=False)

    print("Error breakdown (_error_label):")
    for lab, cnt in out_df["_error_label"].value_counts().sort_index().items():
        print(f"  {lab}: {cnt}")
    print()

    def calculated_total(r: pd.Series) -> float:
        return calc_total(
            float(r["shipment_weight_lbs"]),
            float(r["base_rate_charged"]),
            float(r["fuel_surcharge_pct_charged"]),
            float(r["accessorial_liftgate"]),
            float(r["accessorial_residential"]),
            float(r["accessorial_inside_delivery"]),
        )

    mismatches = sum(
        1
        for _, r in out_df.iterrows()
        if abs(float(r["total_charged"]) - calculated_total(r)) > 0.01
    )
    print(f"⚠️ Validation: {mismatches} invoices where total_charged doesn't match calculated")
    print(f"Saved: {out_raw}")


if __name__ == "__main__":
    main()
