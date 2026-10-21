"""Target Module: Discount & Pricing Calculator.

Computes customer discounts based on age and purchase volume.
Demonstrates multi-branch boundary conditions.
"""


def calculate_discount(age: int, order_amount: float) -> float:
    """Calculates discount percentage based on age and order volume.

    Rules:
    - Age must be between 0 and 120 (0 <= age <= 120).
    - Order amount must be positive up to 10000.0 (0 < order_amount <= 10000.0).
    - Senior citizens (age >= 65): 20% discount.
    - Minors (age < 18): 15% discount.
    - High-volume orders (order_amount >= 1000.0): additional 5% discount.
    - Default standard discount: 5%.
    """
    if age is None or order_amount is None:
        raise ValueError("Age and order amount must not be None")

    if age < 0 or age > 120:
        raise ValueError("Age out of valid range [0, 120]")

    if order_amount <= 0 or order_amount > 10000.0:
        raise ValueError("Order amount out of valid range (0, 10000.0]")

    discount = 0.05
    if age >= 65:
        discount = 0.20
    elif age < 18:
        discount = 0.15

    if order_amount >= 1000.0:
        discount += 0.05

    return discount

