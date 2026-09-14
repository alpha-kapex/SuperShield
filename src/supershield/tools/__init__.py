"""Deterministic tools used by both local and Strands-backed workflows."""

from supershield.tools.evidence import collect_evidence
from supershield.tools.finance import calculate_financial_scenarios
from supershield.tools.location import assess_location
from supershield.tools.skepticism import assess_claims
from supershield.tools.validation import validate_analysis

__all__ = [
    "assess_claims",
    "assess_location",
    "calculate_financial_scenarios",
    "collect_evidence",
    "validate_analysis",
]
