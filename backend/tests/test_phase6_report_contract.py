from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from string import Formatter
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

EXPECTED_SECTION_KEYS = {
    "age_risk_profile",
    "draft_summary",
    "dynasty_market_context",
    "evidence_limits",
    "liquidity",
    "long_term_value",
    "personal_board_choice_moments",
    "player_fragility",
    "position_inventory",
    "recorded_alert_moments",
    "roster_concentration",
    "starter_coverage",
    "strategy_story",
    "year_one_production_context",
}
EXPECTED_FIXTURE_HASH = (
    "375fa48cd95bb2c325f7ed0c37b6fbcae38606f9dc095d2e16c41ab818423bce"
)
FORBIDDEN_PUBLIC_MARKERS = (
    "espn",
    "fantasycalc",
    "keeptradecut",
    "myfantasyleague",
    "sleeper",
    "yahoo",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _definitions() -> dict[str, Any]:
    return _read_json(
        _project_root()
        / "docs"
        / "requirements"
        / "post-draft-report-definitions.v1.json"
    )


def _fixtures() -> dict[str, Any]:
    return _read_json(
        _project_root()
        / "tests"
        / "fixtures"
        / "post_draft_reports"
        / "phase-6-report-v1.expected.json"
    )


def _canonical_fixture_hash(fixtures: dict[str, Any]) -> str:
    content = deepcopy(fixtures)
    content.pop("content_hash")
    canonical = json.dumps(
        content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _placeholders(template: str) -> list[str]:
    return sorted(
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name is not None
    )


def _evidence_result(
    covered_players: int,
    roster_players: int,
    evidence_state: str,
    definitions: dict[str, Any],
) -> tuple[int, str, str]:
    assert 0 <= covered_players <= roster_players
    coverage = definitions["evidence_coverage"]
    basis_points = covered_players * 10_000 // roster_players
    if evidence_state in coverage["blocking_evidence_states"]:
        return basis_points, "unavailable", "unavailable"
    if basis_points >= coverage["supported_minimum_basis_points"]:
        return (
            basis_points,
            coverage["supported_availability"],
            coverage["supported_confidence"],
        )
    if basis_points >= coverage["limited_minimum_basis_points"]:
        return (
            basis_points,
            coverage["limited_availability"],
            coverage["limited_confidence"],
        )
    return (
        basis_points,
        coverage["below_limited_availability"],
        coverage["unavailable_confidence"],
    )


def _concentration_result(
    total_user_picks: int,
    position_pick_counts: dict[str, int],
    unfilled_distinct_starter_positions: int,
    definitions: dict[str, Any],
) -> tuple[int, list[str]]:
    assert sum(position_pick_counts.values()) == total_user_picks
    rules = definitions["concentration"]
    maximum_basis_points = max(position_pick_counts.values()) * 10_000 // total_user_picks
    if maximum_basis_points <= rules["balanced_maximum_basis_points"]:
        share_band = "balanced_distribution"
    elif maximum_basis_points <= rules["highly_concentrated_above_basis_points"]:
        share_band = "concentrated"
    else:
        share_band = "highly_concentrated"

    bands = [share_band]
    if unfilled_distinct_starter_positions:
        if share_band == "balanced_distribution":
            bands = []
        bands.append("coverage_gap")
    return maximum_basis_points, bands


def _enumerate_maximum_assignments(
    slots: list[dict[str, Any]],
    roster: list[dict[str, Any]],
) -> list[list[tuple[int, int, str]]]:
    player_by_id = {player["canonical_player_id"]: player for player in roster}
    best_count = -1
    best: list[list[tuple[int, int, str]]] = []

    def visit(
        slot_index: int,
        used_players: set[str],
        edges: list[tuple[int, int, str]],
    ) -> None:
        nonlocal best_count, best
        if slot_index == len(slots):
            edge_count = len(edges)
            if edge_count > best_count:
                best_count = edge_count
                best = [edges.copy()]
            elif edge_count == best_count:
                best.append(edges.copy())
            return

        slot = slots[slot_index]
        visit(slot_index + 1, used_players, edges)
        for player_id, player in player_by_id.items():
            if player_id in used_players:
                continue
            if not set(player["fantasy_positions"]).intersection(
                slot["eligible_positions"]
            ):
                continue
            used_players.add(player_id)
            edges.append((slot["slot_order"], player["overall_pick"], player_id))
            visit(slot_index + 1, used_players, edges)
            edges.pop()
            used_players.remove(player_id)

    visit(0, set(), [])
    return best


def _assert_definition_semantics(definitions: dict[str, Any]) -> None:
    sections = definitions["section_registry"]
    section_keys = [section["section_key"] for section in sections]
    assert len(section_keys) == len(set(section_keys))
    assert set(section_keys) == EXPECTED_SECTION_KEYS
    assert definitions["availability_states"] == [
        "supported",
        "limited",
        "unavailable",
        "not_applicable",
    ]
    assert definitions["confidence_states"] == [
        "high",
        "medium",
        "low",
        "unavailable",
    ]

    templates = definitions["explanation_templates"]
    template_keys = [template["template_key"] for template in templates]
    assert len(template_keys) == len(set(template_keys))
    forbidden = [phrase.casefold() for phrase in definitions["forbidden_language"]]
    for template in templates:
        assert template["section_key"] in EXPECTED_SECTION_KEYS
        assert template["required_placeholders"] == _placeholders(template["template"])
        text = template["template"].casefold()
        assert not any(phrase in text for phrase in forbidden)


def _assert_starter_fixture_semantics(fixtures: dict[str, Any]) -> None:
    case = fixtures["starter_assignment_case"]
    slots = case["league_shape"]["starter_slots"]
    roster = case["roster"]
    expected = case["expected"]
    slot_orders = [slot["slot_order"] for slot in slots]
    player_ids = [player["canonical_player_id"] for player in roster]
    overall_picks = [player["overall_pick"] for player in roster]
    assert slot_orders == list(range(len(slots)))
    assert len(player_ids) == len(set(player_ids))
    assert len(overall_picks) == len(set(overall_picks))

    maximum_assignments = _enumerate_maximum_assignments(slots, roster)
    chosen = min(maximum_assignments)
    expected_edges = [
        (
            assignment["slot_order"],
            next(
                player["overall_pick"]
                for player in roster
                if player["canonical_player_id"] == assignment["canonical_player_id"]
            ),
            assignment["canonical_player_id"],
        )
        for assignment in expected["assignments"]
    ]
    assert expected["starter_slots_total"] == len(slots)
    assert expected["starter_slots_filled"] == len(chosen)
    assert expected["starter_coverage_basis_points"] == len(chosen) * 10_000 // len(slots)
    assert expected_edges == chosen

    assigned_player_ids = {edge[2] for edge in chosen}
    calculated_depth = {"QB": 0, "RB": 0, "WR": 0, "TE": 0}
    for player in roster:
        if player["canonical_player_id"] not in assigned_player_ids:
            calculated_depth[player["primary_position"]] += 1
    assert expected["depth_counts"] == calculated_depth

    player_by_slot: dict[int, set[str]] = {}
    for assignment in maximum_assignments:
        for slot_order, _, player_id in assignment:
            player_by_slot.setdefault(slot_order, set()).add(player_id)
    expected_ambiguous = [
        slot["slot_key"]
        for slot in slots
        if slot["slot_type"] in {"FLEX", "SUPER_FLEX"}
        and len(player_by_slot[slot["slot_order"]]) > 1
    ]
    assert expected["ambiguous_flex_slot_keys"] == expected_ambiguous


def test_phase6_schemas_definitions_and_expected_fixtures_are_valid() -> None:
    root = _project_root()
    definitions_schema = _read_json(
        root / "docs" / "schemas" / "post-draft-report-definitions.schema.json"
    )
    fixtures_schema = _read_json(
        root
        / "docs"
        / "schemas"
        / "post-draft-report-expected-fixtures.schema.json"
    )
    definitions = _definitions()
    fixtures = _fixtures()

    Draft202012Validator.check_schema(definitions_schema)
    Draft202012Validator.check_schema(fixtures_schema)
    Draft202012Validator(definitions_schema).validate(definitions)
    Draft202012Validator(fixtures_schema).validate(fixtures)
    _assert_definition_semantics(definitions)
    assert fixtures["content_hash"] == EXPECTED_FIXTURE_HASH
    assert _canonical_fixture_hash(fixtures) == EXPECTED_FIXTURE_HASH


def test_phase6_expected_boundary_cases_match_the_frozen_rules() -> None:
    definitions = _definitions()
    fixtures = _fixtures()

    for case in fixtures["evidence_coverage_cases"]:
        result = _evidence_result(
            case["covered_players"],
            case["roster_players"],
            case["evidence_state"],
            definitions,
        )
        assert result == (
            case["expected_basis_points"],
            case["expected_availability"],
            case["expected_confidence"],
        )

    coverage_by_key = {
        case["case_key"]: case for case in fixtures["evidence_coverage_cases"]
    }
    assert {
        key for key in coverage_by_key if key.startswith("usable_")
    } == {
        "usable_49_percent",
        "usable_50_percent",
        "usable_79_percent",
        "usable_80_percent",
    }

    for case in fixtures["concentration_cases"]:
        result = _concentration_result(
            case["total_user_picks"],
            case["position_pick_counts"],
            case["unfilled_distinct_starter_positions"],
            definitions,
        )
        assert result == (
            case["expected_maximum_share_basis_points"],
            case["expected_bands"],
        )

    concentration_by_key = {
        case["case_key"]: case for case in fixtures["concentration_cases"]
    }
    assert {
        key
        for key in concentration_by_key
        if key.startswith("exactly_")
    } == {
        "exactly_40_percent_full_coverage",
        "exactly_41_percent_full_coverage",
        "exactly_55_percent_full_coverage",
        "exactly_56_percent_full_coverage",
    }


def test_phase6_starter_assignment_fixture_is_maximal_stable_and_complete() -> None:
    _assert_starter_fixture_semantics(_fixtures())


def test_phase6_modes_unsupported_sections_and_explanations_are_safe() -> None:
    definitions = _definitions()
    fixtures = _fixtures()
    section_by_key = {
        section["section_key"]: section for section in definitions["section_registry"]
    }
    template_by_key = {
        template["template_key"]: template
        for template in definitions["explanation_templates"]
    }

    for case in fixtures["mode_cases"]:
        assert case["section_key"] == "strategy_story"
        assert case["section_key"] in section_by_key
    assert {
        (case["mode"], case["expected_availability"])
        for case in fixtures["mode_cases"]
    } == {("live", "not_applicable"), ("mock", "supported")}

    unavailable_keys = {
        case["section_key"] for case in fixtures["unsupported_section_cases"]
    }
    assert unavailable_keys == {"long_term_value", "liquidity", "player_fragility"}
    for section_key in unavailable_keys:
        assert section_by_key[section_key]["availability_rule"] == "always_unavailable_v1"

    forbidden = [phrase.casefold() for phrase in definitions["forbidden_language"]]
    for case in fixtures["explanation_cases"]:
        template = template_by_key[case["template_key"]]
        assert sorted(case["values"]) == template["required_placeholders"]
        rendered = template["template"].format_map(case["values"])
        assert rendered == case["expected"]
        assert not any(phrase in rendered.casefold() for phrase in forbidden)

    serialized_fixture = json.dumps(fixtures).casefold()
    assert not any(marker in serialized_fixture for marker in FORBIDDEN_PUBLIC_MARKERS)
    for private_field in definitions["privacy_forbidden_fields"]:
        assert f'"{private_field}"' not in serialized_fixture


def test_phase6_contract_rejects_representative_unsafe_variants() -> None:
    root = _project_root()
    definitions_schema = _read_json(
        root / "docs" / "schemas" / "post-draft-report-definitions.schema.json"
    )
    fixtures_schema = _read_json(
        root
        / "docs"
        / "schemas"
        / "post-draft-report-expected-fixtures.schema.json"
    )

    invalid_availability = deepcopy(_definitions())
    invalid_availability["availability_states"][0] = "graded"
    with pytest.raises(ValidationError):
        Draft202012Validator(definitions_schema).validate(invalid_availability)

    duplicate_section = deepcopy(_definitions())
    duplicate_section["section_registry"][1]["section_key"] = "draft_summary"
    with pytest.raises(AssertionError):
        _assert_definition_semantics(duplicate_section)

    private_fixture_field = deepcopy(_fixtures())
    private_fixture_field["private_source_reference"] = "not-public"
    with pytest.raises(ValidationError):
        Draft202012Validator(fixtures_schema).validate(private_fixture_field)

    impossible_coverage = deepcopy(_fixtures())
    impossible_coverage["evidence_coverage_cases"][0]["covered_players"] = 101
    with pytest.raises(AssertionError):
        case = impossible_coverage["evidence_coverage_cases"][0]
        _evidence_result(
            case["covered_players"],
            case["roster_players"],
            case["evidence_state"],
            _definitions(),
        )
