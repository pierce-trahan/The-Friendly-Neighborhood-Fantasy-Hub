from typing import Final, Literal

ALERT_ENGINE_VERSION: Final = "alert-engine-v1"
ALERT_RULE_VERSION: Final = "alert-rules-v1"
DEFAULT_VALUE_GAP_MINIMUM: Final = 6
DEFAULT_TARGET_SAFETY_BUFFER: Final = 2
MAX_COST_REFERENCES: Final = 3

ReturnRisk = Literal[
    "likely_to_return",
    "uncertain",
    "unlikely_to_return",
    "unavailable",
]
FreshnessState = Literal["fresh", "aging", "stale", "expired", "invalid"]
FormatCompatibility = Literal["exact", "family", "partial", "incompatible", "unknown"]
ConfidenceLevel = Literal["high", "medium", "low", "unavailable"]
