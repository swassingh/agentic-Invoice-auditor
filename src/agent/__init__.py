"""
Agent layer: LLM-based explanation of deterministic audit findings.

This package must never be used to compute pass/fail decisions. It only
explains the structured outputs from the policy engine.
"""

from .explainer import explain_batch, explain_findings

__all__ = ["explain_findings", "explain_batch"]

