# Automated QA & Boundary-Value Test Synthesizer

> **Domain:** Software Engineering & Quality Assurance (LLM Agents + Static Code Analysis)

---

## 📌 Problem Statement & Why It Is Needed
Manual test case creation—especially for edge cases in **Equivalence Class Partitioning (ECP)** and **Boundary Value Analysis (BVA)**—is tedious and error-prone. Developers frequently miss:
- Off-by-one errors (`<` vs `<=`, `>` vs `>=`)
- Null-state transitions and missing guard assertions
- Complex multi-variable combinatorial boundaries
- Unhandled edge cases leading to production defects and regression bottlenecks

---

## 🏗️ System Architecture Flowchart

```
[Source Code / PR Diff] 
       │
       ▼
[AST & Static Analyzer] ──► Extracts Variables, Types & Branch Conditions
       │
       ▼
[Hybrid AI Engine]
  ├──► [Z3 / Constraint Solver] ──► Calculates Exact BVA & ECP Partitions
  └──► [LLM Agent (RAG)]        ──► Maps Business Logic & Decision Tables
       │
       ▼
[Test Script Synthesizer] ──► Generates Executable Pytest / Unittest Code
       │
       ▼
[Sandbox Test Runner] ──► Passes? ──► [Yes] ──► [Approve PR & Log Coverage]
       │
      [No]
       ▼
[Auto-Generate Defect Log & Alert Developer]
```

---

## ⚡ Core Components

1. **AST Parser & Context Extractor (`core/ast_analyzer.py`)**
   - Built on Python's native `ast` library.
   - Extracts function signatures, type annotations, default arguments, docstrings, and control flow branches (`if`, `elif`, `assert`, `while`).
   - Automatically parses guard clauses, numerical comparisons, string length validations (`len(var)`), and specification contracts from docstrings.

2. **SMT & Boundary-Value Solver (`core/solver.py`)**
   - Exact mathematical 6-point & 7-point Boundary Value Analysis:
     $$\{min - 1, min, min + 1, nominal, max - 1, max, max + 1\}$$
   - Equivalence Class Partitioning (ECP) into Valid Range, Underflow, Overflow, and Null-State Partitions.
   - Exact interval propagation with optional dynamic hook into the `z3-solver` SMT engine.

3. **Hybrid AI & Decision Table Engine (`core/llm_agent.py`)**
   - Maps extracted boundary points into human-readable business logic rules and cause-effect decision tables.
   - Generates actionable root-cause diagnoses and code patch recommendations when boundary defects are encountered.
   - Supports Gemini API / fine-tuned local models with high-fidelity zero-dependency heuristic fallback.

4. **Test Suite & Decision Table Generator (`core/test_synthesizer.py`)**
   - Outputs standalone executable test suites compatible with both `pytest` and Python's built-in `unittest`.
   - Generates structured Markdown Decision Tables detailing rule IDs ($R_1, R_2, \dots$), condition stubs, action stubs, and expected outcomes.

5. **Sandbox Test Runner & Defect Logger (`core/sandbox_runner.py`)**
   - Runs synthesized test suites inside an isolated subprocess.
   - Evaluates test outcomes:
     - **Pass:** Emits a QA Audit & Compliance Report approving the Pull Request.
     - **Fail:** Analyzes failure traces, pinpoints off-by-one errors, and generates an actionable `DEFECT_LOG.md` blocking the PR.

6. **CI/CD Hook Integration (`.github/workflows/qa_synthesizer.yml`)**
   - Pre-configured GitHub Actions workflow triggered on pull requests and pushes to audit boundary conditions and prevent off-by-one bugs from landing in production.

---

## 🚀 Quick Start & Usage

### 1. Run the End-to-End Pipeline
```bash
# Run benchmark demonstration on loan approval module (contains intentional off-by-one boundary bug)
python Main.py pipeline examples/loan_approval.py

# Run on discount calculator (100% compliant boundary target)
python Main.py pipeline examples/discount_calculator.py

# Run on multi-variable user validator (string lengths & age bounds)
python Main.py pipeline examples/user_validator.py
```

### 2. Inspect Extracted AST Constraints
```bash
python Main.py scan examples/loan_approval.py
```

### 3. Compute BVA & ECP Partitions
```bash
python Main.py solve examples/loan_approval.py
```

### 4. Run Synthesizer Framework Unit Tests
```bash
python -m unittest tests/test_framework.py
```

---

## 📁 Project Structure

```
├── Main.py                              # CLI & Pipeline Orchestrator
├── README.md                            # System Architecture & Documentation
├── requirements.txt                     # Optional dependencies (z3-solver, pytest)
├── core/
│   ├── __init__.py
│   ├── ast_analyzer.py                  # AST static analysis & spec extractor
│   ├── solver.py                        # SMT & exact BVA/ECP interval solver
│   ├── llm_agent.py                     # Hybrid AI decision table mapper & defect diagnoser
│   ├── test_synthesizer.py              # Test script & Markdown decision table generator
│   └── sandbox_runner.py                # Isolated subprocess test runner & PR gatekeeper
├── examples/
│   ├── loan_approval.py                 # Target with off-by-one boundary defect
│   ├── discount_calculator.py           # Multi-branch tiered pricing target
│   └── user_validator.py                # String length & multi-variable target
├── tests/
│   └── test_framework.py                # Framework test suite
└── .github/
    └── workflows/
        └── qa_synthesizer.yml           # GitHub Actions CI/CD workflow
```
