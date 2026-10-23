#!/usr/bin/env python3
"""Automated QA & Boundary-Value Test Synthesizer.

Domain: Software Engineering & Quality Assurance (LLM Agents + Static Code Analysis)
Combines Python AST parsing, exact SMT/Interval Boundary-Value Analysis (BVA),
Equivalence Class Partitioning (ECP), and LLM-guided decision table generation
to automatically synthesize and execute test suites, detect off-by-one errors,
and output structured Defect Logs.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from core.ast_analyzer import extract_file_context
from core.llm_agent import LLMAgentEngine
from core.sandbox_runner import SandboxTestRunner
from core.solver import BoundarySolver
from core.test_synthesizer import TestSynthesizer


def print_banner() -> None:
    banner = r"""
================================================================================
   AUTOMATED QA & BOUNDARY-VALUE TEST SYNTHESIZER
   Static AST Analysis • SMT/BVA Solver • Decision Tables • Defect Logger
================================================================================
    """
    print(banner)


def run_pipeline(
    filepath: str,
    output_dir: str = "synthesized_output",
    function_name: Optional[str] = None,
) -> int:
    """Executes the full end-to-end synthesizer pipeline on the target file."""
    print_banner()
    os.makedirs(output_dir, exist_ok=True)
    abs_path = os.path.abspath(filepath)
    print(f"[*] Target Source File: {abs_path}")

    # Step 1: AST & Static Code Analysis
    print("\n[Phase 1] AST Parser & Context Extractor...")
    func_models = extract_file_context(abs_path)
    if not func_models:
        print(f"[!] Error: No functions discovered in {filepath}")
        return 1

    target_func = None
    if function_name:
        target_func = next((f for f in func_models if f.name == function_name), None)
        if not target_func:
            print(f"[!] Error: Function '{function_name}' not found in {filepath}")
            return 1
    else:
        target_func = func_models[0]

    print(f"    ✔ Target Function: `{target_func.name}` (lines {target_func.line_start}-{target_func.line_end})")
    print(f"    ✔ Extracted Parameters ({len(target_func.parameters)}): {[p.name + ': ' + p.type_name for p in target_func.parameters]}")
    print(f"    ✔ Extracted Branch Constraints ({len(target_func.constraints)}):")
    for c in target_func.constraints:
        print(f"        • {c.variable} {c.operator} {c.target_value} (expr: `{c.raw_expr}` at line {c.line_number})")

    # Step 2: SMT / Boundary-Value & Equivalence-Class Solver
    print("\n[Phase 2] Constraint Solver & Partition Engine...")
    solver = BoundarySolver()
    param_plans = solver.solve_function(target_func)
    raw_cases = solver.generate_decision_table_cases(target_func, param_plans)

    for p_name, plan in param_plans.items():
        print(f"    ✔ Parameter `{p_name}`:")
        print(f"        - Inferred Type: {plan.inferred_type}")
        print(f"        - Bounds: [{plan.min_bound}, {plan.max_bound}]")
        print(f"        - Boundary Values ({len(plan.boundary_values)} points): {[f'{b.category}={b.value}' for b in plan.boundary_values]}")
        print(f"        - Equivalence Partitions ({len(plan.partitions)} classes): {[p.name for p in plan.partitions]}")

    # Step 3: Hybrid AI & Decision Table Engine
    print("\n[Phase 3] Hybrid AI & Business Logic Engine...")
    llm_engine = LLMAgentEngine()
    enriched_cases = llm_engine.enrich_decision_table(target_func, param_plans, raw_cases)
    print(f"    ✔ Mapped {len(enriched_cases)} Decision Rules with semantic rationales.")

    # Step 4: Test Script & Decision Table Synthesis
    print("\n[Phase 4] Test Script & Decision Table Generator...")
    synthesizer = TestSynthesizer(
        target_module_name=os.path.basename(abs_path),
        target_file_path=abs_path,
    )
    test_code = synthesizer.generate_test_script(target_func, enriched_cases, param_plans)
    decision_table_md = synthesizer.generate_decision_table_markdown(target_func, param_plans, enriched_cases)

    test_file_path = os.path.join(output_dir, f"test_{target_func.name}_bva.py")
    decision_table_path = os.path.join(output_dir, f"DECISION_TABLE_{target_func.name}.md")

    with open(test_file_path, "w", encoding="utf-8") as f:
        f.write(test_code)
    with open(decision_table_path, "w", encoding="utf-8") as f:
        f.write(decision_table_md)

    print(f"    ✔ Executable Test Suite generated: {test_file_path}")
    print(f"    ✔ Structured Decision Table saved: {decision_table_path}")

    # Step 5: Sandbox Test Runner & Defect Logger
    print("\n[Phase 5] Isolated Sandbox Test Execution...")
    runner = SandboxTestRunner(llm_engine=llm_engine)
    summary = runner.run_tests(
        test_file_path=test_file_path,
        func_model=target_func,
        test_case_metadata=enriched_cases,
    )

    defect_log_md = runner.generate_defect_log_markdown(target_func, summary)
    defect_log_path = os.path.join(output_dir, f"DEFECT_LOG_{target_func.name}.md")
    with open(defect_log_path, "w", encoding="utf-8") as f:
        f.write(defect_log_md)

    print(f"\n====================== EXECUTION SUMMARY ======================")
    print(f" Total Tests Ran    : {summary.total}")
    print(f" Passed             : {summary.passed} ✅")
    print(f" Failed/Regressions : {summary.failed} ❌")
    print(f" Duration           : {summary.duration_sec}s")

    if summary.is_approved:
        print("\n[RESULT] PR AUDIT STATUS: ✅ APPROVED")
        print(f"         All boundary cases and equivalence partitions passed successfully.")
        print(f"         Compliance Report: {defect_log_path}")
        return 0
    else:
        print("\n[RESULT] PR AUDIT STATUS: ❌ DEFECTS DETECTED — PR BLOCKED!")
        print(f"         Automated Defect Log generated: {defect_log_path}")
        print(f"\n--- Top Defect Preview ---")
        if summary.failure_details:
            top_bug = summary.failure_details[0]
            print(f" * Rule: {top_bug.get('rule_id')} | Target: {top_bug.get('boundary')}")
            print(f" * Offending Inputs: {top_bug.get('inputs')}")
            print(f" * AI Root Cause: {top_bug.get('root_cause')}")
            print(f" * Actionable Fix: {top_bug.get('remediation')}")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automated QA & Boundary-Value Test Synthesizer (LLM Agents + Static Code Analysis)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # Command: pipeline
    pipe_parser = subparsers.add_parser("pipeline", help="Run end-to-end synthesizer pipeline")
    pipe_parser.add_argument("file", help="Path to Python target file")
    pipe_parser.add_argument("-f", "--function", help="Target function name (optional)")
    pipe_parser.add_argument("-o", "--output-dir", default="synthesized_output", help="Directory for output artifacts")

    # Command: scan
    scan_parser = subparsers.add_parser("scan", help="Scan source file and extract AST constraints")
    scan_parser.add_argument("file", help="Path to Python source file")

    # Command: solve
    solve_parser = subparsers.add_parser("solve", help="Compute BVA and ECP bounds")
    solve_parser.add_argument("file", help="Path to Python source file")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Run already synthesized tests")
    run_parser.add_argument("test_file", help="Path to test script")

    # Command: serve
    serve_parser = subparsers.add_parser("serve", help="Launch interactive FastAPI Web Dashboard")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable live auto-reload")

    args = parser.parse_args()

    if not args.command:
        # Default interactive demonstration on sample
        sample_path = os.path.join(os.path.dirname(__file__), "examples", "loan_approval.py")
        print("[*] No subcommand specified. Running benchmark demonstration on `examples/loan_approval.py`...\n")
        exit_code = run_pipeline(sample_path)
        sys.exit(exit_code)

    if args.command == "pipeline":
        exit_code = run_pipeline(args.file, args.output_dir, args.function)
        sys.exit(exit_code)

    elif args.command == "scan":
        func_models = extract_file_context(args.file)
        print(f"[*] Discovered {len(func_models)} functions in {args.file}:")
        for f in func_models:
            print(f"\nFunction: {f.name} (lines {f.line_start}-{f.line_end})")
            print(f"  Params: {[p.name + ': ' + p.type_name for p in f.parameters]}")
            print(f"  Constraints: {len(f.constraints)}")
            for c in f.constraints:
                print(f"    - {c.variable} {c.operator} {c.target_value} (`{c.raw_expr}`)")

    elif args.command == "solve":
        func_models = extract_file_context(args.file)
        solver = BoundarySolver()
        for f in func_models:
            print(f"\n=== Boundary Solutions for `{f.name}` ===")
            plans = solver.solve_function(f)
            for p_name, plan in plans.items():
                print(f"\nParameter `{p_name}` ({plan.inferred_type}):")
                print(f"  Bounds: [{plan.min_bound}, {plan.max_bound}]")
                print("  BVA Points:")
                for b in plan.boundary_values:
                    print(f"    - {b.category:12s}: {repr(b.value)} ({'Valid' if b.is_valid else 'Invalid'}) -> {b.description}")

    elif args.command == "run":
        cmd = [sys.executable, "-m", "unittest", args.test_file]
        res = os.system(" ".join(cmd))
        sys.exit(0 if res == 0 else 1)

    elif args.command == "serve":
        try:
            import uvicorn
        except ImportError:
            print("[!] Uvicorn not installed in current interpreter. Checking .venv...")
            venv_python = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python")
            if os.path.exists(venv_python):
                cmd = [venv_python, "-m", "uvicorn", "app.server:app", "--host", args.host, "--port", str(args.port)]
                if args.reload:
                    cmd.append("--reload")
                os.execv(venv_python, cmd)
            else:
                print("[!] Error: FastAPI and Uvicorn are required. Please run: pip install -r requirements.txt")
                sys.exit(1)

        print(f"\n🚀 Launching QA Synthesizer Web Dashboard at http://{args.host}:{args.port}")
        uvicorn.run("app.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
