from __future__ import annotations

from types import MappingProxyType
from typing import Final, Literal

REPORT_ENGINE_VERSION: Final = "post-draft-report-engine-v1"
REPORT_RULES_VERSION: Final = "post-draft-report-rules-v1"
EXPLANATION_TEMPLATE_VERSION: Final = "post-draft-report-explanations-v1"

SECTION_KEYS: Final = (
    "draft_summary",
    "position_inventory",
    "starter_coverage",
    "roster_concentration",
    "year_one_production_context",
    "dynasty_market_context",
    "age_risk_profile",
    "long_term_value",
    "liquidity",
    "player_fragility",
    "strategy_story",
    "personal_board_choice_moments",
    "recorded_alert_moments",
    "evidence_limits",
)

SECTION_TITLES = MappingProxyType(
    {
        "draft_summary": "Draft summary",
        "position_inventory": "Position inventory",
        "starter_coverage": "Starter coverage",
        "roster_concentration": "Roster-construction concentration",
        "year_one_production_context": "Year-one production context",
        "dynasty_market_context": "Dynasty market context",
        "age_risk_profile": "Age-risk profile",
        "long_term_value": "Long-term dynasty value",
        "liquidity": "Liquidity",
        "player_fragility": "Player fragility",
        "strategy_story": "Strategy story",
        "personal_board_choice_moments": "Personal Board choice moments",
        "recorded_alert_moments": "Recorded alert moments",
        "evidence_limits": "Evidence limits",
    }
)

LIMITED_COVERAGE_MINIMUM_BASIS_POINTS: Final = 5_000
SUPPORTED_COVERAGE_MINIMUM_BASIS_POINTS: Final = 8_000
BALANCED_MAXIMUM_BASIS_POINTS: Final = 4_000
HIGHLY_CONCENTRATED_ABOVE_BASIS_POINTS: Final = 5_500
MAXIMUM_USER_ROSTER_PICKS: Final = 60
MAXIMUM_STARTER_SLOTS: Final = 60

Availability = Literal["supported", "limited", "unavailable", "not_applicable"]
Confidence = Literal["high", "medium", "low", "unavailable"]
EvidenceState = Literal["usable", "expired", "incompatible", "invalid"]
DraftMode = Literal["live", "mock"]
StrategyHistoryState = Literal["valid", "incomplete", "corrupt"]
ConcentrationBand = Literal[
    "balanced_distribution",
    "concentrated",
    "highly_concentrated",
    "coverage_gap",
]
SlotType = Literal["QB", "RB", "WR", "TE", "FLEX", "SUPER_FLEX"]

SUPPORTED_SLOT_ELIGIBILITY = MappingProxyType(
    {
        "QB": frozenset({"QB"}),
        "RB": frozenset({"RB"}),
        "WR": frozenset({"WR"}),
        "TE": frozenset({"TE"}),
        "FLEX": frozenset({"RB", "WR", "TE"}),
        "SUPER_FLEX": frozenset({"QB", "RB", "WR", "TE"}),
    }
)
FLEX_SLOT_TYPES: Final = frozenset({"FLEX", "SUPER_FLEX"})
BLOCKING_EVIDENCE_STATES: Final = frozenset(
    {"expired", "incompatible", "invalid"}
)

UNSUPPORTED_SECTION_REASONS = MappingProxyType(
    {
        "long_term_value": "LONG_TERM_VALUE_EVIDENCE_UNAVAILABLE",
        "liquidity": "LIQUIDITY_EVIDENCE_UNAVAILABLE",
        "player_fragility": "PLAYER_FRAGILITY_EVIDENCE_UNAVAILABLE",
    }
)

EXPLANATION_TEMPLATES = MappingProxyType(
    {
        "starter.coverage_complete": (
            "All {starter_slots_total} configured starter slots can be covered "
            "by the drafted roster."
        ),
        "starter.coverage_partial": (
            "{starter_slots_filled} of {starter_slots_total} configured starter "
            "slots can be covered; review the unfilled slot labels."
        ),
        "starter.coverage_unavailable": (
            "Starter coverage is unavailable because the saved league starter "
            "shape could not be normalized."
        ),
        "concentration.balanced": (
            "No position accounts for more than {balanced_maximum_percent}% of "
            "the roster, and every distinct starter position is covered."
        ),
        "concentration.concentrated": (
            "{position} accounts for {position_share_percent}% of the roster, "
            "above the V1 concentration boundary."
        ),
        "concentration.highly_concentrated": (
            "{position} accounts for {position_share_percent}% of the roster, "
            "above the V1 high-concentration boundary."
        ),
        "concentration.coverage_gap": (
            "{unfilled_position_count} distinct configured starter position "
            "group remains uncovered."
        ),
        "production.supported": (
            "Saved categorical production evidence covers {covered_players} of "
            "{roster_players} rostered players."
        ),
        "production.limited": (
            "Saved categorical production evidence covers {covered_players} of "
            "{roster_players} rostered players, so this context is limited."
        ),
        "production.unavailable": (
            "Year-one production context is unavailable because the saved draft "
            "lacks enough compatible, usable evidence."
        ),
        "market.supported": (
            "Saved categorical market evidence covers {covered_players} of "
            "{roster_players} rostered players."
        ),
        "market.limited": (
            "Saved categorical market evidence covers {covered_players} of "
            "{roster_players} rostered players, so this context is limited."
        ),
        "market.unavailable": (
            "Dynasty market context is unavailable because the saved draft lacks "
            "enough compatible, usable evidence."
        ),
        "age_risk.supported": (
            "Saved categorical age-risk evidence covers {covered_players} of "
            "{roster_players} rostered players."
        ),
        "age_risk.limited": (
            "Saved categorical age-risk evidence covers {covered_players} of "
            "{roster_players} rostered players, so this profile is limited."
        ),
        "age_risk.unavailable": (
            "Age profile is unavailable because the saved draft does not contain "
            "enough approved age-risk evidence."
        ),
        "long_term.unavailable": (
            "Long-term dynasty value is unavailable because V1 has no approved "
            "outcome evidence for this claim."
        ),
        "liquidity.unavailable": (
            "Liquidity is unavailable because V1 has no approved market-depth or "
            "transaction evidence."
        ),
        "fragility.unavailable": (
            "Player fragility is unavailable because V1 has no approved injury, "
            "contract, or role evidence."
        ),
        "strategy.summary": (
            "The mock began with {initial_strategy} and contains {pivot_count} "
            "saved strategy pivot events."
        ),
        "strategy.limited": (
            "The saved mock strategy story is limited because part of its "
            "recorded history is incomplete."
        ),
        "strategy.not_applicable": (
            "Strategy story does not apply to this live draft."
        ),
        "personal_board.moment": (
            "At pick {overall_pick}, you selected {selected_player} while "
            "{passed_player} was {rank_delta} places higher on the saved Personal "
            "Board."
        ),
        "alerts.summary": (
            "The saved draft history contains {alert_event_count} recorded alert "
            "events."
        ),
        "comparison.compatible": (
            "{report_count} reports share the required league shape and rules "
            "version for descriptive comparison."
        ),
        "comparison.not_comparable": (
            "This section cannot be compared because one or more selected "
            "reports lacks compatible support."
        ),
        "report.limits": (
            "This report describes saved draft evidence, does not project "
            "outcomes, and leaves user judgment authoritative."
        ),
    }
)
