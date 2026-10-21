"""Unit Test Suite for QA Synthesizer Framework Itself.

Verifies AST extraction, BVA calculations, Decision Table synthesis,
and sandbox test execution.
"""

import os
import unittest

from core.ast_analyzer import ASTContextExtractor, extract_file_context
from core.llm_agent import LLMAgentEngine
from core.sandbox_runner import SandboxTestRunner
from core.solver import BoundarySolver
from core.test_synthesizer import TestSynthesizer


class TestSynthesizerFramework(unittest.TestCase):
    """Test suite validating the synthesizer components."""

    def test_ast_extractor_numerical_and_guards(self):
        sample_code = """
def sample_func(x: int, y: float) -> bool:
    '''Spec: 10 <= x <= 50'''
    if x < 10 or x > 50:
        return False
    if y <= 0.0:
        raise ValueError("y must be positive")
    return True
"""
        extractor = ASTContextExtractor(sample_code)
        funcs = extractor.parse()
        self.assertEqual(len(funcs), 1)
        fn = funcs[0]
        self.assertEqual(fn.name, "sample_func")
        self.assertEqual(len(fn.parameters), 2)
        self.assertEqual(fn.parameters[0].name, "x")
        self.assertEqual(fn.parameters[0].type_name, "int")
        self.assertGreaterEqual(len(fn.constraints), 2)

    def test_solver_bva_calculation(self):
        sample_code = """
def sample_age(age: int) -> bool:
    if age < 18 or age > 65:
        return False
    return True
"""
        extractor = ASTContextExtractor(sample_code)
        fn = extractor.parse()[0]
        solver = BoundarySolver()
        plans = solver.solve_function(fn)
        age_plan = plans["age"]

        self.assertEqual(age_plan.min_bound, 18)
        self.assertEqual(age_plan.max_bound, 65)

        categories = {b.category: b.value for b in age_plan.boundary_values}
        self.assertEqual(categories["min - 1"], 17)
        self.assertEqual(categories["min"], 18)
        self.assertEqual(categories["min + 1"], 19)
        self.assertEqual(categories["max - 1"], 64)
        self.assertEqual(categories["max"], 65)
        self.assertEqual(categories["max + 1"], 66)

    def test_decision_table_generation(self):
        sample_code = """
def sample_check(score: int) -> bool:
    if score < 50:
        return False
    return True
"""
        extractor = ASTContextExtractor(sample_code)
        fn = extractor.parse()[0]
        solver = BoundarySolver()
        plans = solver.solve_function(fn)
        cases = solver.generate_decision_table_cases(fn, plans)

        llm = LLMAgentEngine()
        enriched = llm.enrich_decision_table(fn, plans, cases)
        self.assertGreater(len(enriched), 0)

        synthesizer = TestSynthesizer("dummy", "dummy.py")
        md = synthesizer.generate_decision_table_markdown(fn, plans, enriched)
        self.assertIn("# Decision Table & Equivalence Partition Matrix", md)
        self.assertIn("score", md)

    def test_string_len_partitions(self):
        sample_code = """
def sample_pwd(password: str) -> bool:
    if len(password) < 8 or len(password) > 16:
        return False
    return True
"""
        extractor = ASTContextExtractor(sample_code)
        fn = extractor.parse()[0]
        solver = BoundarySolver()
        plans = solver.solve_function(fn)
        plan = plans["password"]

        self.assertEqual(plan.inferred_type, "str_len")
        self.assertEqual(plan.min_bound, 8)
        self.assertEqual(plan.max_bound, 16)


if __name__ == "__main__":
    unittest.main()

