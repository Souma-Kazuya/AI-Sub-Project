"""Target Module: Loan Approval Engine.

Evaluates credit score, annual income, and employment years for loan qualification.
Contains business constraints subject to Boundary Value Analysis (BVA) and
Equivalence Class Partitioning (ECP).
"""

from typing import Any, Dict


def evaluate_loan_eligibility(
    credit_score: int,
    annual_income: float,
    employment_years: int,
) -> bool:
    """Evaluates whether an applicant meets the minimum qualification thresholds.

    Business Rules:
    1. Credit score must be at least 650 and at most 850 (650 <= credit_score <= 850).
    2. Annual income must be at least $30,000.00 (annual_income >= 30000.0).
    3. Employment history must be at least 2 years (employment_years >= 2).

    Note: Contains an intentional subtle off-by-one boundary bug on credit_score
    (uses '>' instead of '>=') to demonstrate boundary synthesizer detection.
    """
    if credit_score is None or annual_income is None or employment_years is None:
        raise ValueError("Inputs cannot be null")

    # Fixed boundary condition: 650 is eligible (credit_score >= 650)
    if credit_score < 650 or credit_score > 850:
        return False

    if annual_income < 30000.0:
        return False

    if employment_years < 2:
        return False

    return True

