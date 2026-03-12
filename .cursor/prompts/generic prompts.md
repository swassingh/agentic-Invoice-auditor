# PROMPTS.md — Execution Command List
# Project: Agentic Freight Billing Auditor

> **Instructions:** Copy and paste these into Cursor (Cmd+L for chat, Cmd+I for Composer) to execute the build phases.

---

## 🏗️ Phase 1: Scaffolding & Data Contracts
**Goal:** Establish the Pydantic "Firewall" between layers.

**Prompt:**
> "Initialize the project structure based on `SPEC.md`. Create `src/engine/models.py` and define Pydantic models for `RateContract`, `FreightInvoice`, and `AuditFinding`. Ensure all fields match the specifications in `Claude rules.md`. Add a `Config` class to allow arbitrary types if needed, and include a `total_variance` calculated property in the findings."

---

## 📊 Phase 2: Synthetic Data Generation
**Goal:** Create the "Raw" data with intentional billing leaks.

**Prompt:**
> "Act as a Data Engineer. Write `src/scripts/generate_data.py`. Use the `RateContract` and `FreightInvoice` models. Generate a master CSV with 10 lanes and a second CSV with 50 invoices. **Crucial:** Inject intentional errors into 30% of the invoices: 
> 1. Fuel surcharge overages (e.g., contract says 12%, invoice says 15%)
> 2. Base rate mismatches 
> 3. Duplicate invoice IDs. 
> Save outputs to `data/master_rates.csv` and `data/raw_invoices.csv`."

---

## 🧠 Phase 3: The Deterministic Policy Engine
**Goal:** Build the "Brain" that finds the leaks without AI.

**Prompt:**
> "Using `Claude rules.md` as a guide, implement `src/engine/policy_engine.py`. Create a class `FreightAuditor` that loads the master rates and validates a list of invoices. Implement the 6 core rules from `gemini SPEC.md`. The output must be a `List[AuditFinding]`. **Constraint:** No LLM calls allowed in this file. Ensure the math is 100% deterministic."

---

## 🤖 Phase 4: The Agentic Explainer
**Goal:** Give the Auditor a "Voice" to explain rejections.

**Prompt:**
> "Build `src/agent/explainer.py`. Create a function that takes a list of `AuditFinding` objects and calls the LLM to generate a plain-English explanation. Use the system prompt defined in `Claude SPEC.md`. The agent should output a structured `LLMExplanation` JSON including a 'dispute_message' for the carrier. Reference `gemini rules.md` for the temperature and fallback settings."

---

## 🖥️ Phase 5: The Streamlit Dashboard
**Goal:** The "Gold" layer—visualizing the workflow.

**Prompt:**
> "Build `app/dashboard.py` using Streamlit. Follow the UI layout in `chatgpt rules.md`. 
> 1. Create a sidebar for file uploads. 
> 2. Display 'Invoices Audited' and 'Total Leakage' metrics at the top. 
> 3. Show a dataframe of all invoices with color-coded status. 
> 4. Add an 'Audit Deep Dive' section where the user can see the AI's explanation for a specific rejected invoice. 
> **Constraint:** Call the engine and agent logic from `src/`, do not write business logic in this file."

---

## 🧪 Phase 6: Verification
**Goal:** Ensure the "Gold" data is actually accurate.

**Prompt:**
> "Generate `tests/test_policy.py`. Create test cases for `BASE_RATE_OVERAGE` and `FUEL_SURCHARGE_OVERAGE`. Use a mock `RateContract` and verify that the `PolicyEngine` correctly identifies the dollar impact and variance percentage. Follow the testing rules in `Claude rules.md`."