from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HubError(Exception):
    code: str
    message: str
    action: str
    status_code: int
    severity: str = "error"
    retryable: bool = False
    field_errors: list[dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        return self.message
