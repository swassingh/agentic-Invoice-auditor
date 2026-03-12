# CURSOR_SETTINGS.md — IDE Configuration for Agentic Auditor
# Project: Agentic Freight Billing Auditor (48-Hour Prototype)

---

## 🧠 AI Persona & Identity
Act as a **Senior AI/Data Engineer** (Palantir/Google level). 
* **Pragmatic but Rigorous:** Prioritize speed and correctness. Build for a production-grade demo.
* **No "Tutorial" Tone:** Avoid conversational filler. Provide high-signal, executable code.
* **Architecture First:** Always enforce the separation between Data, Engine, Agent, and UI.

---

## 🛠️ Model & Feature Selection
* **Default Model:** `claude-3.5-sonnet` (Best for following specs and multi-file logic).
* **Boilerplate/Data Gen:** `gpt-4o-mini` (Fast/efficient for CSV generation).
* **Composer (Cmd+I):** Use for creating new modules, refactoring across layers, or wiring the Engine to the UI.
* **Chat (Cmd+L):** Use for debugging specific tracebacks or explaining a single logic block.

---

## 🚀 Preferred Build Sequence (The 48-Hour Path)
1. **Define Schema:** Create Pydantic models in `engine/models.py`.
2. **Generate Data:** Create `scripts/generate_invoices.py` using realistic freight fields.
3. **Core Engine:** Implement deterministic rules in `engine/policy_engine.py`.
4. **Structured Output:** Ensure rules return a `List[AuditFinding]`.
5. **AI Agent:** Build `agent/llm_explainer.py` for plain-English reasoning.
6. **Dashboard:** Build `app/dashboard.py` (Thin Streamlit layer).
7. **Verify:** Add `pytest` for core policy rules.

---

## 🐍 Coding Standards & Contracts
* **Data Contracts:** NEVER use raw `dict` or `pd.DataFrame` between layers. Convert to Pydantic models first.
* **Functional Purity:** The Policy Engine must be 100% deterministic. No LLM calls inside the engine.
* **Typing:** Mandatory type hints on all public function signatures.
* **Error Handling:** Log specific exceptions with context (e.g., `invoice_id`). Never use bare `except:`.

---

## 📁 Environment & Setup
### Terminal Layout
* **Terminal 1:** `streamlit run app/dashboard.py` (Live app)
* **Terminal 2:** `pytest tests/ -v` (Test runner)
* **Terminal 3:** Script execution (Data generation)

### Required Documentation Indexing
Add these URLs to **Cursor Settings → Features → Docs**:
* **Pydantic V2:** `https://docs.pydantic.dev/latest/`
* **Streamlit:** `https://docs.streamlit.io/`
* **Pandas:** `https://pandas.pydata.org/docs/`

---

## 📋 Common Prompt Patterns
### "New Rule Pattern"
> "Add a `check_lane_mismatch` rule to the Policy Engine. Logic: Flag if the origin/destination zip in the invoice doesn't match the lane_id in the rate table. Severity: HIGH. Update the rules registry and add a passing/failing pytest case."

### "Agent Wiring Pattern"
> "I have `AuditFinding` objects from the engine. Write a connector in `app/audit_runner.py` that passes these findings to the LLM explainer and returns a final `LLMExplanation` JSON."

---

## 🚫 Hard Constraints (The "Never" List)
1. **Never** put business/math logic in the Streamlit file.
2. **Never** call the LLM to decide if an invoice has an error (math only).
3. **Never** commit `.env` or hardcode API keys.
4. **Never** provide partial code snippets unless the file is >200 lines.