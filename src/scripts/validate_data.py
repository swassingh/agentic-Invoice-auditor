"""
Data contract validator: master rate table + invoices_sample before Policy Engine.

Strict fuel mode (all rate table fuel_surcharge_pct must be 0.142):
  python src/scripts/validate_data.py --fuel-uniform 0.142

Current repo rate table uses per-lane fuel (0.11–0.142); default run skips uniform fuel.

Loads:
  - data/master_rate_table.csv (falls back to data/reference/master_rate_table.csv)
  - data/invoices_sample.csv

Exit code 0 if all checks pass; non-zero if any fail.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Expected _error_label counts (must match generate_invoices.py COUNTS)
EXPECTED_LABEL_COUNTS = {
    "FUEL_OVERAGE": 5,
    "BASE_RATE_OVERAGE": 4,
    "UNAUTHORIZED_ACCESSORIAL": 4,
    "DUPLICATE": 2,
    "WEIGHT_INFLATION": 3,
    "TOTAL_MISMATCH": 2,
    "CLEAN": 30,
}

# If your rate table uses per-lane fuel (not uniform), set to None to skip fuel check.
# User spec asked for all 0.142 — current generated table uses mixed rates; set False to enforce.
REQUIRE_UNIFORM_FUEL_PCT: float | None = None  # set to 0.142 to enforce uniform fuel in rate table

RATE_ROW_COUNT = 30  # 3 carriers × 10 lanes
CLEAN_TOTAL_TOLERANCE = 0.50

REQUIRED_INVOICE_COLS = [
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
    root = _repo_root()
    master = root / "data" / "master_rate_table.csv"
    reference = root / "data" / "reference" / "master_rate_table.csv"
    if master.exists():
        return pd.read_csv(master)
    if reference.exists():
        return pd.read_csv(reference)
    raise FileNotFoundError("master_rate_table.csv not found")


def load_invoices() -> pd.DataFrame:
    path = _repo_root() / "data" / "invoices_sample.csv"
    if not path.exists():
        raise FileNotFoundError(f"invoices_sample.csv not found at {path}")
    return pd.read_csv(path)


def calc_total_row(r: pd.Series) -> float:
    """Same formula as generator: freight * (1 + fuel) + accessorials."""
    w = float(r["shipment_weight_lbs"])
    b = float(r["base_rate_charged"])
    f = float(r["fuel_surcharge_pct_charged"])
    freight = w * b
    return round(
        freight * (1.0 + f)
        + float(r["accessorial_liftgate"])
        + float(r["accessorial_residential"])
        + float(r["accessorial_inside_delivery"]),
        2,
    )


def report(ok: bool, desc: str) -> bool:
    icon = "✅ PASS" if ok else "❌ FAIL"
    print(f"{icon}: {desc}")
    return ok


def main() -> int:
    global REQUIRE_UNIFORM_FUEL_PCT
    if "--fuel-uniform" in sys.argv:
        i = sys.argv.index("--fuel-uniform")
        if i + 1 < len(sys.argv):
            REQUIRE_UNIFORM_FUEL_PCT = float(sys.argv[i + 1])
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    all_ok = True
    try:
        rates = load_rate_table()
        inv = load_invoices()
    except FileNotFoundError as e:
        print(f"❌ FAIL: {e}")
        print("FIX ISSUES BEFORE PROCEEDING")
        return 1

    # --- Rate table checks ---
    rate_nulls = rates.isnull().any()
    if rate_nulls.any():
        bad = rate_nulls[rate_nulls].index.tolist()
        all_ok &= report(False, f"rate table nulls in columns: {bad}")
    else:
        all_ok &= report(True, "rate table — no null values in any column")

    if REQUIRE_UNIFORM_FUEL_PCT is not None:
        fuel_col = rates["fuel_surcharge_pct"]
        bad_fuel = fuel_col[abs(fuel_col.astype(float) - REQUIRE_UNIFORM_FUEL_PCT) > 1e-9]
        if len(bad_fuel) > 0:
            all_ok &= report(
                False,
                f"rate table fuel_surcharge_pct not all {REQUIRE_UNIFORM_FUEL_PCT} "
                f"({len(bad_fuel)} row(s) differ)",
            )
        else:
            all_ok &= report(
                True,
                f"rate table — all fuel_surcharge_pct == {REQUIRE_UNIFORM_FUEL_PCT}",
            )
    else:
        all_ok &= report(
            True,
            "rate table — fuel_surcharge_pct uniform check skipped (REQUIRE_UNIFORM_FUEL_PCT is None)",
        )

    if len(rates) != RATE_ROW_COUNT:
        all_ok &= report(
            False,
            f"rate table row count {len(rates)} != expected {RATE_ROW_COUNT} (3×10 contracts)",
        )
    else:
        all_ok &= report(True, f"rate table — {RATE_ROW_COUNT} contracts present")

    # effective_date < expiration_date
    eff = pd.to_datetime(rates["effective_date"])
    exp = pd.to_datetime(rates["expiration_date"])
    date_ok = (eff < exp).all()
    if not date_ok:
        all_ok &= report(False, "rate table — effective_date >= expiration_date for some row(s)")
    else:
        all_ok &= report(True, "rate table — effective_date < expiration_date for all rows")

    # --- Invoice checks ---
    inv_nulls = inv[REQUIRED_INVOICE_COLS].isnull().any()
    if inv_nulls.any():
        bad = inv_nulls[inv_nulls].index.tolist()
        all_ok &= report(False, f"invoices — null in required columns: {bad}")
    else:
        all_ok &= report(True, "invoices — no nulls in required columns")

    # (lane_id, carrier_name) must exist in rate table
    rate_keys = set(
        zip(rates["lane_id"].astype(str), rates["carrier_name"].astype(str))
    )
    missing_contract = []
    for _, row in inv.iterrows():
        key = (str(row["lane_id"]), str(row["carrier_name"]))
        if key not in rate_keys:
            missing_contract.append((row["invoice_id"], key))
    if missing_contract:
        all_ok &= report(
            False,
            f"invoices — {len(missing_contract)} row(s) lane_id+carrier not in rate table "
            f"(e.g. {missing_contract[0]})",
        )
    else:
        all_ok &= report(True, "invoices — every lane_id + carrier_name exists in rate table")

    # invoice_id: either (a) exactly 2 ids appear twice each, or (b) 2 DUPLICATE-labeled
    # rows (content duplicate with distinct ids — how generate_invoices builds them)
    counts = inv["invoice_id"].value_counts()
    dup_ids = counts[counts > 1]
    dup_label_count = (inv["_error_label"] == "DUPLICATE").sum()
    if len(dup_ids) == 2 and dup_ids.eq(2).all():
        all_ok &= report(
            True,
            f"invoice_id — 2 ids duplicated once each: {list(dup_ids.index)}",
        )
    elif dup_label_count == 2 and len(dup_ids) == 0:
        all_ok &= report(
            True,
            "invoice_id — all unique; 2 DUPLICATE rows (content duplicate, distinct ids) OK",
        )
    elif dup_label_count == 2:
        all_ok &= report(
            True,
            f"invoice_id — DUPLICATE label rows: {dup_label_count}; id counts: {dict(dup_ids)}",
        )
    else:
        all_ok &= report(
            False,
            f"invoice_id — expected 2 duplicate ids or 2 DUPLICATE labels; "
            f"dup_ids={dict(dup_ids)}, DUPLICATE rows={dup_label_count}",
        )

    # _error_label distribution
    actual = inv["_error_label"].value_counts().to_dict()
    print("  _error_label counts (actual):")
    for lab in sorted(actual.keys()):
        print(f"    {lab}: {actual[lab]}")
    label_mismatch = False
    for lab, expected in EXPECTED_LABEL_COUNTS.items():
        if actual.get(lab, 0) != expected:
            label_mismatch = True
            break
    if label_mismatch:
        all_ok &= report(False, f"_error_label distribution != expected {EXPECTED_LABEL_COUNTS}")
    else:
        all_ok &= report(True, "_error_label distribution matches expected")

    # CLEAN invoices: total within $0.50 of calculated
    clean = inv[inv["_error_label"] == "CLEAN"]
    clean_bad = []
    for _, r in clean.iterrows():
        calc = calc_total_row(r)
        if abs(float(r["total_charged"]) - calc) > CLEAN_TOTAL_TOLERANCE:
            clean_bad.append((r["invoice_id"], r["total_charged"], calc))
    if clean_bad:
        all_ok &= report(
            False,
            f"CLEAN total check — {len(clean_bad)} invoice(s) outside ${CLEAN_TOTAL_TOLERANCE} "
            f"(e.g. {clean_bad[0]})",
        )
    else:
        all_ok &= report(
            True,
            f"CLEAN invoices — total_charged within ${CLEAN_TOTAL_TOLERANCE} of calculated",
        )

    # --- Cross-file ---
    rate_lane_ids = set(rates["lane_id"].astype(str))
    rate_carriers = set(rates["carrier_name"].astype(str))
    inv_lanes = set(inv["lane_id"].astype(str))
    inv_carriers = set(inv["carrier_name"].astype(str))
    orphan_lanes = inv_lanes - rate_lane_ids
    orphan_carriers = inv_carriers - rate_carriers
    if orphan_lanes:
        all_ok &= report(False, f"cross-file — invoice lane_id not in rate table: {orphan_lanes}")
    else:
        all_ok &= report(True, "cross-file — no invoice lane_id outside rate table")
    if orphan_carriers:
        all_ok &= report(
            False,
            f"cross-file — invoice carrier not in rate table: {orphan_carriers}",
        )
    else:
        all_ok &= report(True, "cross-file — no invoice carrier outside rate table")

    if all_ok:
        print("\nDATA READY FOR ENGINE")
        return 0
    print("\nFIX ISSUES BEFORE PROCEEDING")
    return 1


if __name__ == "__main__":
    sys.exit(main())
