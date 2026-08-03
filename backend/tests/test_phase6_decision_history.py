from __future__ import annotations

import json

import pytest

from friendly_hub.domains.reports.history import (
    MomentCandidate,
    MomentPick,
    reconstruct_personal_board_history,
)


def _candidate(
    player_id: str,
    rank: int | None,
    *,
    tier: int | None = None,
    favorite: bool = False,
) -> MomentCandidate:
    return MomentCandidate(
        player_id=player_id,
        display_name=f"Player {player_id}",
        primary_position="WR",
        manual_rank=rank,
        tier_order=tier,
        favorite=favorite,
    )


@pytest.mark.parametrize(
    ("selected_rank", "selected_tier", "passed_favorite", "passed_tier", "expected"),
    [
        (6, None, False, None, 1),
        (5, None, False, None, 0),
        (2, None, True, None, 1),
        (2, 2, False, 1, 1),
        (2, None, False, 1, 0),
    ],
)
def test_personal_board_exact_qualification_boundaries(
    selected_rank: int,
    selected_tier: int | None,
    passed_favorite: bool,
    passed_tier: int | None,
    expected: int,
) -> None:
    history = reconstruct_personal_board_history(
        candidates=(
            _candidate(
                "passed",
                1,
                tier=passed_tier,
                favorite=passed_favorite,
            ),
            _candidate("selected", selected_rank, tier=selected_tier),
        ),
        picks=(
            MomentPick(overall_pick=1, selecting_slot=1, player_id="selected"),
            MomentPick(overall_pick=2, selecting_slot=2, player_id="passed"),
        ),
        user_slot=1,
    )

    assert history.state == "valid"
    assert history.metrics["moment_count"] == expected
    assert len(history.moments) == expected


def test_repeated_pass_collapses_and_tracks_last_availability_without_notes() -> None:
    history = reconstruct_personal_board_history(
        candidates=(
            _candidate("passed", 1, tier=1, favorite=True),
            _candidate("other-1", 2),
            _candidate("other-2", 3),
            _candidate("selected-3", 4, tier=2),
            _candidate("selected-2", 5, tier=2),
            _candidate("selected-1", 6, tier=2),
        ),
        picks=(
            MomentPick(1, 1, "selected-1"),
            MomentPick(2, 2, "other-1"),
            MomentPick(3, 2, "other-2"),
            MomentPick(4, 1, "selected-2"),
            MomentPick(5, 1, "selected-3"),
            MomentPick(6, 2, "passed"),
        ),
        user_slot=1,
    )

    assert history.metrics["qualifying_moment_count"] == 1
    assert len(history.moments) == 1
    moment = history.moments[0]
    assert moment.overall_pick == 1
    assert moment.primary_player_id == "selected-1"
    assert moment.secondary_player_id == "passed"
    assert moment.safe_summary["first_user_pick"] == 1
    assert moment.safe_summary["last_available_user_pick"] == 5
    assert moment.safe_summary["rank_delta"] == 5
    assert moment.safe_summary["passed_player_draft_outcome"] == {
        "state": "drafted_by_other_slot",
        "overall_pick": 6,
    }
    serialized = json.dumps(moment.safe_summary).casefold()
    assert "note" not in serialized
    assert "mistake" not in serialized


def test_personal_board_priority_retains_only_first_ten_tied_observations() -> None:
    candidates: list[MomentCandidate] = []
    picks: list[MomentPick] = []
    for number in range(1, 12):
        passed_id = f"passed-{number}"
        selected_id = f"selected-{number}"
        candidates.extend(
            (
                _candidate(passed_id, number, tier=1),
                _candidate(selected_id, 100 + number, tier=2),
            )
        )
        picks.extend(
            (
                MomentPick((number * 2) - 1, 1, selected_id),
                MomentPick(number * 2, 2, passed_id),
            )
        )

    history = reconstruct_personal_board_history(
        candidates=tuple(candidates),
        picks=tuple(picks),
        user_slot=1,
    )

    assert history.metrics["qualifying_moment_count"] == 11
    assert history.metrics["moment_count"] == 10
    assert history.metrics["truncated"] is True
    assert [moment.overall_pick for moment in history.moments] == list(range(1, 20, 2))


def test_duplicate_or_nonpositive_frozen_ranks_fail_closed() -> None:
    for candidates in (
        (_candidate("one", 1), _candidate("two", 1)),
        (_candidate("one", 0), _candidate("two", 2)),
    ):
        history = reconstruct_personal_board_history(
            candidates=candidates,
            picks=(
                MomentPick(1, 1, "one"),
                MomentPick(2, 2, "two"),
            ),
            user_slot=1,
        )
        assert history.state == "corrupt"
        assert history.moments == ()
        assert "PERSONAL_BOARD_RANKS_CORRUPT" in history.limitation_codes
