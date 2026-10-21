"""Sandbox Test Runner and Automated Defect Logger.

Executes synthesized test suites in an isolated subprocess, captures failures,
diagnoses boundary violations and off-by-one errors, and generates PR compliance
reports and Defect Logs.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.ast_analyzer import FunctionModel
from core.llm_agent import LLMAgentEngine


@dataclass
class TestResultSummary:
    """Summary of sandbox test execution."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    duration_sec: float = 0.0
    failure_details: List[Dict[str, Any]] = field(default_factory=list)
    raw_output: str = ""
    is_approved: bool = False


class SandboxTestRunner:
    """Executes synthesized test scripts in an isolated sandbox subprocess."""

    def __init__(self, llm_engine: Optional[LLMAgentEngine] = None):
        self.llm_engine = llm_engine or LLMAgentEngine()

    def run_tests(
        self,
        test_file_path: str,
        func_model: FunctionModel,
        test_case_metadata: List[Dict[str, Any]],
        timeout_sec: int = 30,
    ) -> TestResultSummary:
        """Executes the test file using unittest in a clean subprocess."""
        start_time = time.time()
        abs_path = os.path.abspath(test_file_path)

        cmd = [sys.executable, abs_path]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
            raw_output = proc.stdout + "\n" + proc.stderr
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            return TestResultSummary(
                total=len(test_case_metadata),
                failed=1,
                raw_output=f"Execution timed out after {timeout_sec}s",
                is_approved=False,
            )

        duration = time.time() - start_time
        summary = self._parse_unittest_output(raw_output, test_case_metadata, func_model)
        summary.duration_sec = round(duration, 3)
        summary.raw_output = raw_output
        summary.is_approved = (summary.failed == 0 and summary.errors == 0 and summary.passed > 0)

        return summary

    def _parse_unittest_output(
        self,
        output: str,
        test_case_metadata: List[Dict[str, Any]],
        func_model: FunctionModel,
    ) -> TestResultSummary:
        meta_by_name = {tc["name"]: tc for tc in test_case_metadata}

        # Count ran tests
        match_ran = re.search(r"Ran (\d+) tests? in", output)
        total_ran = int(match_ran.group(1)) if match_ran else len(test_case_metadata)

        failures = []
        # Split on test failure delimiters in unittest
        fail_blocks = re.split(r"={5,}\s*\n(?:FAIL|ERROR):\s*", output)

        for block in fail_blocks[1:]:
            lines = block.splitlines()
            if not lines:
                continue

            first_line = lines[0].strip()
            # E.g. test_bva_score_min (test_synthesized.TestLoanApprovalSynthesizedSuite.test_bva_score_min)
            test_func_match = re.search(r"(test_\w+)", first_line)
            test_name = test_func_match.group(1) if test_func_match else "unknown_test"

            tc_meta = meta_by_name.get(test_func_match.group(1), {}) if test_func_match else {}
            inputs = tc_meta.get("inputs", {})
            boundary = tc_meta.get("target_boundary", "boundary")

            # Extract error trace
            trace = "\n".join(lines[1:])
            diag = self.llm_engine.explain_defect(
                func_name=func_model.name,
                failing_input=inputs,
                actual_output="Failed / AssertionError",
                expected_output=tc_meta.get("expected_behavior", "Pass or Defensive Error"),
                error_trace=trace,
            )

            failures.append(
                {
                    "test_name": test_name,
                    "rule_id": tc_meta.get("rule_id", "R-Unknown"),
                    "boundary": boundary,
                    "inputs": inputs,
                    "trace": trace.strip()[:600],
                    "root_cause": diag["root_cause"],
                    "remediation": diag["remediation_patch"],
                }
            )

        failed_count = len(failures)
        passed_count = max(0, total_ran - failed_count)

        return TestResultSummary(
            total=total_ran,
            passed=passed_count,
            failed=failed_count,
            errors=0,
            failure_details=failures,
        )

    def generate_defect_log_markdown(
        self,
        func_model: FunctionModel,
        summary: TestResultSummary,
    ) -> str:
        """Generates a structured DEFECT_LOG.md for CI/CD and developer alerting."""
        if summary.is_approved:
            return (
                f"# QA Audit & Compliance Report: `{func_model.name}`\n\n"
                f"**Status:** ✅ **APPROVED (100% Boundary & ECP Pass Rate)**  \n"
                f"- **Tests Evaluated:** {summary.total}\n"
                f"- **Tests Passed:** {summary.passed}\n"
                f"- **Defects Found:** 0\n"
                f"- **Execution Time:** {summary.duration_sec}s\n\n"
                f"All equivalence classes and boundary limits verified successfully against the static specification."
            )

        lines = [
            f"# Automated Defect Log: `{func_model.name}`",
            "",
            "**Status:** ❌ **PR BLOCKED — Boundary Defects Detected**  ",
            f"**Total Synthesized Tests:** {summary.total}  ",
            f"**Passed:** {summary.passed}  ",
            f"**Failed / Regressions:** {summary.failed}  ",
            f"**Audit Execution Time:** {summary.duration_sec}s  ",
            "",
            "---",
            "",
            "## Detected Boundary & Equivalence Class Failures",
            "",
        ]

        for idx, fail in enumerate(summary.failure_details, 1):
            lines.extend([
                f"### Defect #{idx}: [{fail.get('rule_id')}] Boundary Violation in `{fail.get('boundary')}`",
                "",
                f"- **Failed Test Method:** `{fail.get('test_name')}`",
                f"- **Offending Input Combination:** `{json.dumps(fail.get('inputs'))}`",
                f"- **Severity:** **HIGH** (Boundary off-by-one or unhandled state)",
                "",
                "#### AI Diagnostic & Root Cause Analysis",
                f"> {fail.get('root_cause')}",
                "",
                "#### Suggested Remediation Patch",
                f"> 💡 **Actionable Fix:** {fail.get('remediation')}",
                "",
                "#### Subprocess Stack Trace",
                "```text",
                fail.get("trace", "No stack trace available"),
                "```",
                "",
                "---",
                "",
            ])

        lines.extend([
            "## Recommended Developer Action Plan",
            "1. Review the condition operators on the indicated line numbers.",
            "2. Ensure boundary thresholds (`<`, `<=`, `>`, `>=`) correctly mirror the business requirements.",
            "3. Re-run `python Main.py run <file>` to verify regression resolution.",
            "",
        ])

        return "\n".join(lines)
