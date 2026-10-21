"""AST Parser and Context Extractor for Automated QA & BVA Synthesizer.

Extracts function signatures, type hints, branching logic, validation constraints,
and comparison operators from Python source code AST.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ParameterInfo:
    """Information about a function parameter."""
    name: str
    type_name: str = "Any"
    default_value: Any = None
    has_default: bool = False


@dataclass
class ConstraintInfo:
    """Represents a branching or validation constraint."""
    variable: str
    operator: str
    target_value: Any
    is_len: bool = False  # True if condition was e.g. len(s) > 5
    raw_expr: str = ""
    line_number: int = 0
    enclosing_block: str = "if"  # if, elif, assert, while
    is_guard: bool = False


@dataclass
class BranchPath:
    """Represents an execution branch path."""
    conditions: List[ConstraintInfo] = field(default_factory=list)
    action_type: str = "return"  # return, raise
    action_value: str = ""
    line_number: int = 0


@dataclass
class FunctionModel:
    """Extracted semantic model of a function."""
    name: str
    docstring: str = ""
    parameters: List[ParameterInfo] = field(default_factory=list)
    constraints: List[ConstraintInfo] = field(default_factory=list)
    spec_constraints: List[ConstraintInfo] = field(default_factory=list)
    branch_paths: List[BranchPath] = field(default_factory=list)
    return_type: str = "Any"
    source_code: str = ""
    line_start: int = 1
    line_end: int = 1


class ASTContextExtractor(ast.NodeVisitor):
    """Parses Python source code and extracts functions and constraints."""

    OP_MAP = {
        ast.Lt: "<",
        ast.LtE: "<=",
        ast.Gt: ">",
        ast.GtE: ">=",
        ast.Eq: "==",
        ast.NotEq: "!=",
        ast.In: "in",
        ast.NotIn: "not in",
        ast.Is: "is",
        ast.IsNot: "is not",
    }

    def __init__(self, source_code: str):
        self.source_code = source_code
        self.functions: List[FunctionModel] = []
        self._current_func: Optional[FunctionModel] = None

    def parse(self) -> List[FunctionModel]:
        """Parses the source code and returns extracted function models."""
        tree = ast.parse(self.source_code)
        self.visit(tree)
        return self.functions

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._process_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self._process_function(node)

    def _process_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        func_model = FunctionModel(
            name=node.name,
            docstring=ast.get_docstring(node) or "",
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
        )

        # Extract return type annotation
        if node.returns:
            func_model.return_type = ast.unparse(node.returns)

        # Extract parameters
        args = node.args
        defaults = [None] * (len(args.args) - len(args.defaults)) + args.defaults

        for arg, default in zip(args.args, defaults):
            if arg.arg in ("self", "cls"):
                continue
            type_hint = "Any"
            if arg.annotation:
                type_hint = ast.unparse(arg.annotation)

            has_default = default is not None
            default_val = None
            if has_default:
                try:
                    default_val = ast.literal_eval(default)
                except Exception:
                    default_val = ast.unparse(default)

            func_model.parameters.append(
                ParameterInfo(
                    name=arg.arg,
                    type_name=type_hint,
                    default_value=default_val,
                    has_default=has_default,
                )
            )

        # Extract specification constraints from docstring (Business Logic Contract)
        if func_model.docstring:
            func_model.spec_constraints = self._extract_docstring_specifications(
                func_model.docstring, [p.name for p in func_model.parameters]
            )

        # Extract body constraints and branch paths
        self._current_func = func_model
        self._scan_block_statements(node.body, func_model, [])
        self.functions.append(func_model)
        self._current_func = None

    def _extract_docstring_specifications(
        self, docstring: str, valid_param_names: List[str]
    ) -> List[ConstraintInfo]:
        """Extracts formal business boundary specifications from function docstrings."""
        specs: List[ConstraintInfo] = []
        param_set = set(valid_param_names)

        # Pattern 1: e.g. 650 <= credit_score <= 850
        pat_range = re.findall(r"(\d+(?:\.\d+)?)\s*(<=|<)\s*(\w+)\s*(<=|<)\s*(\d+(?:\.\d+)?)", docstring)
        for lower_s, lop, var, rop, upper_s in pat_range:
            if var in param_set:
                lval = float(lower_s) if "." in lower_s else int(lower_s)
                uval = float(upper_s) if "." in upper_s else int(upper_s)
                specs.append(ConstraintInfo(variable=var, operator=">=" if "<=" in lop else ">", target_value=lval, enclosing_block="docstring_spec"))
                specs.append(ConstraintInfo(variable=var, operator="<=" if "<=" in rop else "<", target_value=uval, enclosing_block="docstring_spec"))

        # Pattern 2: e.g. variable must be at least X or variable >= X
        pat_min = re.findall(r"(\w+)\s*(?:must be at least|>=)\s*\$?(\d+(?:\.\d+)?)", docstring, re.IGNORECASE)
        for var, val_s in pat_min:
            var_clean = var.lower().replace(" ", "_")
            # match closest param
            matched = next((p for p in valid_param_names if p.lower() in var_clean or var_clean in p.lower()), None)
            if matched:
                val = float(val_s) if "." in val_s else int(val_s)
                specs.append(ConstraintInfo(variable=matched, operator=">=", target_value=val, enclosing_block="docstring_spec"))

        # Pattern 3: e.g. variable must be at most X or variable <= X
        pat_max = re.findall(r"(\w+)\s*(?:must be at most|<=)\s*\$?(\d+(?:\.\d+)?)", docstring, re.IGNORECASE)
        for var, val_s in pat_max:
            var_clean = var.lower().replace(" ", "_")
            matched = next((p for p in valid_param_names if p.lower() in var_clean or var_clean in p.lower()), None)
            if matched:
                val = float(val_s) if "." in val_s else int(val_s)
                specs.append(ConstraintInfo(variable=matched, operator="<=", target_value=val, enclosing_block="docstring_spec"))

        return specs

    def _is_guard_body(self, body: List[ast.stmt]) -> bool:
        if not body:
            return False
        for s in body:
            if isinstance(s, ast.Raise):
                return True
            if isinstance(s, ast.Return):
                val_str = ast.unparse(s.value) if s.value else "None"
                if val_str in ("False", "None") or "error" in val_str.lower() or "reject" in val_str.lower():
                    return True
        return False

    def _scan_block_statements(
        self,
        statements: List[ast.stmt],
        func_model: FunctionModel,
        current_conditions: List[ConstraintInfo],
    ) -> None:
        for stmt in statements:
            if isinstance(stmt, ast.If):
                is_guard = self._is_guard_body(stmt.body)
                # Extract constraints from if condition
                extracted = self._extract_constraints_from_expr(stmt.test, stmt.lineno, "if", is_guard=is_guard)
                func_model.constraints.extend(extracted)

                # Traverse then-branch
                then_conds = current_conditions + extracted
                self._scan_block_statements(stmt.body, func_model, then_conds)

                # Traverse else/elif branch
                if stmt.orelse:
                    # Inverted condition approximation
                    inv_extracted = [self._invert_constraint(c) for c in extracted]
                    else_conds = current_conditions + inv_extracted
                    self._scan_block_statements(stmt.orelse, func_model, else_conds)

            elif isinstance(stmt, ast.Assert):
                extracted = self._extract_constraints_from_expr(stmt.test, stmt.lineno, "assert", is_guard=True)
                func_model.constraints.extend(extracted)
                msg = ast.unparse(stmt.msg) if stmt.msg else "AssertionError"
                func_model.branch_paths.append(
                    BranchPath(
                        conditions=current_conditions + [self._invert_constraint(c) for c in extracted],
                        action_type="raise",
                        action_value=f"AssertionError({msg})",
                        line_number=stmt.lineno,
                    )
                )

            elif isinstance(stmt, ast.Return):
                val_repr = ast.unparse(stmt.value) if stmt.value else "None"
                func_model.branch_paths.append(
                    BranchPath(
                        conditions=list(current_conditions),
                        action_type="return",
                        action_value=val_repr,
                        line_number=stmt.lineno,
                    )
                )

            elif isinstance(stmt, ast.Raise):
                exc_repr = ast.unparse(stmt.exc) if stmt.exc else "Exception"
                func_model.branch_paths.append(
                    BranchPath(
                        conditions=list(current_conditions),
                        action_type="raise",
                        action_value=exc_repr,
                        line_number=stmt.lineno,
                    )
                )

    def _extract_constraints_from_expr(
        self, expr: ast.expr, lineno: int, block_type: str, is_guard: bool = False
    ) -> List[ConstraintInfo]:
        constraints: List[ConstraintInfo] = []

        if isinstance(expr, ast.Compare):
            # E.g. left op right or chained comparisons like a < b < c
            curr_left = expr.left
            for op_type, right_node in zip(expr.ops, expr.comparators):
                op_str = self.OP_MAP.get(type(op_type), None)
                if not op_str:
                    continue

                var_name, is_len = self._extract_var_info(curr_left)
                target_val = self._eval_literal_or_unparse(right_node)

                # Check if comparison is inverted (e.g. 18 <= age)
                if not var_name:
                    var_name, is_len = self._extract_var_info(right_node)
                    target_val = self._eval_literal_or_unparse(curr_left)
                    op_str = self._flip_op(op_str)

                if var_name:
                    constraints.append(
                        ConstraintInfo(
                            variable=var_name,
                            operator=op_str,
                            target_value=target_val,
                            is_len=is_len,
                            raw_expr=ast.unparse(expr),
                            line_number=lineno,
                            enclosing_block=block_type,
                            is_guard=is_guard,
                        )
                    )
                curr_left = right_node

        elif isinstance(expr, ast.BoolOp):
            for val in expr.values:
                constraints.extend(self._extract_constraints_from_expr(val, lineno, block_type, is_guard=is_guard))

        elif isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
            sub_constraints = self._extract_constraints_from_expr(expr.operand, lineno, block_type, is_guard=is_guard)
            constraints.extend([self._invert_constraint(c) for c in sub_constraints])

        return constraints

    def _extract_var_info(self, node: ast.AST) -> Tuple[Optional[str], bool]:
        """Returns (var_name, is_len)."""
        if isinstance(node, ast.Name):
            return node.id, False
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "len" and node.args:
                if isinstance(node.args[0], ast.Name):
                    return node.args[0].id, True
        return None, False

    def _eval_literal_or_unparse(self, node: ast.AST) -> Any:
        try:
            return ast.literal_eval(node)
        except Exception:
            return ast.unparse(node)

    def _flip_op(self, op: str) -> str:
        flips = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}
        return flips.get(op, op)

    def _invert_constraint(self, c: ConstraintInfo) -> ConstraintInfo:
        inv_map = {
            "<": ">=",
            "<=": ">",
            ">": "<=",
            ">=": "<",
            "==": "!=",
            "!=": "==",
            "in": "not in",
            "not in": "in",
            "is": "is not",
            "is not": "is",
        }
        return ConstraintInfo(
            variable=c.variable,
            operator=inv_map.get(c.operator, "!="),
            target_value=c.target_value,
            is_len=c.is_len,
            raw_expr=f"NOT ({c.raw_expr})",
            line_number=c.line_number,
            enclosing_block=c.enclosing_block,
        )


def extract_file_context(filepath: str) -> List[FunctionModel]:
    """Convenience helper to extract all functions from a Python source file."""
    with open(filepath, "r", encoding="utf-8") as f:
        code = f.read()
    extractor = ASTContextExtractor(code)
    return extractor.parse()
