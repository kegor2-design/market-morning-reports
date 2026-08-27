"""Independent chart-insight research engine.

The module converts expert chart language into normalized primitives, reconstructs
point-in-time chart state, and evaluates historical outcomes without treating
expert claims as facts or standalone trading signals.
"""

from .historical import build_edge_summary, validate_historical_claim
from .primitives import detect_primitives, key_levels, map_expert_text
from .research import build_historical_research_queue, build_nightly_chart_research, build_strategy_candidates
from .universe import scan_symbol_bars, summarize_universe_events

__all__ = [
    "build_edge_summary",
    "validate_historical_claim",
    "detect_primitives",
    "key_levels",
    "map_expert_text",
    "build_strategy_candidates",
    "build_historical_research_queue",
    "build_nightly_chart_research",
    "scan_symbol_bars",
    "summarize_universe_events",
]
