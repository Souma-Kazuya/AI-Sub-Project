"""Unit and Integration Tests for FastAPI REST Endpoints."""

import unittest

from app.server import (
    CodeRequest,
    audit_sandbox,
    list_examples,
    scan_ast,
    solve_bounds,
    synthesize_suite,
)


class TestFastAPIRoutes(unittest.TestCase):
    """Verifies all REST API route handlers."""

    def setUp(self):
        self.sample_code = """
def check_score(score: int) -> bool:
    '''Score must be between 50 and 100'''
    if score < 50 or score > 100:
        return False
    return True
"""

    def test_examples_endpoint(self):
        examples = list_examples()
        self.assertIsInstance(examples, list)
        self.assertGreater(len(examples), 0)

    def test_scan_endpoint(self):
        req = CodeRequest(code=self.sample_code)
        data = scan_ast(req)
        self.assertEqual(data["function_name"], "check_score")
        self.assertEqual(len(data["parameters"]), 1)
        self.assertEqual(data["parameters"][0]["name"], "score")

    def test_solve_endpoint(self):
        req = CodeRequest(code=self.sample_code)
        data = solve_bounds(req)
        self.assertIn("score", data["plans"])
        score_plan = data["plans"]["score"]
        self.assertEqual(score_plan["min_bound"], 50)
        self.assertEqual(score_plan["max_bound"], 100)

    def test_synthesize_endpoint(self):
        req = CodeRequest(code=self.sample_code)
        data = synthesize_suite(req)
        self.assertIn("test_script", data)
        self.assertIn("decision_table_md", data)
        self.assertGreater(data["total_rules"], 0)

    def test_audit_endpoint(self):
        req = CodeRequest(code=self.sample_code)
        data = audit_sandbox(req)
        self.assertTrue(data["is_approved"])
        self.assertEqual(data["failed_tests"], 0)


if __name__ == "__main__":
    unittest.main()

