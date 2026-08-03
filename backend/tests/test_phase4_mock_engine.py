import pytest

from friendly_hub.domains.mocks.definitions import (
    MAX_SEED,
    PRACTICE_BOARD_ENGINE_VERSION,
)
from friendly_hub.domains.mocks.engine import (
    CandidateInput,
    CandidateScoreInput,
    build_consideration_set,
    content_fingerprint,
    deterministic_draw,
    effective_randomness,
    emphasized_position,
    normalize_seed,
    practice_board_score,
    random_variation,
    roster_score_components,
    score_candidates,
    select_candidate,
)


def test_seed_normalization_and_unsigned_64_bit_boundary() -> None:
    assert normalize_seed("00042") == "42"
    assert normalize_seed(str(MAX_SEED)) == str(MAX_SEED)

    for invalid in ("", "-1", "+1", " 1", "1.0", str(MAX_SEED + 1)):
        with pytest.raises(ValueError):
            normalize_seed(invalid)


def test_content_fingerprint_is_canonical_and_order_sensitive() -> None:
    left = {
        "profiles": [{"slot": 2, "archetype": "balanced"}],
        "candidates": ["player-a", "player-b"],
    }
    reordered_keys = {
        "candidates": ["player-a", "player-b"],
        "profiles": [{"archetype": "balanced", "slot": 2}],
    }
    reordered_candidates = {
        "candidates": ["player-b", "player-a"],
        "profiles": [{"archetype": "balanced", "slot": 2}],
    }

    assert content_fingerprint(left) == content_fingerprint(reordered_keys)
    assert content_fingerprint(left) != content_fingerprint(reordered_candidates)
    with pytest.raises(ValueError):
        content_fingerprint({"invalid": float("nan")})


def test_sha256_counter_draw_matches_cross_language_fixture() -> None:
    fingerprint = content_fingerprint(
        {
            "candidates": ["player-a", "player-b"],
            "draft_order": [1, 2],
            "league_shape": {"superflex": True},
            "profiles": [{"slot": 2, "archetype": "balanced"}],
        }
    )
    draw = deterministic_draw(
        seed="2026072801",
        fingerprint=fingerprint,
        overall_pick=7,
        selecting_slot=2,
        purpose="candidate-random-variation",
        draw_index=0,
        stable_key="player-a",
        engine_version=PRACTICE_BOARD_ENGINE_VERSION,
    )

    assert fingerprint == "634ac8517d1e6ac51fa266f544835766ff78aa1b49b6029ad95814964617b7d9"
    assert draw.canonical_input == (
        '["practice-board-v1","sha256-counter-v1","2026072801",'
        '"634ac8517d1e6ac51fa266f544835766ff78aa1b49b6029ad95814964617b7d9",'
        '7,2,"candidate-random-variation",0,"player-a"]'
    )
    assert draw.digest_hex == (
        "43d8743f55f676aa4ad53cff6ec142569fd3add7cbcffd53fa9defe0f9976317"
    )
    assert draw.numerator == 4_888_785_210_884_650_666
    assert draw.value == pytest.approx(0.2650215773228072)


def test_draw_dimensions_change_the_result_and_randomness_is_bounded() -> None:
    fingerprint = content_fingerprint({"candidates": ["player-a"]})
    base = deterministic_draw(
        seed="7",
        fingerprint=fingerprint,
        overall_pick=1,
        selecting_slot=2,
        purpose="candidate-random-variation",
        draw_index=0,
        stable_key="player-a",
    )
    changed = deterministic_draw(
        seed="7",
        fingerprint=fingerprint,
        overall_pick=2,
        selecting_slot=2,
        purpose="candidate-random-variation",
        draw_index=0,
        stable_key="player-a",
    )

    assert base.digest_hex != changed.digest_hex
    assert random_variation(base, 0) == 0
    assert -200 <= random_variation(base, 100) <= 200
    with pytest.raises(ValueError):
        random_variation(base, 101)


def test_draw_rejects_malformed_coordinates_and_versions() -> None:
    fingerprint = content_fingerprint({"candidates": ["player-a"]})
    valid = {
        "seed": "7",
        "fingerprint": fingerprint,
        "overall_pick": 1,
        "selecting_slot": 2,
        "purpose": "candidate-random-variation",
        "draw_index": 0,
        "stable_key": "player-a",
    }
    invalid_overrides = (
        {"fingerprint": "short"},
        {"fingerprint": "G" * 64},
        {"overall_pick": 0},
        {"overall_pick": True},
        {"selecting_slot": 0},
        {"selecting_slot": 1.5},
        {"purpose": ""},
        {"draw_index": -1},
        {"draw_index": False},
        {"rng_version": ""},
        {"engine_version": ""},
        {"stable_key": 7},
    )

    for override in invalid_overrides:
        with pytest.raises(ValueError):
            deterministic_draw(**(valid | override))


def test_practice_board_and_randomness_validation() -> None:
    assert practice_board_score(3, 0) == 300
    assert practice_board_score(3, 2) == 100

    for candidate_count, practice_index in (
        (0, 0),
        (True, 0),
        (3, -1),
        (3, 3),
        (3, False),
    ):
        with pytest.raises(ValueError):
            practice_board_score(candidate_count, practice_index)
    with pytest.raises(ValueError, match="integer"):
        build_consideration_set((), randomness=True)


def test_consideration_set_unions_random_need_and_archetype_candidates() -> None:
    candidates = (
        CandidateInput("wr-1", "WR", 0),
        CandidateInput("rb-1", "RB", 1),
        CandidateInput("qb-1", "QB", 2),
        CandidateInput("te-1", "TE", 3),
        CandidateInput("qb-2", "QB", 4),
        CandidateInput("te-2", "TE", 5),
        CandidateInput("qb-3", "QB", 6),
        CandidateInput("te-3", "TE", 7),
        CandidateInput("qb-4", "QB", 8),
        CandidateInput("te-4", "TE", 9),
    )

    considered = build_consideration_set(
        tuple(reversed(candidates)),
        randomness=0,
        unfilled_starter_positions=("QB",),
        emphasized_position="TE",
    )

    assert [candidate.player_id for candidate in considered] == [
        "wr-1",
        "qb-1",
        "te-1",
        "qb-2",
        "te-2",
        "qb-3",
        "te-3",
    ]
    with pytest.raises(ValueError, match="practice indices"):
        build_consideration_set(
            (
                CandidateInput("player-a", "WR", 0),
                CandidateInput("player-b", "RB", 0),
            ),
            randomness=0,
        )
    assert build_consideration_set(
        (CandidateInput("player-a", "WR", 0),),
        randomness=0,
        unfilled_starter_positions=("",),
    ) == (CandidateInput("player-a", "WR", 0),)
    invalid_candidate_sets = (
        (CandidateInput("", "WR", 0),),
        (
            CandidateInput("player-a", "WR", 0),
            CandidateInput("player-a", "RB", 1),
        ),
        (CandidateInput("player-a", "WR", -1),),
        (CandidateInput("player-a", "", 0),),
    )
    for invalid_candidates in invalid_candidate_sets:
        with pytest.raises(ValueError):
            build_consideration_set(invalid_candidates, randomness=0)


def test_scoring_is_explainable_bounded_and_ties_use_canonical_id() -> None:
    fingerprint = content_fingerprint({"candidates": ["alpha", "beta", "gamma"]})
    tied = score_candidates(
        (
            CandidateScoreInput("beta", practice_index=1, starter_need=100),
            CandidateScoreInput("alpha", practice_index=0),
        ),
        candidate_count=3,
        seed="9",
        fingerprint=fingerprint,
        overall_pick=1,
        selecting_slot=2,
        randomness=0,
    )

    assert [candidate.player_id for candidate in tied] == ["alpha", "beta"]
    assert tied[0].components.board_order == 300
    assert tied[0].components.random_variation == 0
    assert tied[0].total_score == 300
    assert select_candidate(tuple(reversed(tied))).player_id == "alpha"

    with pytest.raises(ValueError, match="starter_need"):
        score_candidates(
            (CandidateScoreInput("gamma", practice_index=2, starter_need=301),),
            candidate_count=3,
            seed="9",
            fingerprint=fingerprint,
            overall_pick=1,
            selecting_slot=2,
            randomness=0,
        )
    with pytest.raises(ValueError, match="practice indices"):
        score_candidates(
            (
                CandidateScoreInput("alpha", practice_index=0),
                CandidateScoreInput("beta", practice_index=0),
            ),
            candidate_count=3,
            seed="9",
            fingerprint=fingerprint,
            overall_pick=1,
            selecting_slot=2,
            randomness=0,
        )
    with pytest.raises(ValueError, match="at least one candidate"):
        score_candidates(
            (),
            candidate_count=3,
            seed="9",
            fingerprint=fingerprint,
            overall_pick=1,
            selecting_slot=2,
            randomness=0,
        )
    with pytest.raises(ValueError, match="player_id"):
        score_candidates(
            (CandidateScoreInput("", practice_index=0),),
            candidate_count=3,
            seed="9",
            fingerprint=fingerprint,
            overall_pick=1,
            selecting_slot=2,
            randomness=0,
        )
    with pytest.raises(ValueError, match="player IDs"):
        score_candidates(
            (
                CandidateScoreInput("alpha", practice_index=0),
                CandidateScoreInput("alpha", practice_index=1),
            ),
            candidate_count=3,
            seed="9",
            fingerprint=fingerprint,
            overall_pick=1,
            selecting_slot=2,
            randomness=0,
        )
    with pytest.raises(ValueError, match="integer"):
        score_candidates(
            (CandidateScoreInput("alpha", practice_index=0, depth_need=1.5),),
            candidate_count=3,
            seed="9",
            fingerprint=fingerprint,
            overall_pick=1,
            selecting_slot=2,
            randomness=0,
        )
    with pytest.raises(ValueError, match="at least one scored"):
        select_candidate(())


def test_fallback_archetypes_change_only_bounded_documented_components() -> None:
    shared = {
        "position": "QB",
        "is_rookie": False,
        "roster_counts": {},
        "unfilled_starter_positions": ("QB",),
        "tight_end_premium": False,
    }
    balanced = roster_score_components(archetype_key="balanced", **shared)
    qb_priority = roster_score_components(archetype_key="qb_priority", **shared)
    rb_heavy = roster_score_components(
        archetype_key="rb_heavy",
        **(shared | {"position": "RB"}),
    )
    wr_heavy = roster_score_components(
        archetype_key="wr_heavy",
        **(shared | {"position": "WR"}),
    )
    te_aware = roster_score_components(
        archetype_key="te_aware",
        **(shared | {"position": "TE", "tight_end_premium": True}),
    )
    rookie_lean = roster_score_components(
        archetype_key="rookie_lean",
        **(shared | {"position": "WR", "is_rookie": True}),
    )
    chaotic = roster_score_components(archetype_key="chaotic", **shared)

    assert balanced.starter_need == 200
    assert balanced.depth_need == 100
    assert balanced.archetype_fit == 0
    assert qb_priority.archetype_fit == 200
    assert rb_heavy.archetype_fit == 175
    assert wr_heavy.archetype_fit == 175
    assert te_aware.archetype_fit == 200
    assert rookie_lean.archetype_fit == 100
    assert chaotic.archetype_fit == 0
    assert emphasized_position("qb_priority") == "QB"
    assert emphasized_position("rookie_lean") is None
    assert effective_randomness(35, "balanced") == 35
    assert effective_randomness(35, "chaotic") == 70
    assert effective_randomness(75, "chaotic") == 100
    assert effective_randomness(0, "chaotic") == 0

    concentrated = roster_score_components(
        position="WR",
        is_rookie=False,
        roster_counts={"WR": 5},
        unfilled_starter_positions=(),
        archetype_key="balanced",
        tight_end_premium=False,
    )
    assert concentrated.depth_need == 0
    assert concentrated.duplication_penalty == -300

    with pytest.raises(ValueError, match="archetype"):
        roster_score_components(archetype_key="unknown", **shared)
    with pytest.raises(ValueError, match="roster counts"):
        roster_score_components(
            archetype_key="balanced",
            **(shared | {"roster_counts": {"QB": -1}}),
        )
