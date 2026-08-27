"""Point-in-time YouTube chart-claim collection and evaluation.

This package is intentionally independent from the morning-news publishing
pipeline.  Its outputs are shadow research data until they pass review and
out-of-sample validation.
"""

from .captions import CaptionCue, parse_vtt
from .claims import extract_chart_claims
from .outcomes import evaluate_claim
from .time_model import AvailabilityDecision, resolve_actionable_time

__all__ = [
    "AvailabilityDecision",
    "CaptionCue",
    "evaluate_claim",
    "extract_chart_claims",
    "parse_vtt",
    "resolve_actionable_time",
]

