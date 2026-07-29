from __future__ import annotations

import csv
import hashlib
import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

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
LIMITATION_CODE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")
FORBIDDEN_PUBLIC_MARKERS = (
    "sleeper",
    "keeptradecut",
    "fantasycalc",
    "dynastyprocess",
    "espn",
    "yahoo",
    "myfantasyleague",
)
SYNTHETIC_CONTENT_HASH = (
    "fc93019416c2b31d9ce0598b1fa278a530df2022ee4e74f89f14161bbcc26274"
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        assert reader.fieldnames is not None
        return reader.fieldnames, list(reader)


def _content_hash(snapshot: dict[str, Any]) -> str:
    content = deepcopy(snapshot)
    content["source"].pop("private_reference", None)
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _optional_text(value: str) -> str | None:
    cleaned = value.strip()
    return cleaned or None


def _optional_int(value: str) -> int | None:
    cleaned = value.strip()
    return int(cleaned) if cleaned else None


def _limitation_codes(value: str) -> list[str]:
    return sorted({part.strip() for part in value.split("|") if part.strip()})


def _player_signal_from_csv(row: dict[str, str]) -> dict[str, Any]:
    low = _optional_int(row["expected_pick_low"])
    high = _optional_int(row["expected_pick_high"])
    expected_pick = None if low is None and high is None else {"low": low, "high": high}
    return {
        "source_player_key": row["source_player_key"].strip(),
        "display_name": row["display_name"].strip(),
        "position": row["position"].strip(),
        "team": _optional_text(row["team"]),
        "expected_pick": expected_pick,
        "market_band": _optional_text(row["market_band"]),
        "win_now_production_band": _optional_text(
            row["win_now_production_band"]
        ),
        "age_risk_band": _optional_text(row["age_risk_band"]),
        "evidence_as_of": row["evidence_as_of"].strip(),
        "limitation_codes": _limitation_codes(row["limitation_codes"]),
    }


def _pick_value_from_csv(row: dict[str, str]) -> dict[str, Any]:
    return {
        "asset_key": row["asset_key"].strip(),
        "asset_type": row["asset_type"].strip(),
        "overall_pick": _optional_int(row["overall_pick"]),
        "season_offset": _optional_int(row["season_offset"]),
        "round": _optional_int(row["round"]),
        "value_low": int(row["value_low"]),
        "value_high": int(row["value_high"]),
        "evidence_as_of": row["evidence_as_of"].strip(),
        "limitation_codes": _limitation_codes(row["limitation_codes"]),
    }


def _assert_monotonic(rows: list[dict[str, Any]], key: str) -> None:
    ordered = sorted(rows, key=lambda row: row[key])
    for previous, current in zip(ordered, ordered[1:], strict=False):
        assert previous["value_low"] >= current["value_low"]
        assert previous["value_high"] >= current["value_high"]


def _assert_semantic_contract(snapshot: dict[str, Any]) -> None:
    supported_depth = snapshot["supported_draft_depth"]
    assert [
        signal["source_player_key"] for signal in snapshot["player_signals"]
    ] == sorted(
        signal["source_player_key"] for signal in snapshot["player_signals"]
    )
    player_keys: set[str] = set()
    for signal in snapshot["player_signals"]:
        key = signal["source_player_key"]
        assert key not in player_keys
        player_keys.add(key)
        expected_pick = signal["expected_pick"]
        if expected_pick is not None:
            assert expected_pick["low"] <= expected_pick["high"]
            assert expected_pick["high"] <= supported_depth
        codes = signal["limitation_codes"]
        assert codes == sorted(set(codes))
        assert all(LIMITATION_CODE.fullmatch(code) for code in codes)

    asset_keys: set[str] = set()
    for value in snapshot["pick_values"]:
        key = value["asset_key"]
        assert key not in asset_keys
        asset_keys.add(key)
        assert value["value_low"] <= value["value_high"]
        if value["asset_type"] == "current_draft_pick":
            assert value["overall_pick"] <= supported_depth
        codes = value["limitation_codes"]
        assert codes == sorted(set(codes))
        assert all(LIMITATION_CODE.fullmatch(code) for code in codes)

    expected_pick_value_order = sorted(
        snapshot["pick_values"],
        key=lambda value: (
            0 if value["asset_type"] == "current_draft_pick" else 1,
            value["overall_pick"] or 0,
            value["season_offset"] or 0,
            value["round"] or 0,
        ),
    )
    assert snapshot["pick_values"] == expected_pick_value_order
    current_picks = [
        value
        for value in snapshot["pick_values"]
        if value["asset_type"] == "current_draft_pick"
    ]
    _assert_monotonic(current_picks, "overall_pick")
    season_offsets = {
        value["season_offset"]
        for value in snapshot["pick_values"]
        if value["asset_type"] == "future_round"
    }
    for season_offset in season_offsets:
        future_rounds = [
            value
            for value in snapshot["pick_values"]
            if value["asset_type"] == "future_round"
            and value["season_offset"] == season_offset
        ]
        _assert_monotonic(future_rounds, "round")


def test_alert_evidence_schemas_and_public_fixtures_are_valid() -> None:
    root = _project_root()
    evidence_schema = _read_json(
        root / "docs" / "schemas" / "alert-evidence-snapshot.schema.json"
    )
    freshness_schema = _read_json(
        root / "docs" / "schemas" / "alert-freshness-policy.schema.json"
    )
    snapshot = _read_json(
        root
        / "tests"
        / "fixtures"
        / "alert_evidence"
        / "entropy-alert-evidence.synthetic.json"
    )
    freshness = _read_json(
        root / "docs" / "requirements" / "alert-freshness-policy.v1.json"
    )

    Draft202012Validator.check_schema(evidence_schema)
    Draft202012Validator.check_schema(freshness_schema)
    Draft202012Validator(
        evidence_schema,
        format_checker=FormatChecker(),
    ).validate(snapshot)
    Draft202012Validator(freshness_schema).validate(freshness)

    assert snapshot["source"] == {
        "label": "Neighborhood Synthetic Market",
        "kind": "synthetic",
        "namespace": "sanitized_fixture",
        "permitted_use_confirmed": True,
    }
    assert "private_reference" not in snapshot["source"]
    assert _content_hash(snapshot) == SYNTHETIC_CONTENT_HASH
    with_private_reference = deepcopy(snapshot)
    with_private_reference["source"]["private_reference"] = "local-only-reference"
    assert _content_hash(with_private_reference) == SYNTHETIC_CONTENT_HASH
    serialized_public_fixture = json.dumps(snapshot).casefold()
    assert not any(
        marker in serialized_public_fixture for marker in FORBIDDEN_PUBLIC_MARKERS
    )


def test_csv_contract_normalizes_to_the_synthetic_snapshot() -> None:
    root = _project_root()
    fixture_root = root / "tests" / "fixtures" / "alert_evidence"
    snapshot = _read_json(
        fixture_root / "entropy-alert-evidence.synthetic.json"
    )
    player_headers, player_rows = _read_csv(
        fixture_root / "player-signals.synthetic.csv"
    )
    pick_headers, pick_rows = _read_csv(
        fixture_root / "pick-values.synthetic.csv"
    )

    assert player_headers == PLAYER_HEADERS
    assert pick_headers == PICK_HEADERS
    normalized_players = {
        signal["source_player_key"]: signal
        for signal in map(_player_signal_from_csv, player_rows)
    }
    normalized_values = {
        value["asset_key"]: value for value in map(_pick_value_from_csv, pick_rows)
    }
    assert len(normalized_players) == len(player_rows)
    assert len(normalized_values) == len(pick_rows)
    assert normalized_players == {
        signal["source_player_key"]: signal
        for signal in snapshot["player_signals"]
    }
    assert normalized_values == {
        value["asset_key"]: value for value in snapshot["pick_values"]
    }

    for row in [*player_rows, *pick_rows]:
        for value in row.values():
            assert not value.startswith(("=", "+", "-", "@"))


def test_synthetic_identity_curve_and_freshness_semantics() -> None:
    root = _project_root()
    snapshot = _read_json(
        root
        / "tests"
        / "fixtures"
        / "alert_evidence"
        / "entropy-alert-evidence.synthetic.json"
    )
    players = _read_json(
        root
        / "tests"
        / "fixtures"
        / "players"
        / "phase-1-players.sanitized.json"
    )
    freshness = _read_json(
        root / "docs" / "requirements" / "alert-freshness-policy.v1.json"
    )

    _assert_semantic_contract(snapshot)
    player_by_external_id = {
        player["external_id"]: player for player in players["players"]
    }
    assert snapshot["source"]["namespace"] == players["players"][0]["provider"]
    for signal in snapshot["player_signals"]:
        player = player_by_external_id[signal["source_player_key"]]
        assert signal["display_name"] == player["name"]
        assert signal["position"] == player["position"]
        assert signal["team"] == player["team"]

    as_of = datetime.fromisoformat(snapshot["as_of"].replace("Z", "+00:00"))
    assert as_of <= datetime.now(UTC)
    for signal in snapshot["player_signals"]:
        evidence_as_of = datetime.fromisoformat(
            signal["evidence_as_of"].replace("Z", "+00:00")
        )
        assert evidence_as_of <= as_of
    for value in snapshot["pick_values"]:
        evidence_as_of = datetime.fromisoformat(
            value["evidence_as_of"].replace("Z", "+00:00")
        )
        assert evidence_as_of <= as_of

    for rule in freshness["elapsed_day_rules"].values():
        assert (
            rule["fresh_through_days"]
            < rule["aging_through_days"]
            < rule["stale_through_days"]
        )
        assert rule["after_status"] == "expired"


def test_schema_and_semantic_failures_reject_unsafe_variants() -> None:
    root = _project_root()
    schema = _read_json(
        root / "docs" / "schemas" / "alert-evidence-snapshot.schema.json"
    )
    snapshot = _read_json(
        root
        / "tests"
        / "fixtures"
        / "alert_evidence"
        / "entropy-alert-evidence.synthetic.json"
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    unconfirmed = deepcopy(snapshot)
    unconfirmed["source"]["permitted_use_confirmed"] = False
    with pytest.raises(ValidationError):
        validator.validate(unconfirmed)

    player_asset = deepcopy(snapshot)
    player_asset["pick_values"][0]["player_id"] = "forbidden-player"
    with pytest.raises(ValidationError):
        validator.validate(player_asset)

    mixed_asset = deepcopy(snapshot)
    mixed_asset["pick_values"][0]["season_offset"] = 1
    with pytest.raises(ValidationError):
        validator.validate(mixed_asset)

    inverted_player_range = deepcopy(snapshot)
    inverted_player_range["player_signals"][0]["expected_pick"] = {
        "low": 20,
        "high": 10,
    }
    with pytest.raises(AssertionError):
        _assert_semantic_contract(inverted_player_range)

    inverted_curve = deepcopy(snapshot)
    inverted_curve["pick_values"][1]["value_low"] = 1100
    inverted_curve["pick_values"][1]["value_high"] = 1200
    with pytest.raises(AssertionError):
        _assert_semantic_contract(inverted_curve)
