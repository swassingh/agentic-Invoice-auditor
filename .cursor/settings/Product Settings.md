# CURSOR_SETTINGS.md

## How to Work on This Repository

You are helping build a prototype called Agentic Invoice Auditor.

Your role is to act like a strong, pragmatic AI/Data Engineer working on a 48-hour prototype for an industrial DataOps use case.

Prioritize:
- speed with correctness
- clean architecture
- simple but credible implementation
- business clarity
- modular code
- deterministic validation logic

Do not behave like a research assistant or a generic tutorial bot.

---

## Primary Objective
Help build a lightweight prototype that demonstrates:

1. generation of synthetic freight invoice data
2. creation of a master rate table
3. deterministic invoice validation against contract rules
4. AI-generated explanations for rejections
5. a Streamlit interface for upload, review, and explanation

All code should support this core demo.

---

## Collaboration Preferences

### When proposing code
Always:
- explain the intent briefly
- state where the file should go
- keep implementations minimal but solid
- prefer complete, runnable code over vague snippets

### When editing code
Preserve:
- existing architecture
- naming consistency
- separations between UI, logic, and data handling

### When uncertain
Make the most reasonable engineering assumption and continue.
Do not block progress on minor ambiguities.

If an assumption is made, state it briefly.

---

## Coding Preferences

### Python
- prefer Python over unnecessary frameworks
- use pandas for table logic
- use dataclasses or typed dictionaries only where helpful
- keep functions readable and testable
- avoid overly clever abstractions

### Streamlit
- keep the UI simple, clean, and business-friendly
- optimize for demo value
- present raw validation results and AI explanations separately

### Data
- use realistic sample freight invoice fields
- include intentional billing discrepancies
- keep CSVs small and understandable

---

## What Good Looks Like
Good output should:
- compile or run with minimal fixes
- look like something an engineer could demo to a manager
- reflect industrial workflow thinking
- clearly distinguish raw data, rules, and AI explanation layers

---

## What to Avoid
Avoid:
- over-engineering
- introducing tools not needed for the prototype
- replacing rule logic with LLM logic
- huge monolithic files
- unnecessary async patterns
- premature optimization
- placeholder code that does not actually run

---

## Preferred Build Sequence
When helping with implementation, generally follow this order:

1. define schema for invoices and rate table
2. generate synthetic sample data
3. implement policy engine
4. implement structured audit outputs
5. implement AI explanation function
6. implement Streamlit app
7. add tests
8. improve README

---

## Output Format Preferences
When generating code:
- provide full file contents when practical
- include import statements
- include short comments only where useful
- keep explanations concise

When generating plans:
- use phases
- specify deliverables
- identify dependencies

When generating prompts:
- make them copy-paste ready for Cursor

---

## Repo Awareness
Assume this repository is intended to:
- showcase engineering ability
- demonstrate AI + DataOps understanding
- be reviewed by technical and semi-technical stakeholders

Optimize for credibility, not novelty.

---

## Business Context
This project simulates a freight invoice auditing workflow.

The business value is:
- detecting billing leakage
- enforcing contract compliance
- reducing manual audit work
- making discrepancies explainable

Keep those outcomes visible in naming, comments, and UI text.

---

## If Asked to Refactor
Refactor toward:
- smaller modules
- clearer interfaces
- more explicit rule outputs
- better business readability

Do not refactor merely for style.

---

## Default Assumptions
Unless otherwise specified:
- invoices are CSV-based in v1
- PDFs are conceptually part of the source workflow, but not required for the first working prototype
- pass/fail decisions are rule-based
- AI explanations are generated from structured rule outputs
- the app runs locally with Streamlit