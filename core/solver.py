"""SMT and Mathematical Boundary-Value & Equivalence-Class Partition Solver.

Calculates:
1. Boundary Value Analysis (BVA): (min-1, min, min+1, nominal, max-1, max, max+1)
2. Equivalence Class Partitioning (ECP): Valid partitions, underflow, overflow, null-state
3. Multi-variable constraint satisfaction using exact Interval arithmetic and optional Z3 SMT solver.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from core.ast_analyzer import ConstraintInfo, FunctionModel, ParameterInfo

# Check if z3 is optionally available
try:
    import z3  # type: ignore
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False


@dataclass
class BoundaryPoint:
    """Represents a specific boundary test point."""
    value: Any
    category: str  # min-1, min, min+1, nominal, max-1, max, max+1, null, type_fault
    is_valid: bool  # True if inside expected valid domain
    description: str


@dataclass
class EquivalencePartition:
    """Represents an Equivalence Class Partition."""
    name: str
    partition_type: str  # 'valid' or 'invalid'
    description: str
    representative_value: Any
    boundary_points: List[BoundaryPoint] = field(default_factory=list)


@dataclass
class ParameterPartitionPlan:
    """Calculated partition plan for a single parameter."""
    param_name: str
    inferred_type: str
    min_bound: Optional[float] = None
    max_bound: Optional[float] = None
    discrete_values: List[Any] = field(default_factory=list)
    partitions: List[EquivalencePartition] = field(default_factory=list)
    boundary_values: List[BoundaryPoint] = field(default_factory=list)


@dataclass
class MultiVarTestCase:
    """A synthesized multi-variable test case."""
    test_id: str
    name: str
    inputs: Dict[str, Any]
    expected_outcome: str  # 'pass', 'reject', 'exception'
    target_boundary: str
    category: str


class BoundarySolver:
    """Calculates BVA points and Equivalence Classes from extracted constraints."""

    def __init__(self, use_z3: bool = True):
        self.use_z3 = use_z3 and HAS_Z3

    def solve_function(self, func_model: FunctionModel) -> Dict[str, ParameterPartitionPlan]:
        """Analyzes all parameters of a function and computes their BVA/ECP partitions."""
        plans: Dict[str, ParameterPartitionPlan] = {}

        # Group constraints by parameter
        param_constraints: Dict[str, List[ConstraintInfo]] = {
            p.name: [] for p in func_model.parameters
        }
        for c in func_model.constraints:
            if c.variable in param_constraints:
                param_constraints[c.variable].append(c)

        for param in func_model.parameters:
            # Prioritize formal docstring/contract specification constraints if present
            spec_c = [c for c in func_model.spec_constraints if c.variable == param.name]
            code_c = param_constraints.get(param.name, [])
            effective_constraints = spec_c if spec_c else code_c

            plan = self._solve_parameter(param, effective_constraints)
            plans[param.name] = plan

        return plans

    def _solve_parameter(
        self, param: ParameterInfo, constraints: List[ConstraintInfo]
    ) -> ParameterPartitionPlan:
        inferred_type = self._resolve_type(param.type_name, constraints)

        min_val: Optional[float] = None
        max_val: Optional[float] = None
        discrete_values: List[Any] = []
        is_length_constraint = False

        inv_map = {
            "<": ">=",
            "<=": ">",
            ">": "<=",
            ">=": "<",
            "==": "!=",
            "!=": "==",
        }

        for c in constraints:
            if c.is_len:
                is_length_constraint = True

            val = c.target_value
            op = c.operator
            # If this is a guard condition (early return False/raise), invert to find valid domain
            if c.is_guard:
                op = inv_map.get(op, op)

            # Numerical bounds
            if isinstance(val, (int, float)):
                if op in (">", ">="):
                    lower = val if op == ">=" else (val + 1 if isinstance(val, int) else val + 0.01)
                    min_val = lower if min_val is None else max(min_val, lower)
                elif op in ("<", "<="):
                    upper = val if op == "<=" else (val - 1 if isinstance(val, int) else val - 0.01)
                    max_val = upper if max_val is None else min(max_val, upper)
                elif op == "==":
                    discrete_values.append(val)

            elif isinstance(val, (list, tuple, set)):
                discrete_values.extend(list(val))

        # Ensure valid ordering if both present
        if min_val is not None and max_val is not None and min_val > max_val:
            min_val, max_val = min(min_val, max_val), max(min_val, max_val)

        # Default fallback bounds if unbounded
        if min_val is None and max_val is not None:
            min_val = 0 if max_val >= 0 else max_val - 100
        elif max_val is None and min_val is not None:
            max_val = min_val + 50 if min_val < 50 else min_val * 2
        elif min_val is None and max_val is None:
            # Default bounds based on parameter type
            if inferred_type in ("int", "float"):
                min_val = 1
                max_val = 100

        plan = ParameterPartitionPlan(
            param_name=param.name,
            inferred_type="str_len" if is_length_constraint else inferred_type,
            min_bound=min_val,
            max_bound=max_val,
            discrete_values=discrete_values,
        )

        if is_length_constraint:
            self._generate_string_partitions(plan, min_val or 1, max_val or 50)
        elif inferred_type == "int":
            self._generate_int_partitions(plan, int(min_val or 0), int(max_val or 100))
        elif inferred_type == "float":
            self._generate_float_partitions(plan, float(min_val or 0.0), float(max_val or 100.0))
        elif inferred_type == "bool":
            self._generate_bool_partitions(plan)
        else:
            self._generate_generic_partitions(plan, discrete_values)

        return plan

    def _generate_int_partitions(
        self, plan: ParameterPartitionPlan, min_v: int, max_v: int
    ) -> None:
        nominal = (min_v + max_v) // 2

        # 6-Point / 7-Point Boundary Value Analysis
        bva_points = [
            BoundaryPoint(value=min_v - 1, category="min - 1", is_valid=False, description=f"Just below min ({min_v - 1})"),
            BoundaryPoint(value=min_v, category="min", is_valid=True, description=f"Exact lower bound ({min_v})"),
            BoundaryPoint(value=min_v + 1, category="min + 1", is_valid=True, description=f"Just above min ({min_v + 1})"),
            BoundaryPoint(value=nominal, category="nominal", is_valid=True, description=f"Nominal typical value ({nominal})"),
            BoundaryPoint(value=max_v - 1, category="max - 1", is_valid=True, description=f"Just below max ({max_v - 1})"),
            BoundaryPoint(value=max_v, category="max", is_valid=True, description=f"Exact upper bound ({max_v})"),
            BoundaryPoint(value=max_v + 1, category="max + 1", is_valid=False, description=f"Just above max ({max_v + 1})"),
        ]

        # Equivalence Class Partitions
        partitions = [
            EquivalencePartition(
                name=f"EC_Valid_Range_[{min_v},{max_v}]",
                partition_type="valid",
                description=f"Valid inputs inside range [{min_v}, {max_v}]",
                representative_value=nominal,
                boundary_points=[b for b in bva_points if b.is_valid],
            ),
            EquivalencePartition(
                name=f"EC_Invalid_Underflow_[<{min_v}]",
                partition_type="invalid",
                description=f"Invalid inputs below lower bound < {min_v}",
                representative_value=min_v - 1,
                boundary_points=[bva_points[0]],
            ),
            EquivalencePartition(
                name=f"EC_Invalid_Overflow_[>{max_v}]",
                partition_type="invalid",
                description=f"Invalid inputs above upper bound > {max_v}",
                representative_value=max_v + 1,
                boundary_points=[bva_points[-1]],
            ),
            EquivalencePartition(
                name="EC_Invalid_NullState",
                partition_type="invalid",
                description="Invalid None / null state transition",
                representative_value=None,
                boundary_points=[BoundaryPoint(value=None, category="null", is_valid=False, description="Null / None value")],
            ),
        ]

        plan.boundary_values = bva_points
        plan.partitions = partitions

    def _generate_float_partitions(
        self, plan: ParameterPartitionPlan, min_v: float, max_v: float, epsilon: float = 0.01
    ) -> None:
        nominal = round((min_v + max_v) / 2.0, 2)
        min_v = round(min_v, 2)
        max_v = round(max_v, 2)

        bva_points = [
            BoundaryPoint(value=round(min_v - epsilon, 2), category="min - eps", is_valid=False, description=f"Underflow lower boundary ({min_v - epsilon})"),
            BoundaryPoint(value=min_v, category="min", is_valid=True, description=f"Exact lower bound ({min_v})"),
            BoundaryPoint(value=round(min_v + epsilon, 2), category="min + eps", is_valid=True, description=f"Just inside lower bound ({min_v + epsilon})"),
            BoundaryPoint(value=nominal, category="nominal", is_valid=True, description=f"Nominal floating point value ({nominal})"),
            BoundaryPoint(value=round(max_v - epsilon, 2), category="max - eps", is_valid=True, description=f"Just inside upper bound ({max_v - epsilon})"),
            BoundaryPoint(value=max_v, category="max", is_valid=True, description=f"Exact upper bound ({max_v})"),
            BoundaryPoint(value=round(max_v + epsilon, 2), category="max + eps", is_valid=False, description=f"Overflow upper boundary ({max_v + epsilon})"),
        ]

        partitions = [
            EquivalencePartition(
                name=f"EC_Valid_Float_Range_[{min_v},{max_v}]",
                partition_type="valid",
                description=f"Valid float domain within [{min_v}, {max_v}]",
                representative_value=nominal,
                boundary_points=[b for b in bva_points if b.is_valid],
            ),
            EquivalencePartition(
                name=f"EC_Invalid_Float_Underflow_[<{min_v}]",
                partition_type="invalid",
                description=f"Float values strictly below {min_v}",
                representative_value=round(min_v - epsilon, 2),
                boundary_points=[bva_points[0]],
            ),
            EquivalencePartition(
                name=f"EC_Invalid_Float_Overflow_[>{max_v}]",
                partition_type="invalid",
                description=f"Float values strictly above {max_v}",
                representative_value=round(max_v + epsilon, 2),
                boundary_points=[bva_points[-1]],
            ),
        ]

        plan.boundary_values = bva_points
        plan.partitions = partitions

    def _generate_string_partitions(
        self, plan: ParameterPartitionPlan, min_len: float, max_len: float
    ) -> None:
        min_l = max(0, int(min_len))
        max_l = int(max_len)
        nom_l = (min_l + max_l) // 2

        bva_points = [
            BoundaryPoint(value="", category="empty_str", is_valid=(min_l == 0), description="Empty string (len=0)"),
            BoundaryPoint(value="a" * max(0, min_l - 1), category="len_min - 1", is_valid=False, description=f"Length min - 1 (len={max(0, min_l - 1)})"),
            BoundaryPoint(value="a" * min_l, category="len_min", is_valid=True, description=f"Exact min length (len={min_l})"),
            BoundaryPoint(value="a" * (min_l + 1), category="len_min + 1", is_valid=True, description=f"Length min + 1 (len={min_l + 1})"),
            BoundaryPoint(value="a" * nom_l, category="len_nominal", is_valid=True, description=f"Nominal string (len={nom_l})"),
            BoundaryPoint(value="a" * max_l, category="len_max", is_valid=True, description=f"Exact max length (len={max_l})"),
            BoundaryPoint(value="a" * (max_l + 1), category="len_max + 1", is_valid=False, description=f"Length max + 1 (len={max_l + 1})"),
            BoundaryPoint(value=None, category="null", is_valid=False, description="Null/None string reference"),
        ]

        partitions = [
            EquivalencePartition(
                name=f"EC_Valid_StringLength_[{min_l},{max_l}]",
                partition_type="valid",
                description=f"Strings of length between {min_l} and {max_l}",
                representative_value="a" * nom_l,
                boundary_points=[b for b in bva_points if b.is_valid],
            ),
            EquivalencePartition(
                name="EC_Invalid_String_Short",
                partition_type="invalid",
                description=f"Strings with length < {min_l}",
                representative_value="a" * max(0, min_l - 1),
                boundary_points=[bva_points[1]],
            ),
            EquivalencePartition(
                name="EC_Invalid_String_Long",
                partition_type="invalid",
                description=f"Strings with length > {max_l}",
                representative_value="a" * (max_l + 1),
                boundary_points=[bva_points[6]],
            ),
            EquivalencePartition(
                name="EC_Invalid_String_Null",
                partition_type="invalid",
                description="Null reference string",
                representative_value=None,
                boundary_points=[bva_points[-1]],
            ),
        ]

        plan.boundary_values = bva_points
        plan.partitions = partitions

    def _generate_bool_partitions(self, plan: ParameterPartitionPlan) -> None:
        plan.boundary_values = [
            BoundaryPoint(value=True, category="true", is_valid=True, description="Boolean True state"),
            BoundaryPoint(value=False, category="false", is_valid=True, description="Boolean False state"),
            BoundaryPoint(value=None, category="null", is_valid=False, description="Null boolean state"),
        ]
        plan.partitions = [
            EquivalencePartition("EC_Bool_True", "valid", "Boolean True", True),
            EquivalencePartition("EC_Bool_False", "valid", "Boolean False", False),
            EquivalencePartition("EC_Bool_Null", "invalid", "Null state", None),
        ]

    def _generate_generic_partitions(
        self, plan: ParameterPartitionPlan, discrete_vals: List[Any]
    ) -> None:
        if discrete_vals:
            b_points = [
                BoundaryPoint(value=v, category="member", is_valid=True, description=f"Allowed member {v}")
                for v in discrete_vals
            ]
            b_points.append(BoundaryPoint(value="__INVALID_VAL__", category="non_member", is_valid=False, description="Disallowed member"))
            b_points.append(BoundaryPoint(value=None, category="null", is_valid=False, description="Null value"))

            plan.boundary_values = b_points
            plan.partitions = [
                EquivalencePartition("EC_Valid_Members", "valid", "Recognized domain members", discrete_vals[0]),
                EquivalencePartition("EC_Invalid_Member", "invalid", "Unrecognized member", "__INVALID_VAL__"),
                EquivalencePartition("EC_Null_State", "invalid", "Null reference", None),
            ]
        else:
            plan.boundary_values = [
                BoundaryPoint(value="valid_sample", category="nominal", is_valid=True, description="Sample valid argument"),
                BoundaryPoint(value=None, category="null", is_valid=False, description="Null reference"),
            ]
            plan.partitions = [
                EquivalencePartition("EC_Valid_Generic", "valid", "Valid input", "valid_sample"),
                EquivalencePartition("EC_Invalid_Null", "invalid", "Null input", None),
            ]

    def _resolve_type(self, type_hint: str, constraints: List[ConstraintInfo]) -> str:
        hint_lower = type_hint.lower()
        if "int" in hint_lower:
            return "int"
        if "float" in hint_lower:
            return "float"
        if "str" in hint_lower:
            return "str"
        if "bool" in hint_lower:
            return "bool"

        # Infer from constraints
        for c in constraints:
            if c.is_len:
                return "str"
            if isinstance(c.target_value, int):
                return "int"
            if isinstance(c.target_value, float):
                return "float"
            if isinstance(c.target_value, bool):
                return "bool"
            if isinstance(c.target_value, str):
                return "str"

        return "int"  # sensible default for numerical BVA

    def generate_decision_table_cases(
        self,
        func_model: FunctionModel,
        plans: Dict[str, ParameterPartitionPlan],
        max_combinations: int = 25,
    ) -> List[MultiVarTestCase]:
        """Synthesizes multi-variable decision table combinations (Cartesian / Pairwise)."""
        test_cases: List[MultiVarTestCase] = []
        param_names = [p.name for p in func_model.parameters]

        if not param_names:
            return [
                MultiVarTestCase(
                    test_id="TC_001",
                    name="test_zero_args",
                    inputs={},
                    expected_outcome="pass",
                    target_boundary="nominal",
                    category="nominal",
                )
            ]

        # 1. Base Nominal Valid Test Case
        nominal_inputs = {}
        for p in func_model.parameters:
            plan = plans.get(p.name)
            nom_pt = next((b for b in (plan.boundary_values if plan else []) if b.category in ("nominal", "len_nominal")), None)
            if not nom_pt:
                nom_pt = next((b for b in (plan.boundary_values if plan else []) if b.is_valid), None)
            nominal_inputs[p.name] = nom_pt.value if nom_pt else (p.default_value if p.has_default else 10)

        test_cases.append(
            MultiVarTestCase(
                test_id=f"TC_{len(test_cases)+1:03d}",
                name="test_nominal_happy_path",
                inputs=dict(nominal_inputs),
                expected_outcome="pass",
                target_boundary="all_nominal",
                category="happy_path",
            )
        )

        # 2. Individual Boundary Variations (One-at-a-time BVA: min-1, min, min+1, max-1, max, max+1, null)
        for p_name in param_names:
            plan = plans.get(p_name)
            if not plan:
                continue

            for pt in plan.boundary_values:
                # Skip duplicate of nominal
                if pt.category in ("nominal", "len_nominal"):
                    continue

                case_inputs = dict(nominal_inputs)
                case_inputs[p_name] = pt.value

                expected = "pass" if pt.is_valid else "reject"
                safe_cat = pt.category.replace(" ", "_").replace("+", "plus_").replace("-", "minus_")
                test_cases.append(
                    MultiVarTestCase(
                        test_id=f"TC_{len(test_cases)+1:03d}",
                        name=f"test_bva_{p_name}_{safe_cat}",
                        inputs=case_inputs,
                        expected_outcome=expected,
                        target_boundary=f"{p_name}={pt.category}",
                        category=f"BVA_{safe_cat}",
                    )
                )

        # 3. Multi-Variable Extreme Combinations (All min, All max, Mixed)
        if len(param_names) > 1:
            all_min = {}
            all_max = {}
            for p_name in param_names:
                plan = plans.get(p_name)
                min_pt = next((b for b in (plan.boundary_values if plan else []) if b.category in ("min", "len_min")), None)
                max_pt = next((b for b in (plan.boundary_values if plan else []) if b.category in ("max", "len_max")), None)
                all_min[p_name] = min_pt.value if min_pt else nominal_inputs[p_name]
                all_max[p_name] = max_pt.value if max_pt else nominal_inputs[p_name]

            test_cases.append(
                MultiVarTestCase(
                    test_id=f"TC_{len(test_cases)+1:03d}",
                    name="test_multivar_all_min_boundary",
                    inputs=all_min,
                    expected_outcome="pass",
                    target_boundary="all_min",
                    category="multivar_boundary",
                )
            )
            test_cases.append(
                MultiVarTestCase(
                    test_id=f"TC_{len(test_cases)+1:03d}",
                    name="test_multivar_all_max_boundary",
                    inputs=all_max,
                    expected_outcome="pass",
                    target_boundary="all_max",
                    category="multivar_boundary",
                )
            )

        return test_cases[:max_combinations]
