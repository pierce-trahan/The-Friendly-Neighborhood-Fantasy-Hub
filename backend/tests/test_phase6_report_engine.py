from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from friendly_hub.domains.reports.definitions import (
    EXPLANATION_TEMPLATE_VERSION,
    EXPLANATION_TEMPLATES,
    REPORT_ENGINE_VERSION,
    REPORT_RULES_VERSION,
)
from friendly_hub.domains.reports.engine import (
    RosterPlayer,
    StarterAssignment,
    StarterSlot,
    canonical_json,
    content_fingerprint,
    evaluate_concentration,
    evaluate_evidence_coverage,
    evaluate_starter_coverage,
    render_explanation,
    strategy_section_state,
    unsupported_section_state,
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


def _fixture() -> dict[str, Any]:
    return _read_json(
        _project_root()
        / "tests"
        / "fixtures"
        / "post_draft_reports"
        / "phase-6-report-v1.expected.json"
    )


def _starter_inputs() -> tuple[tuple[StarterSlot, ...], tuple[RosterPlayer, ...]]:
    case = _fixture()["starter_assignment_case"]
    slots = tuple(
        StarterSlot(
            slot_order=slot["slot_order"],
            slot_key=slot["slot_key"],
            slot_type=slot["slot_type"],
            eligible_positions=tuple(slot["eligible_positions"]),
        )
        for slot in case["league_shape"]["starter_slots"]
    )
    roster = tuple(
        RosterPlayer(
            canonical_player_id=player["canonical_player_id"],
            overall_pick=player["overall_pick"],
            primary_position=player["primary_position"],
            fantasy_positions=tuple(player["fantasy_positions"]),
        )
        for player in case["roster"]
    )
    return slots, roster


def test_runtime_versions_and_templates_match_the_approved_contract() -> None:
    definitions = _definitions()
    assert REPORT_ENGINE_VERSION == "post-draft-report-engine-v1"
    assert REPORT_RULES_VERSION == definitions["rules_version"]
    assert EXPLANATION_TEMPLATE_VERSION == definitions["explanation_template_version"]
    assert dict(EXPLANATION_TEMPLATES) == {
        template["template_key"]: template["template"]
        for template in definitions["explanation_templates"]
    }


def test_starter_assignment_reproduces_the_expected_fixture() -> None:
    slots, roster = _starter_inputs()
    expected = _fixture()["starter_assignment_case"]["expected"]

    result = evaluate_starter_coverage(
        starter_slots=tuple(reversed(slots)),
        roster=tuple(reversed(roster)),
    )

    assert result.availability == expected["availability"]
    assert result.confidence == expected["confidence"]
    assert result.starter_slots_total == expected["starter_slots_total"]
    assert result.starter_slots_filled == expected["starter_slots_filled"]
    assert (
        result.starter_coverage_basis_points
        == expected["starter_coverage_basis_points"]
    )
    assert result.assignments == tuple(
        StarterAssignment(
            slot_order=assignment["slot_order"],
            slot_key=assignment["slot_key"],
            canonical_player_id=assignment["canonical_player_id"],
        )
        for assignment in expected["assignments"]
    )
    assert result.unfilled_slot_keys == tuple(expected["unfilled_slot_keys"])
    assert result.ambiguous_flex_slot_keys == tuple(
        expected["ambiguous_flex_slot_keys"]
    )
    assert dict(result.depth_counts) == expected["depth_counts"]
    assert result.limitation_codes == tuple(expected["limitation_codes"])

    repeated = evaluate_starter_coverage(
        starter_slots=slots,
        roster=roster,
    )
    assert repeated == result


def test_starter_assignment_maximizes_coverage_before_tie_breaking() -> None:
    slots = (
        StarterSlot(0, "FLEX1", "FLEX", ("RB", "WR", "TE")),
        StarterSlot(1, "RB1", "RB", ("RB",)),
    )
    roster = (
        RosterPlayer("fictional-rb", 1, "RB", ("RB",)),
        RosterPlayer("fictional-wr", 2, "WR", ("WR",)),
    )

    result = evaluate_starter_coverage(starter_slots=slots, roster=roster)

    assert result.starter_slots_filled == 2
    assert result.assignments == (
        StarterAssignment(0, "FLEX1", "fictional-wr"),
        StarterAssignment(1, "RB1", "fictional-rb"),
    )


def test_missing_shape_and_incomplete_eligibility_fail_visibly() -> None:
    player = RosterPlayer("fictional-qb", 1, "QB", ("QB",))
    unavailable = evaluate_starter_coverage(
        starter_slots=None,
        roster=(player,),
    )
    assert unavailable.availability == "unavailable"
    assert unavailable.confidence == "unavailable"
    assert unavailable.reason_codes == ("STARTER_SHAPE_UNAVAILABLE",)
    assert dict(unavailable.depth_counts) == {"QB": 1}

    limited = evaluate_starter_coverage(
        starter_slots=(StarterSlot(0, "QB1", "QB", ("QB",)),),
        roster=(
            player,
            RosterPlayer("fictional-unknown", 2, "UNKNOWN", ()),
        ),
    )
    assert limited.availability == "limited"
    assert limited.confidence == "low"
    assert limited.limitation_codes == ("PLAYER_ELIGIBILITY_INCOMPLETE",)
    assert dict(limited.depth_counts) == {"QB": 0, "UNKNOWN": 1}


def test_evidence_coverage_reproduces_every_expected_boundary() -> None:
    for case in _fixture()["evidence_coverage_cases"]:
        result = evaluate_evidence_coverage(
            covered_players=case["covered_players"],
            roster_players=case["roster_players"],
            evidence_state=case["evidence_state"],
        )
        assert result.coverage_basis_points == case["expected_basis_points"]
        assert result.availability == case["expected_availability"]
        assert result.confidence == case["expected_confidence"]


def test_concentration_reproduces_every_expected_boundary() -> None:
    for case in _fixture()["concentration_cases"]:
        result = evaluate_concentration(
            total_user_picks=case["total_user_picks"],
            position_pick_counts=case["position_pick_counts"],
            unfilled_distinct_starter_positions=case[
                "unfilled_distinct_starter_positions"
            ],
        )
        assert (
            result.maximum_share_basis_points
            == case["expected_maximum_share_basis_points"]
        )
        assert result.bands == tuple(case["expected_bands"])


def test_mode_and_unsupported_section_states_reproduce_expected_fixtures() -> None:
    for case in _fixture()["mode_cases"]:
        result = strategy_section_state(draft_mode=case["mode"])
        assert result.availability == case["expected_availability"]
        assert result.confidence == case["expected_confidence"]
        assert result.reason_codes == tuple(case["reason_codes"])

    for case in _fixture()["unsupported_section_cases"]:
        result = unsupported_section_state(case["section_key"])
        assert result.availability == case["expected_availability"]
        assert result.confidence == case["expected_confidence"]
        assert result.reason_codes == tuple(case["reason_codes"])

    assert strategy_section_state(
        draft_mode="mock",
        history_state="incomplete",
    ).availability == "limited"
    assert strategy_section_state(
        draft_mode="mock",
        history_state="corrupt",
    ).availability == "unavailable"


def test_explanation_renderer_reproduces_expected_fixture_text() -> None:
    for case in _fixture()["explanation_cases"]:
        assert render_explanation(
            template_key=case["template_key"],
            values=case["values"],
        ) == case["expected"]

    with pytest.raises(ValueError, match="exactly"):
        render_explanation(
            template_key="starter.coverage_complete",
            values={},
        )
    with pytest.raises(ValueError, match="exactly"):
        render_explanation(
            template_key="starter.coverage_complete",
            values={"starter_slots_total": 8, "extra": 1},
        )
    with pytest.raises(ValueError, match="strings or integers"):
        render_explanation(
            template_key="starter.coverage_complete",
            values={"starter_slots_total": True},
        )


def test_canonical_json_and_fingerprint_are_stable_and_strict() -> None:
    left = {"b": [2, None], "a": {"z": "Café", "y": 1}}
    right = {"a": {"y": 1, "z": "Café"}, "b": [2, None]}
    assert canonical_json(left) == '{"a":{"y":1,"z":"Café"},"b":[2,null]}'
    assert canonical_json(left) == canonical_json(right)
    assert content_fingerprint(left) == content_fingerprint(right)
    assert content_fingerprint({"values": [1, 2]}) != content_fingerprint(
        {"values": [2, 1]}
    )
    with pytest.raises(ValueError, match="finite JSON"):
        canonical_json({"invalid": float("nan")})
    with pytest.raises(ValueError, match="finite JSON"):
        canonical_json({"invalid": object()})


def test_invalid_engine_inputs_fail_closed() -> None:
    with pytest.raises(ValueError, match="slot type"):
        StarterSlot(0, "FLEX1", "FLEX", ("RB",))
    with pytest.raises(ValueError, match="unique"):
        RosterPlayer("fictional-player", 1, "RB", ("RB", "RB"))
    with pytest.raises(ValueError, match="overall_pick values"):
        evaluate_starter_coverage(
            starter_slots=(StarterSlot(0, "RB1", "RB", ("RB",)),),
            roster=(
                RosterPlayer("fictional-a", 1, "RB", ("RB",)),
                RosterPlayer("fictional-b", 1, "RB", ("RB",)),
            ),
        )
    with pytest.raises(ValueError, match="between zero"):
        evaluate_evidence_coverage(
            covered_players=11,
            roster_players=10,
            evidence_state="usable",
        )
    with pytest.raises(ValueError, match="sum"):
        evaluate_concentration(
            total_user_picks=10,
            position_pick_counts={"RB": 9},
            unfilled_distinct_starter_positions=0,
        )
    with pytest.raises(ValueError, match="draft_mode"):
        strategy_section_state(draft_mode="practice")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="always-unavailable"):
        unsupported_section_state("starter_coverage")
