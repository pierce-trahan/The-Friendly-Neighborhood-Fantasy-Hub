from datetime import UTC, datetime


def utc_now_text() -> str:
    return datetime.now(UTC).isoformat()
