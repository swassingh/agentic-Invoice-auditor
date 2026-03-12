# prompts.md

This file contains reusable prompts for developing the Agentic Invoice Auditor project.

Each prompt assumes that Cursor should follow the repository's rules, settings, and specs before generating code.

Relevant documents:

- .cursor/rules/*
- .cursor/settings/*
- .cursor/SPECs/*

All prompts should prioritize:
- deterministic business logic
- modular Python code
- clarity and explainability
- separation between validation logic, AI explanation, and UI

---

# Prompt: Project Setup

Follow all engineering rules, settings, and specifications in this repository.

Create the initial project structure for the Agentic Invoice Auditor.

Requirements:
- organize code into logical modules
- separate data generation, validation, explanation, and UI layers
- avoid monolithic scripts

Expected folder structure:

src/
    data_generation/
    data_processing/
    policy_engine/
    agent/
    utils/

data/
    generated/

app/

tests/

requirements.txt
README.md

Explain:
1. which files will be created
2. the purpose of each module
3. any assumptions made

Then generate the implementation.

---

# Prompt: Generate Synthetic Freight Data

Follow repository rules and specs.

Create a Python module that generates synthetic freight invoice data.

Requirements:

Generate:
- a master contract rate table
- at least 50 freight invoices

Include realistic fields such as:
- invoice_id
- carrier
- origin
- destination
- lane_id
- shipment_weight_lb
- billed_base_rate
- billed_fuel_surcharge_pct
- billed_accessorial_fee
- billed_total_amount

Include intentional discrepancies in approximately 20–30% of invoices such as:
- incorrect base rate
- excessive fuel surcharge
- invalid accessorial fee
- incorrect total amount
- missing contract lane

Output files should be written to:

data/generated/
    invoices.csv
    master_rate_table.csv

Explain the schema before generating the code.

---

# Prompt: Build the Policy Engine

Follow repository rules and specs.

Implement the deterministic invoice validation engine.

Requirements:

The validator must compare invoice data against the master rate table.

Implement the following checks:

- base rate mismatch
- fuel surcharge violation
- accessorial fee violation
- total amount inconsistency
- missing contract or lane mismatch
- duplicate invoice detection

Constraints:

- pass/fail must NOT be determined by an LLM
- logic must be deterministic
- outputs must be structured

Expected output fields:

- invoice_id
- audit_status
- violation_type
- expected_value
- actual_value
- variance
- severity
- explanation

Implementation guidelines:

- modular functions
- typed Python where appropriate
- clear docstrings
- easy to test

Explain the architecture before writing code.

---

# Prompt: Generate AI Explanation Layer

Follow repository rules and specs.

Implement the AI explanation module.

Purpose:

Convert structured validation results into a human-readable explanation.

Important constraint:

The AI must NOT determine pass/fail decisions.
It only explains rule violations produced by the policy engine.

Inputs:

Structured audit output such as:

- expected values
- actual values
- rule violations
- variance

Output:

A concise explanation such as:

"Invoice INV-1042 should be rejected because the billed fuel surcharge of 18% exceeds the contract limit of 15%. The base freight rate is also $120 above the agreed lane rate."

Implementation goals:

- grounded explanations
- no hallucinated information
- reference rule violations explicitly
- concise language

Explain how the explanation pipeline works before coding.

---

# Prompt: Build the Streamlit Dashboard

Follow repository rules and specs.

Create a Streamlit dashboard that demonstrates the invoice auditing workflow.

The dashboard should allow a user to:

1. load the generated sample data
2. upload an invoice CSV
3. run audit checks
4. view validation results
5. view AI-generated explanations

UI priorities:

- simple and professional
- clearly show the workflow
- separate raw rule outputs from AI explanation

Suggested sections:

Invoice Input  
Audit Results  
AI Explanation  

Explain the UI layout before generating the implementation.

---

# Prompt: Write Tests

Follow repository rules and specs.

Create tests for the policy engine.

Tests should validate:

- correct invoices pass validation
- base rate violations are detected
- fuel surcharge violations are detected
- missing contracts trigger errors
- duplicate invoices are detected

Use lightweight tests.

Prioritize correctness over test volume.

Explain the test strategy before writing the tests.

---

# Prompt: Architecture Review

Review the repository architecture.

Evaluate:

- modularity
- separation of concerns
- clarity of business rules
- correctness of the validation logic
- maintainability

Provide suggestions for improvement.

Focus on practical engineering improvements rather than stylistic preferences.

---

# Prompt: Refactor Module

Refactor the specified module.

Goals:

- improve readability
- reduce duplication
- improve modularity
- preserve existing behavior

Constraints:

- do not change business logic unless necessary
- maintain compatibility with existing modules
- document changes clearly

Explain what is being refactored before generating the new code.

---

# Prompt: Demo Readiness Check

Evaluate whether the project is ready for a demo.

Check:

- the synthetic data generator works
- the policy engine detects discrepancies
- the Streamlit app runs
- explanations are clear
- the workflow from raw data to audited output is visible

Provide a short checklist of improvements needed before presenting the system.