from friendly_hub.domains.mocks.strategy import (
    evaluate_strategy,
    explanation_text,
    pivot_text,
)

LEAGUE_SHAPE = {
    "starter_slots": [
        {"slot": "QB", "eligible_positions": ["QB"]},
        {"slot": "RB", "eligible_positions": ["RB"]},
        {"slot": "WR", "eligible_positions": ["WR"]},
        {"slot": "TE", "eligible_positions": ["TE"]},
        {
            "slot": "SUPER_FLEX",
            "eligible_positions": ["QB", "RB", "WR", "TE"],
        },
    ],
    "superflex": True,
    "qb_eligible_starter_slots": 2,
    "limitations": [],
}


def _evaluate(
    strategy_key: str,
    roster: tuple[tuple[str, bool], ...] = (),
    *,
    pick: int = 1,
    rounds: int = 10,
):
    return evaluate_strategy(
        strategy_key=strategy_key,
        round_count=rounds,
        team_count=10,
        effective_overall_pick=pick,
        roster=roster,
        league_shape=LEAGUE_SHAPE,
    )


def test_balanced_and_timeline_guides_cover_evidence_boundaries() -> None:
    balanced = _evaluate(
        "balanced",
        (("QB", False), ("RB", False), ("WR", True), ("TE", False)),
        pick=71,
    )
    concentrated = _evaluate(
        "balanced",
        (("WR", False), ("WR", False), ("RB", False)),
        pick=21,
    )
    missing_coverage = _evaluate(
        "balanced",
        (("WR", False),),
        pick=71,
    )
    win_now = _evaluate("win_now")
    win_now_late = _evaluate("win_now", (("WR", False),), pick=71)
    productive = _evaluate(
        "productive_struggle",
        (("RB", False), ("RB", True)),
        pick=21,
    )

    assert balanced.state == "on_plan"
    assert concentrated.state == "watch"
    assert missing_coverage.state == "risk_checkpoint"
    assert win_now.state == "insufficient_evidence"
    assert win_now.confidence == "low"
    assert "TIMELINE_EVIDENCE_UNAVAILABLE" in win_now.limitation_codes
    assert win_now_late.state == "risk_checkpoint"
    assert productive.state == "off_plan_viable"
    assert productive.pivot_template_key == "strategy.viable_pivot"


def test_position_strategy_checkpoints_cover_watch_risk_and_viable_pivots() -> None:
    assert _evaluate("hero_rb").state == "watch"
    assert _evaluate("hero_rb", (("RB", False),)).state == "on_plan"
    assert _evaluate("hero_rb", (), pick=41).state == "risk_checkpoint"
    assert _evaluate(
        "hero_rb",
        (("RB", False), ("RB", False), ("RB", True)),
        pick=21,
    ).state == "off_plan_viable"

    assert _evaluate("robust_rb").state == "watch"
    assert _evaluate(
        "robust_rb",
        (("RB", False), ("RB", False)),
    ).state == "on_plan"
    assert _evaluate("robust_rb", (("RB", False),), pick=41).state == (
        "risk_checkpoint"
    )
    assert _evaluate(
        "robust_rb",
        (("RB", False), ("RB", False), ("RB", False)),
        pick=71,
    ).state == "off_plan_viable"

    assert _evaluate("wr_heavy", rounds=5).state == "insufficient_evidence"
    assert _evaluate("wr_heavy").state == "watch"
    assert _evaluate(
        "wr_heavy",
        (("WR", False), ("WR", False), ("WR", True), ("RB", False)),
    ).state == "on_plan"
    assert _evaluate("wr_heavy", (("WR", False),), pick=71).state == (
        "risk_checkpoint"
    )

    assert _evaluate("early_qb_superflex").state == "watch"
    assert _evaluate(
        "early_qb_superflex",
        (("QB", False), ("QB", False)),
    ).state == "on_plan"
    assert _evaluate("early_qb_superflex", (), pick=41).state == (
        "risk_checkpoint"
    )


def test_guidance_templates_are_plain_language_and_player_free() -> None:
    evaluation = _evaluate(
        "productive_struggle",
        (("RB", False), ("RB", True)),
    )
    explanation = explanation_text(evaluation.explanation_template_key)
    viable_pivot = pivot_text(evaluation.pivot_template_key)

    assert "player" not in explanation.lower()
    assert viable_pivot is not None
    assert "earlier selections will not change" in viable_pivot
    assert evaluation.observed_counts["ROOKIE"] == 1
    assert evaluation.target_ranges["affected_positions"] == [
        "QB",
        "RB",
        "WR",
        "TE",
    ]
