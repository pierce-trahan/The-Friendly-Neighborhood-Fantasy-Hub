from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

CPU_ENGINE_VERSION: Final = "practice-board-v1"
RNG_VERSION: Final = "sha256-counter-v1"
STRATEGY_DEFINITION_VERSION: Final = "strategy-v1"
MAX_SEED: Final = (1 << 64) - 1
MAX_RANDOMNESS: Final = 100
MAX_RANDOM_CONSIDERATION_COUNT: Final = 21

SUPPORTED_FALLBACK_ARCHETYPES: Final = (
    "balanced",
    "qb_priority",
    "rb_heavy",
    "wr_heavy",
    "te_aware",
    "rookie_lean",
    "chaotic",
)

SUPPORTED_STRATEGIES: Final = (
    "balanced",
    "win_now",
    "productive_struggle",
    "hero_rb",
    "robust_rb",
    "wr_heavy",
    "early_qb_superflex",
)


@dataclass(frozen=True)
class ComponentBound:
    minimum: int
    maximum: int | None


@dataclass(frozen=True)
class ArchetypeDefinition:
    emphasized_position: str | None
    position_bonus: int
    rookie_bonus: int
    te_premium_bonus: int
    randomness_multiplier: int


COMPONENT_BOUNDS = MappingProxyType(
    {
        "board_order": ComponentBound(0, None),
        "starter_need": ComponentBound(-200, 300),
        "depth_need": ComponentBound(-100, 150),
        "archetype_fit": ComponentBound(-150, 200),
        "duplication_penalty": ComponentBound(-300, 0),
        "random_variation": ComponentBound(-200, 200),
    }
)

STARTER_NEED_SCORE: Final = 200
DEPTH_NEED_EMPTY_SCORE: Final = 100
DEPTH_NEED_SINGLE_SCORE: Final = 50
DUPLICATION_PENALTY_PER_EXTRA: Final = 100
DUPLICATION_PENALTY_START_COUNT: Final = 3

ARCHETYPE_DEFINITIONS = MappingProxyType(
    {
        "balanced": ArchetypeDefinition(None, 0, 0, 0, 1),
        "qb_priority": ArchetypeDefinition("QB", 200, 0, 0, 1),
        "rb_heavy": ArchetypeDefinition("RB", 175, 0, 0, 1),
        "wr_heavy": ArchetypeDefinition("WR", 175, 0, 0, 1),
        "te_aware": ArchetypeDefinition("TE", 150, 0, 50, 1),
        "rookie_lean": ArchetypeDefinition(None, 0, 100, 0, 1),
        "chaotic": ArchetypeDefinition(None, 0, 0, 0, 2),
    }
)
