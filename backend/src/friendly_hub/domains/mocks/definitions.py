from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

CPU_ENGINE_VERSION: Final = "practice-board-v1"
RNG_VERSION: Final = "sha256-counter-v1"
MAX_SEED: Final = (1 << 64) - 1
MAX_RANDOMNESS: Final = 100
MAX_RANDOM_CONSIDERATION_COUNT: Final = 21


@dataclass(frozen=True)
class ComponentBound:
    minimum: int
    maximum: int | None


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
