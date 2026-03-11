"""
Synthetic RAW + reference data generation (repeatable seed).
Writes:
  data/reference/gen_data_master_rate_table.csv
  data/raw/freight_invoices.csv
Does not perform ingestion — run ingestion separately.
"""

from __future__ import annotations

import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# Repo root on path for `from src.engine...`
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.engine.models import FreightInvoice, RateContract

SEED = 42
NUM_INVOICES = 50
NUM_LANES = 10
CARRIERS = ["FastFreight Inc", "ReliableHaul LLC", "NationalFreight Co"]


def _ensure_dirs() -> tuple[Path, Path]:
    root = _ROOT
    ref_dir = root / "data" / "reference"
    raw_dir = root / "data" / "raw"
    ref_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    return ref_dir, raw_dir


def build_rate_table(rng: random.Random) -> list[RateContract]:
    """
    10 unique lanes × 3 carriers = 30 contracts (Engineering SPEC).
    Negotiated base rates and fuel surcharge caps per lane.
    """
    # Fixed zip pairs for 10 lanes
    lane_zips = [
        ("60601", "10001"),
        ("75201", "30301"),
        ("98101", "80202"),
        ("85001", "78701"),
        ("02101", "19101"),
        ("94102", "92101"),
        ("33101", "20001"),
        ("55401", "43215"),
        ("63101", "37201"),
        ("40202", "44101"),
    ]
    base_rates = [0.42, 0.38, 0.55, 0.48, 0.51, 0.44, 0.39, 0.47, 0.53, 0.45]
    fuel_pcts = [0.12, 0.115, 0.142, 0.13, 0.128, 0.12, 0.11, 0.135, 0.14, 0.125]

    contracts: list[RateContract] = []
    effective = date(2024, 1, 1)
    expiration = date(2026, 12, 31)

    for i in range(NUM_LANES):
        lane_id = f"LANE_{i+1:03d}"
        oz, dz = lane_zips[i]
        base = base_rates[i]
        fuel = fuel_pcts[i]
        allowed = "inside_delivery|residential" if i % 2 == 0 else "liftgate|inside_delivery"
        for carrier in CARRIERS:
            # Slight carrier variance optional — keep same per lane for clearer audits
            contracts.append(
                RateContract(
                    lane_id=lane_id,
                    carrier_name=carrier,
                    origin_zip=oz,
                    destination_zip=dz,
                    agreed_base_rate_per_lb=round(base, 4),
                    fuel_surcharge_pct=round(fuel, 4),
                    allowed_accessorials=allowed,
                    effective_date=effective,
                    expiration_date=expiration,
                )
            )
    return contracts


def _pick_contract(
    contracts: list[RateContract], rng: random.Random
) -> RateContract:
    return rng.choice(contracts)


def _compute_total(
    weight_lb: float,
    base_per_lb: float,
    fuel_pct: float,
    acc_lift: float,
    acc_res: float,
    acc_inside: float,
) -> float:
    freight = weight_lb * base_per_lb
    fuel_amt = freight * fuel_pct
    return round(freight + fuel_amt + acc_lift + acc_res + acc_inside, 2)


def build_invoices(
    contracts: list[RateContract], rng: random.Random
) -> list[FreightInvoice]:
    """
    50 invoices; ~30% with intentional errors:
    - Fuel surcharge overage
    - Base rate overage
    - Duplicate invoice_ids
    """
    invoices: list[FreightInvoice] = []
    freight_classes = ["70", "85", "100"]
    base_date = date(2025, 1, 15)

    # ~30% with at least one intentional error (fuel/base overage, etc.)
    error_indices = set(rng.sample(range(NUM_INVOICES), k=15))

    for n in range(NUM_INVOICES):
        c = _pick_contract(contracts, rng)
        weight = round(rng.uniform(500, 5000), 2)
        fclass = rng.choice(freight_classes)
        inv_date = base_date + timedelta(days=rng.randint(0, 120))

        base_charged = c.agreed_base_rate_per_lb
        fuel_charged = c.fuel_surcharge_pct
        acc_l = acc_r = acc_i = 0.0
        if rng.random() < 0.25:
            acc_l = round(rng.choice([0, 0, 75, 125]), 2)
        if rng.random() < 0.2 and "residential" in c.allowed_accessorials:
            acc_r = round(rng.choice([0, 50, 95]), 2)

        total = _compute_total(weight, base_charged, fuel_charged, acc_l, acc_r, acc_i)

        invoice_id = f"INV-2025-{n+1:04d}"

        # Error injection
        if n in error_indices:
            etype = rng.choice(["fuel", "base", "both", "dup_only"])
            if etype == "fuel" or etype == "both":
                # Contract cap exceeded, e.g. 12% → 15%
                fuel_charged = min(0.22, c.fuel_surcharge_pct + rng.uniform(0.03, 0.08))
                fuel_charged = round(fuel_charged, 4)
            if etype == "base" or etype == "both":
                # Base rate mismatch, e.g. $450 lane → invoice uses higher $/lb
                base_charged = round(
                    c.agreed_base_rate_per_lb + rng.uniform(0.10, 0.35), 4
                )
            total = _compute_total(weight, base_charged, fuel_charged, acc_l, acc_r, acc_i)

        inv = FreightInvoice(
            invoice_id=invoice_id,
            carrier_name=c.carrier_name,
            invoice_date=inv_date,
            lane_id=c.lane_id,
            origin_zip=c.origin_zip,
            destination_zip=c.destination_zip,
            shipment_weight_lbs=weight,
            freight_class=fclass,
            base_rate_charged=base_charged,
            fuel_surcharge_pct_charged=fuel_charged,
            accessorial_liftgate=acc_l,
            accessorial_residential=acc_r,
            accessorial_inside_delivery=acc_i,
            total_charged=total,
        )
        invoices.append(inv)

    # Duplicate invoice IDs (dedup test): same id on two distinct rows
    if len(invoices) > 7:
        invoices[6] = invoices[6].model_copy(update={"invoice_id": invoices[5].invoice_id})
    if len(invoices) > 19:
        invoices[18] = invoices[18].model_copy(
            update={"invoice_id": invoices[17].invoice_id}
        )

    return invoices


def _contracts_to_df(contracts: list[RateContract]) -> pd.DataFrame:
    rows = [c.model_dump() for c in contracts]
    for r in rows:
        r["effective_date"] = r["effective_date"].isoformat()
        r["expiration_date"] = r["expiration_date"].isoformat()
    return pd.DataFrame(rows)


def _invoices_to_df(invoices: list[FreightInvoice]) -> pd.DataFrame:
    rows = [inv.model_dump() for inv in invoices]
    for r in rows:
        r["invoice_date"] = r["invoice_date"].isoformat()
    return pd.DataFrame(rows)


def main() -> None:
    # Windows consoles often default to cp1252; SPEC asks for emoji in output
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    rng = random.Random(SEED)
    ref_dir, raw_dir = _ensure_dirs()

    contracts = build_rate_table(rng)
    df_rates = _contracts_to_df(contracts)

    # Write both a generic master_rate_table.csv and a gen_data_ variant
    gen_data_path = ref_dir / "gen_data_master_rate_table.csv"
    df_rates.to_csv(gen_data_path, index=False)

    # Reset rng stream for invoice generation after rate table built
    rng = random.Random(SEED + 1)
    invoices = build_invoices(contracts, rng)
    raw_path = raw_dir / "freight_invoices.csv"
    df_inv = _invoices_to_df(invoices)
    df_inv.to_csv(raw_path, index=False)

    n_contracts = len(contracts)
    n_carriers = df_rates["carrier_name"].nunique()
    n_lanes = df_rates["lane_id"].nunique()
    sample = df_rates.iloc[0].to_dict()
    print(f"✅ Rate table generated: {n_contracts} contracts across {n_carriers} carriers and {n_lanes} lanes")
    print(f"📋 Sample row: {sample}")


if __name__ == "__main__":
    main()
