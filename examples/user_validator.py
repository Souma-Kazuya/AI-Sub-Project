"""Target Module: User Registration Validator.

Demonstrates Boundary Value Analysis (BVA) for string lengths and multi-variable types.
"""


def validate_user_registration(username: str, password: str, age: int) -> bool:
    """Validates user account creation requirements.

    Rules:
    - Username length must be between 3 and 20 characters (3 <= len(username) <= 20).
    - Password length must be between 8 and 64 characters (8 <= len(password) <= 64).
    - Age must be at least 18 (age >= 18 and age <= 100).
    """
    if username is None or password is None or age is None:
        raise ValueError("Fields cannot be null")

    if len(username) < 3 or len(username) > 20:
        return False

    if len(password) < 8 or len(password) > 64:
        return False

    if age < 18 or age > 100:
        return False

    return True

