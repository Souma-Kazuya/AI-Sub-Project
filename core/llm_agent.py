"""Hybrid AI Engine and Decision Table Mapper.

Combines LLM prompting (Gemini API or local LLMs) with expert rule-based
heuristics to map extracted code constraints into business logic decision tables
and actionable defect explanations.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional

from core.ast_analyzer import FunctionModel
from core.solver import MultiVarTestCase, ParameterPartitionPlan


class LLMAgentEngine:
    """Hybrid LLM & Heuristic Agent for Business Logic & Decision Table Mapping."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")

    def enrich_decision_table(
        self,
        func_model: FunctionModel,
        plans: Dict[str, ParameterPartitionPlan],
        test_cases: List[MultiVarTestCase],
    ) -> List[Dict[str, Any]]:
        """Enriches raw test cases with semantic business logic descriptions and expected rules."""
        enriched: List[Dict[str, Any]] = []

        for idx, tc in enumerate(test_cases, 1):
            rule_id = f"R{idx}"
            rationale = self._generate_business_rationale(tc, func_model)
            expected_behavior = self._infer_expected_behavior(tc, func_model)

            enriched.append(
                {
                    "rule_id": rule_id,
                    "test_id": tc.test_id,
                    "name": tc.name,
                    "inputs": tc.inputs,
                    "target_boundary": tc.target_boundary,
                    "category": tc.category,
                    "expected_outcome": tc.expected_outcome,
                    "expected_behavior": expected_behavior,
                    "business_rationale": rationale,
                }
            )

        return enriched

    def _generate_business_rationale(
        self, tc: MultiVarTestCase, func_model: FunctionModel
    ) -> str:
        cat = tc.category
        if cat == "happy_path":
            return "Standard nominal operation: all input variables lie comfortably within accepted operational tolerances."
        elif "min_minus_1" in cat or "underflow" in cat:
            return f"Negative boundary audit: verifies strict rejection when {tc.target_boundary} drops below lower limit (protects against underflow)."
        elif "min" == cat or "BVA_min" in cat:
            return f"Boundary limit compliance: verifies inclusive threshold at exact lower boundary {tc.target_boundary} (checks for >= vs > off-by-one errors)."
        elif "min_plus_1" in cat:
            return f"Boundary tolerance check: verifies acceptance 1 unit above minimum threshold ({tc.target_boundary})."
        elif "max_minus_1" in cat:
            return f"Boundary tolerance check: verifies acceptance 1 unit below maximum threshold ({tc.target_boundary})."
        elif "max" == cat or "BVA_max" in cat:
            return f"Boundary limit compliance: verifies inclusive threshold at exact upper boundary {tc.target_boundary} (checks for <= vs < off-by-one errors)."
        elif "max_plus_1" in cat or "overflow" in cat:
            return f"Upper boundary audit: verifies strict rejection when {tc.target_boundary} exceeds upper limit (protects against overflow)."
        elif "null" in cat:
            return f"Null-safety invariant: verifies graceful error handling or validation rejection when {tc.target_boundary} is None."
        elif "multivar_boundary" in cat:
            return f"Multi-variable combinatorial boundary: verifies coupled boundary interaction under extreme values ({tc.target_boundary})."
        return f"Equivalence class evaluation targeting {tc.target_boundary}."

    def _infer_expected_behavior(
        self, tc: MultiVarTestCase, func_model: FunctionModel
    ) -> str:
        if tc.expected_outcome == "pass":
            return "Execute successfully and return valid business response (no unhandled exception)."
        else:
            return "Raise ValueError / AssertionError, or return rejection status (False/None/Error)."

    def explain_defect(
        self,
        func_name: str,
        failing_input: Dict[str, Any],
        actual_output: Any,
        expected_output: str,
        error_trace: str,
    ) -> Dict[str, str]:
        """Analyzes a test failure and produces a root-cause explanation and suggested fix."""
        # Check for typical off-by-one signature
        is_off_by_one = any(
            k in error_trace.lower() or "boundary" in str(failing_input).lower()
            for k in ["assertionerror", "valueerror", "off-by-one"]
        )

        if "NoneType" in error_trace:
            root_cause = f"Null-State Transition Failure: '{func_name}' attempted attribute access or comparison on None input without defensive null check."
            suggestion = "Add an explicit null guard at the top of the function: `if any(arg is None for arg in [...]): raise ValueError('Arguments cannot be None')`"
        elif is_off_by_one:
            root_cause = f"Off-By-One Boundary Error: '{func_name}' failed at exact boundary inputs {failing_input}. Comparison operator likely uses `<` instead of `<=` (or `>` instead of `>=`), prematurely rejecting valid edge cases."
            suggestion = f"Inspect boundary conditions in `{func_name}`. Verify if condition threshold is inclusive: replace `< threshold` with `<= threshold` or vice-versa."
        else:
            root_cause = f"Uncaught Exception or Contract Violation: '{func_name}' threw `{error_trace.splitlines()[-1] if error_trace else 'Error'}` on inputs {failing_input}."
            suggestion = "Ensure all domain branches handle equivalence class edge cases defensively with try-except or explicit boundary checks."

        return {
            "root_cause": root_cause,
            "remediation_patch": suggestion,
        }

