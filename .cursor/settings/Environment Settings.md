# CURSOR_SETTINGS.md — Cursor IDE Configuration Guide
# Project: Agentic Freight Billing Auditor
# Author: Swastik Singh

---

## How to Load These Settings Into Cursor

### 1. Project Rules (rules.md)
- Open Cursor → `Cmd+Shift+P` → "Cursor Settings"
- Navigate to: **Features → Rules for AI**
- Paste the full contents of `rules.md` into the "Rules for AI" box
- OR: Save `rules.md` as `.cursorrules` in the **project root** — Cursor auto-loads it

```bash
# In your project root:
cp rules.md .cursorrules
```

### 2. Enable These Cursor Features

| Feature | Setting | Why |
|---|---|---|
| **Codebase Indexing** | ON | Cursor reads your full project so suggestions are context-aware |
| **Auto-import** | ON | Python imports resolved automatically |
| **Docs indexing** | Add Pydantic, Streamlit, Pandas docs | Get accurate suggestions for these libs |
| **Privacy Mode** | Your call | If proprietary data, enable it |

---

## Recommended Model Settings

| Context | Model to Use |
|---|---|
| Writing new functions | `claude-3.5-sonnet` or `gpt-4o` |
| Debugging / tracing errors | `claude-3.5-sonnet` (best at reading tracebacks) |
| Boilerplate / data generation | `gpt-4o-mini` (fast + cheap) |
| Architecture decisions | `claude-3.5-sonnet` |

**Tip:** Use `claude-3.5-sonnet` as your default. It's strongest at following structured rules and maintaining layered architecture across a session.

---

## Cursor Composer Setup (Multi-file edits)

Use **Composer** (not Chat) when:
- Creating a new module from scratch
- Refactoring across multiple files
- Wiring a new layer into existing code

### How to open Composer:
`Cmd+I` (Mac) / `Ctrl+I` (Windows)

### Composer workflow for this project:
1. Always describe the **layer** you're working in: *"I'm adding a new rule to the Policy Engine layer"*
2. Reference the schema: *"Use the FreightInvoice and RateContract Pydantic models defined in models.py"*
3. Ask for tests alongside code: *"Also generate the pytest unit test for this rule"*

---

## Cursor Chat — Recommended Prompt Patterns

### When generating a new audit rule:
```
Add a new Policy Engine rule called check_weight_rounding.

Rule logic: If the invoice shipment_weight_lbs is rounded to the nearest 
100 lbs and is more than 2% higher than the expected weight, flag it.

Use the existing AuditFinding schema. Severity: MEDIUM.
Calculate dollar_impact as: (rounded_weight - actual_weight) * base_rate_charged.
Add it to the rules registry in policy_engine.py.
Then write a pytest test with one passing and one failing invoice.
```

### When debugging:
```
Here is my traceback: [paste traceback]
Here is the function: [paste function]
Here is the input data: [paste sample row]

Identify the root cause. Do not rewrite the whole function — 
explain the issue first, then show me the minimal fix.
```

### When wiring layers together:
```
I have:
- engine/policy_engine.py → returns List[AuditFinding]
- agent/llm_explainer.py → takes List[AuditFinding], returns LLMExplanation

Now write the connector function in app/dashboard.py that:
1. Runs the policy engine on an uploaded DataFrame
2. Groups findings by invoice_id
3. Calls the explainer for each invoice with findings
4. Returns a list of (invoice_id, List[AuditFinding], LLMExplanation) tuples

Do not put business logic in the Streamlit file — this connector 
function should be in a separate app/audit_runner.py module.
```

---

## Docs to Index in Cursor

Go to **Cursor Settings → Features → Docs** and add:

| Library | URL |
|---|---|
| Pydantic V2 | `https://docs.pydantic.dev/latest/` |
| Streamlit | `https://docs.streamlit.io/` |
| Pandas | `https://pandas.pydata.org/docs/` |
| OpenAI Python SDK | `https://platform.openai.com/docs/api-reference` |
| Anthropic Python SDK | `https://docs.anthropic.com/` |
| Pytest | `https://docs.pytest.org/en/stable/` |

---

## File Watcher / Terminal Setup

### Recommended `.env` file (never commit this):
```bash
# .env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
RATE_TOLERANCE_PCT=0.01        # 1% tolerance for rate comparisons
LOG_LEVEL=INFO
DATA_DIR=./data
```

### Recommended `.gitignore` additions:
```
.env
*.env
__pycache__/
.pytest_cache/
*.pyc
.streamlit/secrets.toml
data/raw/
```

### Recommended terminal split layout in Cursor:
- **Terminal 1:** `streamlit run app/dashboard.py` (live app)
- **Terminal 2:** `pytest tests/ -v --tb=short` (test runner)
- **Terminal 3:** Free for scripts / data generation

---

## Cursor Keyboard Shortcuts to Know

| Action | Mac | Windows |
|---|---|---|
| Open Composer | `Cmd+I` | `Ctrl+I` |
| Open Chat | `Cmd+L` | `Ctrl+L` |
| Inline edit | `Cmd+K` | `Ctrl+K` |
| Accept suggestion | `Tab` | `Tab` |
| Reject suggestion | `Escape` | `Escape` |
| Index codebase | `Cmd+Shift+P` → "Resync" | `Ctrl+Shift+P` → "Resync" |

---

## Project Initialization Commands

Run these once to set up your environment:

```bash
# Create project structure
mkdir -p freight_auditor/{data,engine,agent,app,tests/fixtures,scripts}
touch freight_auditor/{engine,agent,app,tests}/__init__.py

# Create virtual environment
cd freight_auditor
python3.11 -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install pydantic pandas streamlit openai anthropic python-dotenv pytest loguru

# Freeze requirements
pip freeze > requirements.txt

# Initialize git
git init
echo ".env" >> .gitignore
echo "__pycache__/" >> .gitignore
git add .
git commit -m "init: project scaffold"
```
