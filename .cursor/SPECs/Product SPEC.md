# SPEC.md

## Project Name
Agentic Invoice Auditor

---

## Overview
Build a lightweight prototype of an industrial freight invoice auditing workflow.

The system should simulate how enterprise teams move from messy source data to audit-ready outputs using a DataOps pipeline and an AI explanation layer.

This project is inspired by enterprise invoice auditing systems that:
- ingest invoice documents and ERP data
- compare billed charges against contracted rates
- detect discrepancies
- explain rejections through an AI assistant

This version is a solo prototype focused on workflow clarity, not enterprise scale.

---

## Product Goal
Demonstrate an end-to-end workflow that:

1. generates or ingests freight invoice data
2. compares invoice charges to a master contract rate table
3. detects billing discrepancies
4. explains why an invoice failed validation
5. presents results in a simple Streamlit dashboard

---

## User Story
As an operations analyst or finance reviewer,
I want to upload or inspect freight invoices and automatically see
whether they violate contract pricing rules,
so that I can quickly identify billing leakage and understand the reason for each rejection.

---

## Core Demo Narrative
The demo should clearly show this flow:

### Raw
Synthetic invoice data representing freight bills

### Structured
Normalized tabular invoice fields

### Policy Validation
A deterministic policy engine checks invoice values against contract rates

### Agent Explanation
An AI explanation layer converts rule violations into plain-English reasoning

### Gold / Audit-Ready
A final result showing pass/fail, discrepancy details, and explanation

This raw-to-gold DataOps story should be visible in the repo and UI.

---

## v1 Scope

### In Scope
- synthetic freight invoice generation in CSV format
- master rate table generation in CSV format
- deterministic validation logic in Python
- structured audit result outputs
- Streamlit dashboard for invoice review
- natural language explanation of failed invoices
- local-first execution

### Out of Scope
- real ERP integration
- real SAP connectivity
- production deployment
- authentication/authorization
- real PDF OCR in v1
- human-in-the-loop workflow queues
- distributed or large-scale processing
- advanced multi-agent orchestration

---

## Data Model

### Invoice Fields
Synthetic invoices should include fields similar to:

- invoice_id
- invoice_date
- carrier
- origin
- destination
- lane_id
- shipment_weight_lb
- billed_base_rate
- billed_fuel_surcharge_pct
- billed_accessorial_fee
- billed_total_amount

Optional additional fields:
- service_level
- distance_miles
- currency
- contract_id

### Master Rate Table Fields
The master rate table should include:

- contract_id
- carrier
- lane_id
- origin
- destination
- contract_base_rate
- contract_fuel_surcharge_pct
- allowed_accessorial_fee
- effective_date
- expiration_date

---

## Functional Requirements

### FR1: Synthetic data generation
The system must generate:
- a master rate table
- at least 50 synthetic freight invoices
- intentional billing discrepancies in a subset of invoices

Examples of discrepancies:
- billed base rate higher than contract rate
- billed fuel surcharge higher than allowed
- accessorial fee above allowed amount
- total amount inconsistent with component charges
- lane mismatch or unknown lane
- duplicate invoice_id

### FR2: Policy engine
The system must compare invoices against the master rate table and determine:
- pass or fail
- type of violation
- expected values
- actual values
- variance

The policy engine must be deterministic and not depend on an LLM.

### FR3: Structured audit outputs
For every processed invoice, return a structured result containing fields such as:
- invoice_id
- audit_status
- rule_results
- rejection_reasons
- total_variance_amount
- severity

### FR4: AI explanation layer
For failed invoices, generate a plain-English explanation that:
- identifies the violated rule(s)
- references expected vs actual values
- states why the invoice should be rejected
- is grounded in the structured policy output

### FR5: Streamlit dashboard
The dashboard should allow a user to:
- load sample invoice data
- upload a CSV invoice file or select a sample invoice
- run audit checks
- view structured findings
- view AI-generated explanation
- understand the raw-to-gold workflow

---

## Non-Functional Requirements

### NFR1: Clarity
The codebase should be easy to review and understand quickly.

### NFR2: Modularity
Validation logic, explanation logic, data generation, and UI should be separate.

### NFR3: Reliability
The policy engine should produce reproducible outputs for the same input.

### NFR4: Explainability
Failures should be understandable by non-technical users.

### NFR5: Demo-readiness
The project should be runnable locally with a short setup process.

---

## Suggested Architecture

```text
data/generated/*.csv
        ↓
src/data_processing/loaders.py
        ↓
src/policy_engine/validator.py
        ↓
src/policy_engine/rules.py
        ↓
src/agent/explainer.py
        ↓
app/streamlit_app.py