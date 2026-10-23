"""FastAPI REST API Server for Automated QA & Boundary-Value Test Synthesizer.

Provides endpoints:
- POST /api/scan: Static AST analysis & constraint extraction
- POST /api/solve: Exact SMT / BVA & ECP calculation
- POST /api/synthesize: Test script & Decision Table generator
- POST /api/audit: Sandbox test runner & defect logger
- GET /api/examples: Built-in target benchmarks
"""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.ast_analyzer import ASTContextExtractor, FunctionModel
from core.llm_agent import LLMAgentEngine
from core.sandbox_runner import SandboxTestRunner
from core.solver import BoundarySolver
from core.test_synthesizer import TestSynthesizer

app = FastAPI(
    title="Automated QA & Boundary-Value Test Synthesizer API",
    description="REST API for static AST parsing, exact BVA/ECP solving, test synthesis, and sandbox auditing.",
    version="1.0.0",
)

# Enable CORS for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
EXAMPLES_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "examples"))

# Mount static assets
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class CodeRequest(BaseModel):
    code: str
    function_name: Optional[str] = None
    module_name: Optional[str] = "target_module"


def _parse_and_get_target_func(code: str, function_name: Optional[str] = None) -> FunctionModel:
    try:
        extractor = ASTContextExtractor(code)
        funcs = extractor.parse()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"AST Syntax Parse Error: {str(e)}")

    if not funcs:
        raise HTTPException(status_code=400, detail="No Python function definitions found in provided code.")

    if function_name:
        matched = next((f for f in funcs if f.name == function_name), None)
        if not matched:
            raise HTTPException(status_code=404, detail=f"Function '{function_name}' not found.")
        return matched

    return funcs[0]


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>Automated QA & Boundary-Value Test Synthesizer API is Running</h1>")


@app.get("/api/examples")
def list_examples() -> List[Dict[str, Any]]:
    """Returns benchmark code examples."""
    examples = []
    if os.path.exists(EXAMPLES_DIR):
        for fname in sorted(os.listdir(EXAMPLES_DIR)):
            if fname.endswith(".py") and not fname.startswith("__"):
                fpath = os.path.join(EXAMPLES_DIR, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()

                desc = "Benchmark Target"
                if "loan_approval" in fname:
                    desc = "Loan Eligibility (Numerical bounds & off-by-one check)"
                elif "discount" in fname:
                    desc = "Tiered Discount Calculator (Multi-variable conditionals)"
                elif "user_validator" in fname:
                    desc = "User Registration (String length bounds & null assertions)"

                examples.append({
                    "id": fname.replace(".py", ""),
                    "filename": fname,
                    "title": fname.replace("_", " ").replace(".py", "").title(),
                    "description": desc,
                    "code": content,
                })
    return examples


@app.post("/api/scan")
def scan_ast(req: CodeRequest) -> Dict[str, Any]:
    """Phase 1: Scans source code and extracts AST functions, parameters, and branching constraints."""
    target_func = _parse_and_get_target_func(req.code, req.function_name)

    return {
        "function_name": target_func.name,
        "line_start": target_func.line_start,
        "line_end": target_func.line_end,
        "return_type": target_func.return_type,
        "docstring": target_func.docstring,
        "parameters": [
            {
                "name": p.name,
                "type": p.type_name,
                "has_default": p.has_default,
                "default_value": p.default_value,
            }
            for p in target_func.parameters
        ],
        "constraints": [
            {
                "variable": c.variable,
                "operator": c.operator,
                "target_value": c.target_value,
                "is_len": c.is_len,
                "is_guard": c.is_guard,
                "raw_expr": c.raw_expr,
                "line_number": c.line_number,
                "enclosing_block": c.enclosing_block,
            }
            for c in target_func.constraints
        ],
        "spec_constraints": [
            {
                "variable": c.variable,
                "operator": c.operator,
                "target_value": c.target_value,
            }
            for c in target_func.spec_constraints
        ],
    }


@app.post("/api/solve")
def solve_bounds(req: CodeRequest) -> Dict[str, Any]:
    """Phase 2: Computes exact Boundary Value Analysis (BVA) and Equivalence Class Partitioning (ECP)."""
    target_func = _parse_and_get_target_func(req.code, req.function_name)
    solver = BoundarySolver()
    plans = solver.solve_function(target_func)

    serialized_plans = {}
    for p_name, plan in plans.items():
        serialized_plans[p_name] = {
            "param_name": plan.param_name,
            "inferred_type": plan.inferred_type,
            "min_bound": plan.min_bound,
            "max_bound": plan.max_bound,
            "discrete_values": plan.discrete_values,
            "boundary_values": [
                {
                    "category": b.category,
                    "value": b.value,
                    "is_valid": b.is_valid,
                    "description": b.description,
                }
                for b in plan.boundary_values
            ],
            "partitions": [
                {
                    "name": p.name,
                    "partition_type": p.partition_type,
                    "description": p.description,
                    "representative_value": p.representative_value,
                }
                for p in plan.partitions
            ],
        }

    return {
        "function_name": target_func.name,
        "plans": serialized_plans,
    }


@app.post("/api/synthesize")
def synthesize_suite(req: CodeRequest) -> Dict[str, Any]:
    """Phase 3 & 4: Generates executable test suite and structured Markdown Decision Table."""
    target_func = _parse_and_get_target_func(req.code, req.function_name)
    solver = BoundarySolver()
    plans = solver.solve_function(target_func)
    raw_cases = solver.generate_decision_table_cases(target_func, plans)

    llm_engine = LLMAgentEngine()
    enriched_cases = llm_engine.enrich_decision_table(target_func, plans, raw_cases)

    synthesizer = TestSynthesizer(
        target_module_name=req.module_name or "target_module",
        target_file_path=f"{req.module_name or 'target_module'}.py",
    )
    test_script = synthesizer.generate_test_script(target_func, enriched_cases, plans)
    decision_table_md = synthesizer.generate_decision_table_markdown(target_func, plans, enriched_cases)

    return {
        "function_name": target_func.name,
        "total_rules": len(enriched_cases),
        "test_script": test_script,
        "decision_table_md": decision_table_md,
        "decision_rules": enriched_cases,
    }


@app.post("/api/audit")
def audit_sandbox(req: CodeRequest) -> Dict[str, Any]:
    """Phase 5: Executes synthesized tests in an isolated sandbox subprocess and logs defects."""
    target_func = _parse_and_get_target_func(req.code, req.function_name)
    solver = BoundarySolver()
    plans = solver.solve_function(target_func)
    raw_cases = solver.generate_decision_table_cases(target_func, plans)

    llm_engine = LLMAgentEngine()
    enriched_cases = llm_engine.enrich_decision_table(target_func, plans, raw_cases)

    # Execute in temporary sandbox directory
    temp_dir = tempfile.mkdtemp(prefix="qa_sandbox_")
    try:
        module_file = os.path.join(temp_dir, f"{target_func.name}_mod.py")
        with open(module_file, "w", encoding="utf-8") as f:
            f.write(req.code)

        synthesizer = TestSynthesizer(
            target_module_name=f"{target_func.name}_mod",
            target_file_path=module_file,
        )
        test_code = synthesizer.generate_test_script(target_func, enriched_cases, plans)
        test_file = os.path.join(temp_dir, f"test_{target_func.name}_bva.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(test_code)

        runner = SandboxTestRunner(llm_engine=llm_engine)
        summary = runner.run_tests(
            test_file_path=test_file,
            func_model=target_func,
            test_case_metadata=enriched_cases,
        )
        defect_log_md = runner.generate_defect_log_markdown(target_func, summary)

        return {
            "function_name": target_func.name,
            "is_approved": summary.is_approved,
            "total_tests": summary.total,
            "passed_tests": summary.passed,
            "failed_tests": summary.failed,
            "duration_sec": summary.duration_sec,
            "failure_details": summary.failure_details,
            "defect_log_md": defect_log_md,
            "raw_output": summary.raw_output,
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
