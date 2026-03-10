# Policy Engine Architecture

## Purpose

Deterministic **invoice vs contract** comparison. No LLM, no randomness, no I/O inside rule functions.  
Input: structured invoices + rate table. Output: structured `AuditFinding` list per invoice.

## Data flow

```
data/master_rate_table.csv
data/invoices_sample.csv   (or processed layer)
        │
        ▼
  load_rate_table()  →  dict[(lane_id, carrier_name)] → RateContract
  load_invoices()    →  list[FreightInvoice] + optional _error_label for validation only
        │
        ▼
  audit_invoices(invoices, rate_table)
        │
        ├── Per-invoice rules (sequential)
        │     check_base_rate
        │     check_fuel_surcharge
        │     check_unauthorized_accessorials
        │     check_total_mismatch
        │     check_weight_inflation
        │     check_missing_contract
        │
        └── Dataset rules (full scan)
              check_duplicate_invoice_id
              check_duplicate_content (fingerprint — catches DUPLICATE label when ids differ)
        │
        ▼
  dict[invoice_id, list[AuditFinding]]
```

## SPEC alignment (Engineering SPEC §4)

| User-facing check            | `rule_id`                    | Severity |
|-----------------------------|------------------------------|----------|
| Base rate mismatch          | `BASE_RATE_OVERAGE`          | HIGH     |
| Fuel surcharge violation    | `FUEL_SURCHARGE_OVERAGE`    | HIGH     |
| Accessorial fee violation   | `UNAUTHORIZED_ACCESSORIAL`   | MEDIUM   |
| Incorrect total amount      | `TOTAL_MISMATCH`             | LOW      |
| Missing contract lane       | `MISSING_CONTRACT`           | HIGH     |
| Duplicate invoice           | `DUPLICATE_INVOICE`          | HIGH     |
| Weight inflation (SPEC)     | `WEIGHT_INFLATION`           | MEDIUM   |

## Finding schema (§4.1)

Each finding is an `AuditFinding`:

- `invoice_id`, `rule_id`, `severity`
- `field_audited`, `charged_value`, `contract_value`
- `variance_pct` — `(charged - contract) / contract` when contract ≠ 0; else 0
- `dollar_impact` — recovery $
- `description` — one sentence

Product ask also lists `violation_type` / `expected_value` / `actual_value` / `variance`:

- `violation_type` ≡ `rule_id`
- `expected_value` ≡ `contract_value`
- `actual_value` ≡ `charged_value`
- `variance` — use `variance_pct` or absolute delta by rule (documented per rule)

## Tolerance

Base and fuel rules use `TOLERANCE = 0` (strict) unless SPEC tolerance is added later; optional tiny epsilon for float compare.

## WEIGHT_INFLATION note

SPEC Rule 5 alone (weight % 100 == 0) does not match the generator’s pattern
(`ceil(true/100)*100*1.04`). A deterministic supplemental check uses
`weight/1.04` near a multiple of 100 to flag inflated billed weight without
using `_error_label` at audit time.

## Testing strategy

`__main__` compares injected `_error_label` counts vs findings by mapping label → rule_id(s), prints Injected | Caught | Miss table — proof before UI/agent layers.
