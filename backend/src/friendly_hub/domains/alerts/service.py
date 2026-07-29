from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from friendly_hub.core.errors import HubError
from friendly_hub.core.time import utc_now_text
from friendly_hub.domains.alerts.engine import elapsed_freshness
from friendly_hub.domains.alerts.models import (
    AlertEvidenceSnapshotRow,
    AlertPickValueSignalRow,
    AlertPlayerSignalRow,
)
from friendly_hub.domains.alerts.schemas import (
    AlertEvidenceCandidateRead,
    AlertEvidenceCommitRequest,
    AlertEvidenceCommitResponse,
    AlertEvidenceFormatSummary,
    AlertEvidenceMappingDecisionRequest,
    AlertEvidenceMappingRowRead,
    AlertEvidencePreviewRead,
    AlertEvidencePreviewRequest,
    AlertEvidenceSnapshotListResponse,
    AlertEvidenceSnapshotSummaryRead,
    AlertEvidenceSourceSummary,
)
from friendly_hub.domains.players.normalization import (
    normalize_search_name,
    normalize_team,
)
from friendly_hub.domains.players.repository import (
    ensure_external_mapping,
    find_name_candidates,
    get_external_mapping,
    get_player_row,
)

PLAYER_HEADERS = [
    "source_player_key",
    "display_name",
    "position",
    "team",
    "expected_pick_low",
    "expected_pick_high",
    "market_band",
    "win_now_production_band",
    "age_risk_band",
    "evidence_as_of",
    "limitation_codes",
]
PICK_HEADERS = [
    "asset_key",
    "asset_type",
    "overall_pick",
    "season_offset",
    "round",
    "value_low",
    "value_high",
    "evidence_as_of",
    "limitation_codes",
]
POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB"}
MARKET_BANDS = {"premium", "strong", "standard", "depth", "fringe"}
PRODUCTION_BANDS = {"high", "medium", "low"}
AGE_RISK_BANDS = {"lower", "middle", "higher"}
LIMITATION_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
INTEGER_PATTERN = re.compile(r"^(0|[1-9][0-9]*)$")
FORMULA_PREFIXES = ("=", "+", "-", "@")
FRESHNESS_ORDER = {
    "fresh": 0,
    "aging": 1,
    "stale": 2,
    "expired": 3,
    "invalid": 4,
}


@dataclass
class PreviewPlayerRow:
    id: str
    row_number: int
    signal: dict[str, object] | None
    source_player_key: str
    display_name: str
    position: str
    team: str | None
    status: str
    resolved_player_id: str | None
    candidate_player_ids: list[str]
    reason_code: str
    limitation_codes: list[str]
    initial_status: str
    initial_resolved_player_id: str | None
    initial_candidate_player_ids: list[str]
    initial_reason_code: str


@dataclass
class AlertEvidencePreview:
    id: str
    status: str
    content_hash: str
    snapshot: dict[str, object]
    rows: list[PreviewPlayerRow]
    warnings: list[str]
    limitation_codes: list[str]
    committed_snapshot_id: str | None = None
    created_at: str = field(default_factory=utc_now_text)


class AlertEvidencePreviewStore:
    """Process-local preview cache that never stores raw uploaded CSV text."""

    def __init__(self) -> None:
        self._items: dict[str, AlertEvidencePreview] = {}
        self._lock = RLock()

    def add(self, preview: AlertEvidencePreview) -> None:
        with self._lock:
            self._items[preview.id] = preview

    def get(self, preview_id: str) -> AlertEvidencePreview | None:
        with self._lock:
            return self._items.get(preview_id)


def _error(
    code: str,
    message: str,
    action: str,
    *,
    status_code: int = 422,
    field_errors: list[dict[str, object]] | None = None,
) -> HubError:
    return HubError(
        code,
        message,
        f"{action} Active evidence and draft state remain unchanged.",
        status_code,
        field_errors=field_errors or [],
    )


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str, field_name: str) -> datetime:
    cleaned = value.strip()
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must include a UTC offset")
    return parsed.astimezone(UTC)


def _optional_text(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _strict_int(
    value: str,
    field_name: str,
    *,
    optional: bool,
) -> int | None:
    cleaned = value.strip()
    if not cleaned and optional:
        return None
    if not INTEGER_PATTERN.fullmatch(cleaned):
        raise ValueError(f"{field_name} must be a whole number")
    return int(cleaned)


def _limitation_codes(value: str) -> list[str]:
    codes = sorted({part.strip() for part in value.split("|") if part.strip()})
    if len(codes) > 20 or any(
        len(code) > 80 or not LIMITATION_CODE_PATTERN.fullmatch(code)
        for code in codes
    ):
        raise ValueError("limitation_codes contains an unsupported code")
    return codes


def _bounded_csv_rows(
    csv_text: str,
    *,
    filename: str,
    headers: list[str],
    byte_limit: int,
    row_limit: int,
) -> list[dict[str, str]]:
    if "\x00" in csv_text:
        raise _error(
            "VALIDATION.ALERT_EVIDENCE.INVALID_ROW",
            f"{filename} contains a NUL byte.",
            "Export the file as plain UTF-8 CSV and preview it again.",
        )
    if len(csv_text.encode("utf-8")) > byte_limit:
        raise _error(
            "VALIDATION.ALERT_EVIDENCE.INVALID_ROW",
            f"{filename} is larger than the supported preview limit.",
            "Reduce the file to the documented row and size limits.",
        )
    try:
        reader = csv.DictReader(io.StringIO(csv_text, newline=""))
        if reader.fieldnames != headers:
            raise _error(
                "VALIDATION.ALERT_EVIDENCE.INVALID_HEADER",
                f"{filename} does not use the exact Phase 5 header.",
                "Use the documented column names and order, with no extra columns.",
            )
        rows = list(reader)
    except csv.Error as exc:
        raise _error(
            "VALIDATION.ALERT_EVIDENCE.INVALID_ROW",
            f"{filename} could not be parsed as CSV.",
            "Correct the CSV formatting and preview it again.",
        ) from exc
    if len(rows) > row_limit:
        raise _error(
            "VALIDATION.ALERT_EVIDENCE.INVALID_ROW",
            f"{filename} contains too many data rows.",
            f"Reduce the file to at most {row_limit} data rows.",
        )
    for row_number, row in enumerate(rows, start=2):
        if None in row or any(
            value is None or len(value) > 4096 for value in row.values()
        ):
            raise _error(
                "VALIDATION.ALERT_EVIDENCE.INVALID_ROW",
                f"{filename} row {row_number} has an extra or oversized field.",
                "Correct that row and preview the file again.",
            )
    return rows


def _player_signal(
    source: dict[str, str],
    *,
    supported_depth: int,
    snapshot_as_of: datetime,
) -> dict[str, object]:
    source_key = source["source_player_key"].strip()
    display_name = " ".join(source["display_name"].strip().split())
    position = source["position"].strip().upper()
    team = normalize_team(source["team"])
    if not source_key:
        raise ValueError("source_player_key is required")
    if not display_name:
        raise ValueError("display_name is required")
    if len(source_key) > 200 or len(display_name) > 200:
        raise ValueError("player identity text is too long")
    if position not in POSITIONS:
        raise ValueError("position is not supported")

    low = _strict_int(
        source["expected_pick_low"],
        "expected_pick_low",
        optional=True,
    )
    high = _strict_int(
        source["expected_pick_high"],
        "expected_pick_high",
        optional=True,
    )
    if (low is None) != (high is None):
        raise ValueError("expected-pick endpoints must both be present or empty")
    if low is not None and high is not None:
        if low < 1 or low > high or high > supported_depth:
            raise ValueError("expected-pick range is outside the supported draft")
        expected_pick: dict[str, int] | None = {"low": low, "high": high}
    else:
        expected_pick = None

    market_band = _optional_text(source["market_band"])
    production_band = _optional_text(source["win_now_production_band"])
    age_risk_band = _optional_text(source["age_risk_band"])
    if market_band is not None and market_band not in MARKET_BANDS:
        raise ValueError("market_band is not supported")
    if production_band is not None and production_band not in PRODUCTION_BANDS:
        raise ValueError("win_now_production_band is not supported")
    if age_risk_band is not None and age_risk_band not in AGE_RISK_BANDS:
        raise ValueError("age_risk_band is not supported")

    evidence_as_of = _parse_timestamp(
        source["evidence_as_of"],
        "evidence_as_of",
    )
    if evidence_as_of > snapshot_as_of or evidence_as_of > datetime.now(UTC):
        raise ValueError("evidence_as_of cannot be in the future")
    limitations = _limitation_codes(source["limitation_codes"])
    return {
        "source_player_key": source_key,
        "display_name": display_name,
        "position": position,
        "team": team,
        "expected_pick": expected_pick,
        "market_band": market_band,
        "win_now_production_band": production_band,
        "age_risk_band": age_risk_band,
        "evidence_as_of": _utc_text(evidence_as_of),
        "limitation_codes": limitations,
    }


def _pick_value(
    source: dict[str, str],
    *,
    supported_depth: int,
    snapshot_as_of: datetime,
) -> dict[str, object]:
    asset_key = source["asset_key"].strip()
    asset_type = source["asset_type"].strip()
    if (
        not asset_key
        or len(asset_key) > 128
        or not re.fullmatch(r"^[a-z0-9][a-z0-9._-]*$", asset_key)
    ):
        raise ValueError("asset_key is not supported")
    if asset_type not in {"current_draft_pick", "future_round"}:
        raise ValueError("asset_type is not supported")
    overall_pick = _strict_int(source["overall_pick"], "overall_pick", optional=True)
    season_offset = _strict_int(
        source["season_offset"],
        "season_offset",
        optional=True,
    )
    round_number = _strict_int(source["round"], "round", optional=True)
    if asset_type == "current_draft_pick":
        if (
            overall_pick is None
            or overall_pick < 1
            or overall_pick > supported_depth
            or season_offset is not None
            or round_number is not None
        ):
            raise ValueError("current-draft pick coordinates are invalid")
    elif (
        overall_pick is not None
        or season_offset is None
        or not 1 <= season_offset <= 5
        or round_number is None
        or not 1 <= round_number <= 10
    ):
        raise ValueError("future-round coordinates are invalid")

    value_low = _strict_int(source["value_low"], "value_low", optional=False)
    value_high = _strict_int(source["value_high"], "value_high", optional=False)
    assert value_low is not None and value_high is not None
    if value_low > value_high or value_high > 1_000_000:
        raise ValueError("pick-value range is invalid")
    evidence_as_of = _parse_timestamp(
        source["evidence_as_of"],
        "evidence_as_of",
    )
    if evidence_as_of > snapshot_as_of or evidence_as_of > datetime.now(UTC):
        raise ValueError("evidence_as_of cannot be in the future")
    return {
        "asset_key": asset_key,
        "asset_type": asset_type,
        "overall_pick": overall_pick,
        "season_offset": season_offset,
        "round": round_number,
        "value_low": value_low,
        "value_high": value_high,
        "evidence_as_of": _utc_text(evidence_as_of),
        "limitation_codes": _limitation_codes(source["limitation_codes"]),
    }


def _validate_monotonic_curve(values: list[dict[str, object]]) -> None:
    current = sorted(
        (
            value
            for value in values
            if value["asset_type"] == "current_draft_pick"
        ),
        key=lambda value: int(value["overall_pick"]),
    )
    for previous, following in zip(current, current[1:], strict=False):
        if (
            int(previous["value_low"]) < int(following["value_low"])
            or int(previous["value_high"]) < int(following["value_high"])
        ):
            raise ValueError("current-draft pick values are not monotonic")

    season_offsets = {
        int(value["season_offset"])
        for value in values
        if value["asset_type"] == "future_round"
    }
    for season_offset in season_offsets:
        future = sorted(
            (
                value
                for value in values
                if value["asset_type"] == "future_round"
                and value["season_offset"] == season_offset
            ),
            key=lambda value: int(value["round"]),
        )
        for previous, following in zip(future, future[1:], strict=False):
            if (
                int(previous["value_low"]) < int(following["value_low"])
                or int(previous["value_high"]) < int(following["value_high"])
            ):
                raise ValueError("future-round pick values are not monotonic")


def _candidate_ids(
    session: Session,
    *,
    display_name: str,
    position: str,
    team: str | None,
) -> list[str]:
    rows = find_name_candidates(
        session,
        normalize_search_name(display_name),
        position,
    )
    if team is not None:
        rows = [row for row in rows if row.team in {None, team}]
    return [row.id for row in rows[:10]]


def _map_player_signal(
    session: Session,
    *,
    row_number: int,
    namespace: str,
    signal: dict[str, object],
) -> PreviewPlayerRow:
    source_key = str(signal["source_player_key"])
    display_name = str(signal["display_name"])
    position = str(signal["position"])
    team = signal["team"] if isinstance(signal["team"], str) else None
    formula_like = source_key.startswith(FORMULA_PREFIXES) or display_name.startswith(
        FORMULA_PREFIXES
    )
    exact_mapping = get_external_mapping(session, namespace, source_key)
    candidate_ids = _candidate_ids(
        session,
        display_name=display_name,
        position=position,
        team=team,
    )

    if formula_like:
        status = "review_required"
        resolved_player_id = None
        if exact_mapping is not None and exact_mapping.player_id not in candidate_ids:
            candidate_ids.insert(0, exact_mapping.player_id)
        reason_code = "IMPORT.ALERT_EVIDENCE.FORMULA_LIKE_IDENTITY"
        limitations = ["FORMULA_LIKE_IDENTITY"]
    elif exact_mapping is not None:
        status = "matched"
        resolved_player_id = exact_mapping.player_id
        candidate_ids = [exact_mapping.player_id]
        reason_code = "IMPORT.ALERT_EVIDENCE.EXACT_MAPPING"
        limitations = []
    elif len(candidate_ids) == 1:
        status = "review_required"
        resolved_player_id = None
        reason_code = "IMPORT.ALERT_EVIDENCE.CONFIRM_IDENTITY"
        limitations = []
    elif candidate_ids:
        status = "review_required"
        resolved_player_id = None
        reason_code = "IMPORT.ALERT_EVIDENCE.AMBIGUOUS_IDENTITY"
        limitations = ["AMBIGUOUS_PLAYER_MAPPING"]
    else:
        status = "unmatched"
        resolved_player_id = None
        reason_code = "IMPORT.ALERT_EVIDENCE.UNMATCHED_PLAYER"
        limitations = ["UNMATCHED_PLAYER"]

    return PreviewPlayerRow(
        id=str(uuid4()),
        row_number=row_number,
        signal=signal,
        source_player_key=source_key,
        display_name=display_name,
        position=position,
        team=team,
        status=status,
        resolved_player_id=resolved_player_id,
        candidate_player_ids=candidate_ids,
        reason_code=reason_code,
        limitation_codes=limitations,
        initial_status=status,
        initial_resolved_player_id=resolved_player_id,
        initial_candidate_player_ids=list(candidate_ids),
        initial_reason_code=reason_code,
    )


def _canonical_hash(snapshot: dict[str, object]) -> str:
    hashable = json.loads(json.dumps(snapshot))
    source = hashable.get("source")
    if isinstance(source, dict):
        source.pop("private_reference", None)
    canonical = json.dumps(
        hashable,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _format_from_request(request: AlertEvidencePreviewRequest) -> dict[str, object]:
    metadata = request.metadata
    return {
        "sport": "nfl",
        "league_type": metadata.league_type,
        "draft_purpose": metadata.draft_purpose,
        "team_count": metadata.team_count,
        "draft_format": metadata.draft_format,
        "third_round_reversal": metadata.third_round_reversal,
        "rounds": metadata.round_count,
        "qb_mode": metadata.quarterback_mode,
        "reception_scoring": metadata.reception_scoring,
        "te_premium": metadata.tight_end_premium,
    }


def _worst_freshness(states: list[str]) -> str:
    return max(states, key=FRESHNESS_ORDER.get) if states else "expired"


def _freshness(
    timestamps: list[str],
    *,
    fresh: int,
    aging: int,
    stale: int,
) -> str:
    now = datetime.now(UTC)
    states = [
        elapsed_freshness(
            evidence_as_of=_parse_timestamp(timestamp, "evidence_as_of"),
            evaluated_at=now,
            fresh_through_days=fresh,
            aging_through_days=aging,
            stale_through_days=stale,
        )
        for timestamp in timestamps
    ]
    return _worst_freshness(states)


def _snapshot_freshness(snapshot: dict[str, object]) -> dict[str, str]:
    player_signals = list(snapshot.get("player_signals", []))
    pick_values = list(snapshot.get("pick_values", []))
    expected = [
        str(signal["evidence_as_of"])
        for signal in player_signals
        if isinstance(signal, dict) and signal.get("expected_pick") is not None
    ]
    market = [
        str(signal["evidence_as_of"])
        for signal in player_signals
        if isinstance(signal, dict) and signal.get("market_band") is not None
    ]
    production = [
        str(signal["evidence_as_of"])
        for signal in player_signals
        if isinstance(signal, dict)
        and signal.get("win_now_production_band") is not None
    ]
    picks = [
        str(value["evidence_as_of"])
        for value in pick_values
        if isinstance(value, dict)
    ]
    return {
        "expected_selection": _freshness(expected, fresh=7, aging=21, stale=45),
        "dynasty_market": _freshness(market, fresh=7, aging=21, stale=45),
        "pick_value": _freshness(picks, fresh=30, aging=60, stale=90),
        "in_season_production": _freshness(
            production,
            fresh=14,
            aging=30,
            stale=60,
        ),
    }


def preview_alert_evidence(
    session: Session,
    store: AlertEvidencePreviewStore,
    request: AlertEvidencePreviewRequest,
) -> AlertEvidencePreviewRead:
    snapshot_as_of = request.metadata.as_of.astimezone(UTC)
    if snapshot_as_of > datetime.now(UTC):
        raise _error(
            "VALIDATION.ALERT_EVIDENCE.FUTURE_TIMESTAMP",
            "The evidence as-of timestamp is in the future.",
            "Use the source's actual UTC as-of timestamp.",
        )
    player_sources = _bounded_csv_rows(
        request.player_csv_text,
        filename=request.player_filename,
        headers=PLAYER_HEADERS,
        byte_limit=2 * 1024 * 1024,
        row_limit=1000,
    )
    if not player_sources:
        raise _error(
            "IMPORT.ALERT_EVIDENCE.NO_USABLE_PLAYERS",
            "The player-signals file has no data rows.",
            "Add at least one documented player-signal row.",
        )
    source_keys = [row["source_player_key"].strip() for row in player_sources]
    if len(source_keys) != len(set(source_keys)):
        raise _error(
            "VALIDATION.ALERT_EVIDENCE.DUPLICATE_PLAYER",
            "The player-signals file repeats a source player key.",
            "Keep one row per source player key.",
        )

    preview_rows: list[PreviewPlayerRow] = []
    valid_signals: list[dict[str, object]] = []
    warnings: set[str] = set()
    limitations: set[str] = set()
    for row_number, source in enumerate(player_sources, start=2):
        try:
            signal = _player_signal(
                source,
                supported_depth=request.metadata.supported_draft_depth,
                snapshot_as_of=snapshot_as_of,
            )
        except ValueError as exc:
            source_key = source["source_player_key"].strip()[:200]
            preview_rows.append(
                PreviewPlayerRow(
                    id=str(uuid4()),
                    row_number=row_number,
                    signal=None,
                    source_player_key=source_key or f"row-{row_number}",
                    display_name=(
                        " ".join(source["display_name"].strip().split())[:200]
                        or "(invalid row)"
                    ),
                    position=source["position"].strip().upper()[:16],
                    team=normalize_team(source["team"]),
                    status="invalid",
                    resolved_player_id=None,
                    candidate_player_ids=[],
                    reason_code="VALIDATION.ALERT_EVIDENCE.INVALID_ROW",
                    limitation_codes=["INVALID_PLAYER_ROW"],
                    initial_status="invalid",
                    initial_resolved_player_id=None,
                    initial_candidate_player_ids=[],
                    initial_reason_code="VALIDATION.ALERT_EVIDENCE.INVALID_ROW",
                )
            )
            warnings.add(f"Player row {row_number} is invalid: {exc}.")
            limitations.add("INVALID_PLAYER_ROW")
            continue
        valid_signals.append(signal)
        mapped = _map_player_signal(
            session,
            row_number=row_number,
            namespace=request.metadata.source_namespace,
            signal=signal,
        )
        preview_rows.append(mapped)
        limitations.update(mapped.limitation_codes)

    pick_values: list[dict[str, object]] = []
    if request.pick_csv_text is not None and request.pick_filename is not None:
        pick_sources = _bounded_csv_rows(
            request.pick_csv_text,
            filename=request.pick_filename,
            headers=PICK_HEADERS,
            byte_limit=1024 * 1024,
            row_limit=500,
        )
        asset_keys = [row["asset_key"].strip() for row in pick_sources]
        if len(asset_keys) != len(set(asset_keys)):
            raise _error(
                "VALIDATION.ALERT_EVIDENCE.INVALID_CURVE",
                "The pick-values file repeats an asset key.",
                "Keep one row per pick-only asset key.",
            )
        try:
            pick_values = [
                _pick_value(
                    source,
                    supported_depth=request.metadata.supported_draft_depth,
                    snapshot_as_of=snapshot_as_of,
                )
                for source in pick_sources
            ]
            _validate_monotonic_curve(pick_values)
        except ValueError as exc:
            raise _error(
                "VALIDATION.ALERT_EVIDENCE.INVALID_CURVE",
                f"The pick-value curve is invalid: {exc}.",
                "Correct the ranged pick-only curve and preview it again.",
            ) from exc

    valid_signals.sort(key=lambda signal: str(signal["source_player_key"]))
    pick_values.sort(
        key=lambda value: (
            0 if value["asset_type"] == "current_draft_pick" else 1,
            int(value["overall_pick"] or 0),
            int(value["season_offset"] or 0),
            int(value["round"] or 0),
        )
    )
    snapshot_key = request.metadata.snapshot_key or (
        f"{request.metadata.source_namespace}-{snapshot_as_of.date().isoformat()}"
    )
    source: dict[str, object] = {
        "label": request.metadata.source_label.strip(),
        "kind": request.metadata.source_kind,
        "namespace": request.metadata.source_namespace,
        "permitted_use_confirmed": request.metadata.permitted_use_confirmed,
    }
    if request.metadata.private_source_reference is not None:
        source["private_reference"] = request.metadata.private_source_reference
    snapshot: dict[str, object] = {
        "schema_version": 1,
        "snapshot_key": snapshot_key,
        "source": source,
        "as_of": _utc_text(snapshot_as_of),
        "format": _format_from_request(request),
        "supported_draft_depth": request.metadata.supported_draft_depth,
        "player_signals": valid_signals,
        "pick_values": pick_values,
    }
    if not request.metadata.permitted_use_confirmed:
        warnings.add("Permitted-use confirmation is required before commit.")
        limitations.add("PERMISSION_UNCONFIRMED")
    preview = AlertEvidencePreview(
        id=str(uuid4()),
        status="preview",
        content_hash=_canonical_hash(snapshot),
        snapshot=snapshot,
        rows=preview_rows,
        warnings=sorted(warnings),
        limitation_codes=sorted(limitations),
    )
    store.add(preview)
    return _preview_to_read(session, preview)


def _candidate_read(session: Session, player_id: str) -> AlertEvidenceCandidateRead | None:
    row = get_player_row(session, player_id)
    if row is None:
        return None
    return AlertEvidenceCandidateRead(
        id=row.id,
        display_name=row.display_name,
        position=row.primary_position,
        team=row.team,
    )


def _preview_to_read(
    session: Session,
    preview: AlertEvidencePreview,
) -> AlertEvidencePreviewRead:
    counts = {
        status: sum(row.status == status for row in preview.rows)
        for status in (
            "matched",
            "review_required",
            "unmatched",
            "ignored",
            "invalid",
        )
    }
    rows = []
    for row in preview.rows:
        candidates = [
            candidate
            for player_id in row.candidate_player_ids
            if (candidate := _candidate_read(session, player_id)) is not None
        ]
        rows.append(
            AlertEvidenceMappingRowRead(
                id=row.id,
                row_number=row.row_number,
                source_player_key=row.source_player_key,
                display_name=row.display_name,
                position=row.position,
                team=row.team,
                status=row.status,
                resolved_player_id=row.resolved_player_id,
                candidates=candidates,
                reason_code=row.reason_code,
                limitation_codes=sorted(set(row.limitation_codes)),
            )
        )
    snapshot = preview.snapshot
    source = snapshot["source"]
    format_shape = snapshot["format"]
    assert isinstance(source, dict) and isinstance(format_shape, dict)
    signals = list(snapshot["player_signals"])
    pick_values = list(snapshot["pick_values"])
    expected_available = any(
        isinstance(signal, dict) and signal.get("expected_pick") is not None
        for signal in signals
    )
    return AlertEvidencePreviewRead(
        schema_version=1,
        id=preview.id,
        status=preview.status,
        content_hash=preview.content_hash,
        source=AlertEvidenceSourceSummary(
            label=str(source["label"]),
            kind=source["kind"],
            namespace=str(source["namespace"]),
            permitted_use_confirmed=bool(source["permitted_use_confirmed"]),
            as_of=str(snapshot["as_of"]),
        ),
        format=AlertEvidenceFormatSummary(**format_shape),
        supported_draft_depth=int(snapshot["supported_draft_depth"]),
        freshness_states=_snapshot_freshness(snapshot),
        total_player_count=len(preview.rows),
        valid_player_count=len(signals),
        matched_player_count=counts["matched"],
        review_required_player_count=counts["review_required"],
        unmatched_player_count=counts["unmatched"],
        ignored_player_count=counts["ignored"],
        invalid_player_count=counts["invalid"],
        total_pick_value_count=len(pick_values),
        valid_pick_value_count=len(pick_values),
        expected_selection_available=expected_available,
        pick_curve_available=bool(pick_values),
        warnings=preview.warnings,
        limitation_codes=preview.limitation_codes,
        rows=rows,
        committed_snapshot_id=preview.committed_snapshot_id,
    )


def read_alert_evidence_preview(
    session: Session,
    store: AlertEvidencePreviewStore,
    preview_id: str,
) -> AlertEvidencePreviewRead:
    preview = store.get(preview_id)
    if preview is None:
        raise _error(
            "IMPORT.ALERT_EVIDENCE.PREVIEW_NOT_FOUND",
            "That evidence preview no longer exists.",
            "Start a new local preview.",
            status_code=404,
        )
    return _preview_to_read(session, preview)


def decide_alert_evidence_mapping(
    session: Session,
    store: AlertEvidencePreviewStore,
    preview_id: str,
    row_id: str,
    decision: AlertEvidenceMappingDecisionRequest,
) -> AlertEvidencePreviewRead:
    preview = store.get(preview_id)
    if preview is None:
        raise _error(
            "IMPORT.ALERT_EVIDENCE.PREVIEW_NOT_FOUND",
            "That evidence preview no longer exists.",
            "Start a new local preview.",
            status_code=404,
        )
    if preview.status != "preview":
        raise _error(
            "IMPORT.ALERT_EVIDENCE.PREVIEW_CHANGED",
            "That evidence preview is already committed.",
            "Start a new preview to make different mapping decisions.",
            status_code=409,
        )
    row = next((item for item in preview.rows if item.id == row_id), None)
    if row is None:
        raise _error(
            "IMPORT.ALERT_EVIDENCE.MAPPING_REQUIRED",
            "That mapping row is not part of this preview.",
            "Reload the preview and choose a visible mapping row.",
            status_code=404,
        )
    if decision.decision == "confirm":
        assert decision.player_id is not None
        player = get_player_row(session, decision.player_id)
        if player is None:
            raise _error(
                "IMPORT.ALERT_EVIDENCE.MAPPING_REQUIRED",
                "The selected canonical player no longer exists.",
                "Choose another canonical player.",
                status_code=409,
            )
        row.status = "matched"
        row.resolved_player_id = player.id
        row.candidate_player_ids = [player.id]
        row.reason_code = "IMPORT.ALERT_EVIDENCE.MANUAL_MAPPING"
        row.limitation_codes = [
            code
            for code in row.limitation_codes
            if code not in {"AMBIGUOUS_PLAYER_MAPPING", "UNMATCHED_PLAYER"}
        ]
    elif decision.decision in {"ignore", "reject"}:
        row.status = "ignored"
        row.resolved_player_id = None
        row.reason_code = (
            "IMPORT.ALERT_EVIDENCE.MANUAL_IGNORE"
            if decision.decision == "ignore"
            else "IMPORT.ALERT_EVIDENCE.MAPPING_REJECTED"
        )
    else:
        row.status = row.initial_status
        row.resolved_player_id = row.initial_resolved_player_id
        row.candidate_player_ids = list(row.initial_candidate_player_ids)
        row.reason_code = row.initial_reason_code
    return _preview_to_read(session, preview)


def _commit_transaction(session: Session) -> None:
    session.commit()


def commit_alert_evidence(
    session: Session,
    store: AlertEvidencePreviewStore,
    preview_id: str,
    request: AlertEvidenceCommitRequest,
) -> AlertEvidenceCommitResponse:
    preview = store.get(preview_id)
    if preview is None:
        raise _error(
            "IMPORT.ALERT_EVIDENCE.PREVIEW_NOT_FOUND",
            "That evidence preview no longer exists.",
            "Start a new local preview.",
            status_code=404,
        )
    if request.content_hash != preview.content_hash:
        raise _error(
            "IMPORT.ALERT_EVIDENCE.PREVIEW_CHANGED",
            "The preview hash does not match the accepted evidence.",
            "Preview the current files again before committing.",
            status_code=409,
        )
    source = preview.snapshot["source"]
    assert isinstance(source, dict)
    if (
        not request.permitted_use_confirmed
        or not source["permitted_use_confirmed"]
    ):
        raise _error(
            "IMPORT.ALERT_EVIDENCE.PERMISSION_UNCONFIRMED",
            "Permitted use has not been confirmed for this evidence.",
            "Confirm the source terms and create a permission-confirmed preview.",
            status_code=409,
        )
    if preview.committed_snapshot_id is not None:
        return AlertEvidenceCommitResponse(
            snapshot=read_alert_evidence_snapshot(
                session,
                preview.committed_snapshot_id,
            ),
            idempotent=True,
        )

    existing = session.scalar(
        select(AlertEvidenceSnapshotRow).where(
            AlertEvidenceSnapshotRow.content_hash == preview.content_hash
        )
    )
    if existing is not None:
        preview.status = "committed"
        preview.committed_snapshot_id = existing.id
        return AlertEvidenceCommitResponse(
            snapshot=_snapshot_summary(session, existing),
            idempotent=True,
        )

    invalid_rows = [row for row in preview.rows if row.status == "invalid"]
    if invalid_rows:
        raise _error(
            "VALIDATION.ALERT_EVIDENCE.INVALID_ROW",
            "One or more player rows are still invalid.",
            "Ignore invalid rows or correct the source file and preview it again.",
            status_code=409,
        )
    mapped_rows = [
        row
        for row in preview.rows
        if row.status == "matched"
        and row.resolved_player_id is not None
        and row.signal is not None
    ]
    if not any(
        isinstance(row.signal, dict) and row.signal.get("expected_pick") is not None
        for row in mapped_rows
    ):
        raise _error(
            "IMPORT.ALERT_EVIDENCE.NO_USABLE_PLAYERS",
            "No mapped player has a usable expected-selection window.",
            "Confirm at least one exact player mapping with an expected-pick range.",
            status_code=409,
        )
    resolved_ids = [row.resolved_player_id for row in mapped_rows]
    if len(resolved_ids) != len(set(resolved_ids)):
        raise _error(
            "IMPORT.ALERT_EVIDENCE.MAPPING_REQUIRED",
            "More than one source row maps to the same canonical player.",
            "Keep or confirm only one source row for each canonical player.",
            status_code=409,
        )

    now = utc_now_text()
    snapshot_id = str(uuid4())
    format_shape = preview.snapshot["format"]
    assert isinstance(format_shape, dict)
    snapshot_row = AlertEvidenceSnapshotRow(
        id=snapshot_id,
        schema_version=1,
        source_label=str(source["label"]),
        source_kind=str(source["kind"]),
        source_namespace=str(source["namespace"]),
        permitted_use_confirmed=True,
        private_source_reference=(
            str(source["private_reference"])
            if source.get("private_reference") is not None
            else None
        ),
        format_json=json.dumps(format_shape, separators=(",", ":"), sort_keys=True),
        supported_draft_depth=int(preview.snapshot["supported_draft_depth"]),
        source_as_of=str(preview.snapshot["as_of"]),
        imported_at=now,
        content_hash=preview.content_hash,
        status="committed",
        created_at=now,
    )
    try:
        session.add(snapshot_row)
        for mapped in mapped_rows:
            assert mapped.signal is not None
            signal = mapped.signal
            expected = signal["expected_pick"]
            field_timestamps = {
                field_name: signal["evidence_as_of"]
                for field_name in (
                    "expected_pick",
                    "market_band",
                    "win_now_production_band",
                    "age_risk_band",
                )
                if signal[field_name] is not None
            }
            session.add(
                AlertPlayerSignalRow(
                    id=str(uuid4()),
                    evidence_snapshot_id=snapshot_id,
                    player_id=mapped.resolved_player_id,
                    expected_pick_low=(
                        int(expected["low"]) if isinstance(expected, dict) else None
                    ),
                    expected_pick_high=(
                        int(expected["high"]) if isinstance(expected, dict) else None
                    ),
                    market_band=signal["market_band"],
                    win_now_production_band=signal["win_now_production_band"],
                    age_risk_band=signal["age_risk_band"],
                    field_timestamps_json=json.dumps(
                        field_timestamps,
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    evidence_as_of=str(signal["evidence_as_of"]),
                    limitation_codes_json=json.dumps(signal["limitation_codes"]),
                    private_source_record_reference=mapped.source_player_key,
                )
            )
            if mapped.initial_status != "matched":
                ensure_external_mapping(
                    session,
                    mapped.resolved_player_id,
                    str(source["namespace"]),
                    mapped.source_player_key,
                    manual=True,
                )
        for value in preview.snapshot["pick_values"]:
            assert isinstance(value, dict)
            session.add(
                AlertPickValueSignalRow(
                    id=str(uuid4()),
                    evidence_snapshot_id=snapshot_id,
                    asset_key=str(value["asset_key"]),
                    asset_type=str(value["asset_type"]),
                    season_offset=value["season_offset"],
                    round_number=value["round"],
                    overall_pick=value["overall_pick"],
                    value_low=int(value["value_low"]),
                    value_high=int(value["value_high"]),
                    evidence_as_of=str(value["evidence_as_of"]),
                    limitation_codes_json=json.dumps(value["limitation_codes"]),
                )
            )
        _commit_transaction(session)
    except Exception as exc:
        session.rollback()
        if isinstance(exc, HubError):
            raise
        raise _error(
            "IMPORT.ALERT_EVIDENCE.COMMIT_FAILED",
            "The evidence snapshot could not be committed.",
            "Review the preview and try the explicit commit again.",
            status_code=500,
        ) from exc

    preview.status = "committed"
    preview.committed_snapshot_id = snapshot_id
    return AlertEvidenceCommitResponse(
        snapshot=_snapshot_summary(session, snapshot_row),
        idempotent=False,
    )


def _safe_limitation_codes(
    player_rows: list[AlertPlayerSignalRow],
    pick_rows: list[AlertPickValueSignalRow],
) -> list[str]:
    codes: set[str] = set()
    for row in player_rows:
        codes.update(json.loads(row.limitation_codes_json))
    for row in pick_rows:
        codes.update(json.loads(row.limitation_codes_json))
    return sorted(codes)


def _snapshot_summary(
    session: Session,
    snapshot: AlertEvidenceSnapshotRow,
) -> AlertEvidenceSnapshotSummaryRead:
    player_rows = list(
        session.scalars(
            select(AlertPlayerSignalRow).where(
                AlertPlayerSignalRow.evidence_snapshot_id == snapshot.id
            )
        )
    )
    pick_rows = list(
        session.scalars(
            select(AlertPickValueSignalRow).where(
                AlertPickValueSignalRow.evidence_snapshot_id == snapshot.id
            )
        )
    )
    normalized = {
        "player_signals": [
            {
                "expected_pick": (
                    {
                        "low": row.expected_pick_low,
                        "high": row.expected_pick_high,
                    }
                    if row.expected_pick_low is not None
                    else None
                ),
                "market_band": row.market_band,
                "win_now_production_band": row.win_now_production_band,
                "evidence_as_of": row.evidence_as_of,
            }
            for row in player_rows
        ],
        "pick_values": [
            {"evidence_as_of": row.evidence_as_of} for row in pick_rows
        ],
    }
    expected_count = sum(row.expected_pick_low is not None for row in player_rows)
    return AlertEvidenceSnapshotSummaryRead(
        id=snapshot.id,
        schema_version=snapshot.schema_version,
        source_label=snapshot.source_label,
        source_kind=snapshot.source_kind,
        source_namespace=snapshot.source_namespace,
        source_as_of=snapshot.source_as_of,
        imported_at=snapshot.imported_at,
        content_hash=snapshot.content_hash,
        status=snapshot.status,
        format=AlertEvidenceFormatSummary(**json.loads(snapshot.format_json)),
        supported_draft_depth=snapshot.supported_draft_depth,
        freshness_states=_snapshot_freshness(normalized),
        mapped_player_count=len(player_rows),
        expected_selection_count=expected_count,
        pick_value_count=len(pick_rows),
        expected_selection_available=expected_count > 0,
        pick_curve_available=bool(pick_rows),
        compatibility_state="not_evaluated",
        limitation_codes=_safe_limitation_codes(player_rows, pick_rows),
    )


def list_alert_evidence_snapshots(
    session: Session,
    *,
    limit: int,
    offset: int,
) -> AlertEvidenceSnapshotListResponse:
    total = session.scalar(
        select(func.count()).select_from(AlertEvidenceSnapshotRow)
    ) or 0
    rows = list(
        session.scalars(
            select(AlertEvidenceSnapshotRow)
            .order_by(
                AlertEvidenceSnapshotRow.imported_at.desc(),
                AlertEvidenceSnapshotRow.id,
            )
            .limit(limit)
            .offset(offset)
        )
    )
    return AlertEvidenceSnapshotListResponse(
        items=[_snapshot_summary(session, row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def read_alert_evidence_snapshot(
    session: Session,
    snapshot_id: str,
) -> AlertEvidenceSnapshotSummaryRead:
    row = session.get(AlertEvidenceSnapshotRow, snapshot_id)
    if row is None:
        raise _error(
            "IMPORT.ALERT_EVIDENCE.SNAPSHOT_NOT_FOUND",
            "That committed evidence snapshot does not exist.",
            "Choose a snapshot from the evidence list.",
            status_code=404,
        )
    return _snapshot_summary(session, row)
