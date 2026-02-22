"""
FormulaParser exception hierarchy — extracted from formula_parser.py

PRD §3.3, FR-3.11
"""


class FormulaError(Exception):
    """Base error for formula operations."""
    pass


class FormulaSecurityError(FormulaError):
    """Raised when a disallowed function / pattern is detected (FR-3.11)."""
    pass


class FormulaColumnError(FormulaError):
    """Raised when a referenced column does not exist (ERR-3.1)."""
    pass


class FormulaTypeError(FormulaError):
    """Raised on type mismatch — e.g. math on string column (ERR-3.3)."""
    pass
