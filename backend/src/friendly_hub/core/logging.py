from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "component": record.name,
        }
        for field_name in ("correlation_id", "error_code", "duration_ms"):
            value = getattr(record, field_name, None)
            if value is not None:
                event[field_name] = value
        if record.exc_info and record.exc_info[0]:
            event["exception_type"] = record.exc_info[0].__name__
        return json.dumps(event, separators=(",", ":"), ensure_ascii=True)


def configure_logging(log_dir: Path) -> None:
    root_logger = logging.getLogger()
    if any(getattr(handler, "_friendly_hub_handler", False) for handler in root_logger.handlers):
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "hub.log.jsonl",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(JsonFormatter())
    handler._friendly_hub_handler = True  # type: ignore[attr-defined]
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
