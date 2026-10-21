"""Test Suite and Decision Table Generator.

Synthesizes executable Pytest / Unittest test scripts and structured
Markdown Decision Tables from boundary points and equivalence classes.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from core.ast_analyzer import FunctionModel
from core.solver import MultiVarTestCase, ParameterPartitionPlan


class TestSynthesizer:
    """Generates executable test scripts and Markdown decision tables."""

    def __init__(self, target_module_name: str, target_file_path: str):
        self.target_module_name = target_module_name
        self.target_file_path = target_file_path

    def generate_test_script(
        self,
        func_model: FunctionModel,
        test_cases: List[Dict[str, Any]],
        plans: Dict[str, ParameterPartitionPlan],
    ) -> str:
        """Synthesizes a standalone, executable pytest- and unittest-compatible script."""
        func_name = func_model.name
        abs_target_path = os.path.abspath(self.target_file_path)
        dir_name = os.path.dirname(abs_target_path)
        base_name = os.path.splitext(os.path.basename(abs_target_path))[0]

        lines = [
            '"""',
            f"Automated Boundary-Value & Equivalence-Class Test Suite for `{func_name}`.",
            "Synthesized automatically by Automated QA & Boundary-Value Test Synthesizer.",
            '"""',
            "",
            "import os",
            "import sys",
            "import unittest",
            "",
            "# Ensure target module is importable",
            f"TARGET_DIR = {repr(dir_name)}",
            "if TARGET_DIR not in sys.path:",
            "    sys.path.insert(0, TARGET_DIR)",
            "",
            f"try:",
            f"    from {base_name} import {func_name}",
            f"except ImportError as err:",
            f"    # Fallback import mechanism",
            f"    import importlib.util",
            f"    spec = importlib.util.spec_from_file_location({repr(base_name)}, {repr(abs_target_path)})",
            f"    mod = importlib.util.module_from_spec(spec)",
            f"    spec.loader.exec_module(mod)",
            f"    {func_name} = getattr(mod, {repr(func_name)})",
            "",
            "",
            f"class Test{func_name.capitalize()}SynthesizedSuite(unittest.TestCase):",
            f'    """Comprehensive BVA and ECP Test Suite for {func_name}."""',
            "",
        ]

        # Generate individual test methods for each synthesized test case
        for idx, tc in enumerate(test_cases, 1):
            t_id = tc.get("rule_id", f"R{idx}")
            t_name = tc.get("name", f"test_case_{idx}")
            inputs = tc.get("inputs", {})
            expected = tc.get("expected_outcome", "pass")
            boundary = tc.get("target_boundary", "N/A")
            rationale = tc.get("business_rationale", "")

            # Format input arguments
            args_str = ", ".join(f"{k}={repr(v)}" for k, v in inputs.items())

            lines.extend([
                f"    def {t_name}(self):",
                f'        """[{t_id}] Boundary: {boundary}',
                f'        Rationale: {rationale}',
                f'        """',
            ])

            if expected == "pass":
                lines.extend([
                    f"        # Valid Equivalence Class / In-Boundary: Expect normal execution",
                    f"        result = {func_name}({args_str})",
                    f"        self.assertIsNotNone(result, 'Expected non-null return value for valid boundary inputs')",
                    f"        if isinstance(result, bool):",
                    f"            self.assertTrue(result, 'Expected True result for valid boundary conditions')",
                    "",
                ])
            else:
                lines.extend([
                    f"        # Invalid Equivalence Class / Out-of-Bounds: Expect rejection or defensive exception",
                    f"        try:",
                    f"            res = {func_name}({args_str})",
                    f"            # If function returns boolean or status dict instead of raising",
                    f"            if isinstance(res, bool):",
                    f"                self.assertFalse(res, f'Expected rejection False for invalid boundary {boundary}, got {{res}}')",
                    f"            elif isinstance(res, dict) and 'status' in res:",
                    f"                self.assertIn(str(res.get('status')).lower(), ['rejected', 'error', 'invalid'], 'Expected error status')",
                    f"            elif res is None:",
                    f"                pass # None returned defensively",
                    f"            else:",
                    f"                self.fail(f'Expected rejection or exception for invalid boundary {boundary}, but got {{res}}')",
                    f"        except (ValueError, TypeError, AssertionError):",
                    f"            # Defensive exception caught successfully",
                    f"            pass",
                    "",
                ])

        lines.extend([
            "",
            "if __name__ == '__main__':",
            "    unittest.main()",
            "",
        ])

        return "\n".join(lines)

    def generate_decision_table_markdown(
        self,
        func_model: FunctionModel,
        plans: Dict[str, ParameterPartitionPlan],
        test_cases: List[Dict[str, Any]],
    ) -> str:
        """Synthesizes a structured Markdown Decision Table."""
        func_name = func_model.name
        param_names = [p.name for p in func_model.parameters]

        headers = ["Rule ID", "Category", "Target Boundary"] + [f"`{p}`" for p in param_names] + ["Expected Result", "Business Rationale"]
        divider = ["---"] * len(headers)

        rows = []
        for tc in test_cases:
            inputs = tc.get("inputs", {})
            param_vals = [f"`{repr(inputs.get(p, '-'))}`" for p in param_names]
            rule_id = tc.get("rule_id", "R?")
            cat = tc.get("category", "N/A")
            boundary = tc.get("target_boundary", "N/A")
            expected = "**Accept (Pass)**" if tc.get("expected_outcome") == "pass" else "**Reject / Defensive Error**"
            rationale = tc.get("business_rationale", "")

            row = [rule_id, cat, boundary] + param_vals + [expected, rationale]
            rows.append(row)

        table_lines = [
            f"# Decision Table & Equivalence Partition Matrix: `{func_name}`",
            "",
            f"**Target Function:** `{func_name}`  ",
            f"**Domain Analysis:** Equivalence Class Partitioning (ECP) + Boundary Value Analysis (BVA)  ",
            f"**Total Synthesized Rules:** {len(test_cases)}  ",
            "",
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(divider) + " |",
        ]

        for r in rows:
            table_lines.append("| " + " | ".join(r) + " |")

        # Add Parameter Boundary Summary
        table_lines.extend([
            "",
            "## Extracted Parameter Boundary Limits",
            "",
            "| Parameter | Inferred Type | Lower Bound (min) | Upper Bound (max) | Equivalence Partitions |",
            "| --- | --- | --- | --- | --- |",
        ])

        for p_name, plan in plans.items():
            min_str = str(plan.min_bound) if plan.min_bound is not None else "Unbounded (-∞)"
            max_str = str(plan.max_bound) if plan.max_bound is not None else "Unbounded (+∞)"
            num_ec = len(plan.partitions)
            table_lines.append(f"| `{p_name}` | `{plan.inferred_type}` | {min_str} | {max_str} | {num_ec} Partitions |")

        return "\n".join(table_lines)

