from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from math import ceil


@dataclass(frozen=True)
class ParticipantInput:
    player_id: str
    starting_manual_rank: int


@dataclass(frozen=True)
class ActionInput:
    player_a_id: str
    player_b_id: str
    outcome: str


@dataclass(frozen=True)
class ReplayResult:
    ratings: dict[str, float]
    decisive_counts: dict[str, int]
    order: list[str]
    top_order_change_count: int


def default_target(participant_count: int) -> int:
    total_pairs = participant_count * (participant_count - 1) // 2
    return min(total_pairs, ceil(participant_count * 4 / 2), 40)


def _ordered_ids(
    participants: list[ParticipantInput],
    ratings: dict[str, float],
    decisive_counts: dict[str, int],
) -> list[str]:
    by_id = {participant.player_id: participant for participant in participants}
    return sorted(
        by_id,
        key=lambda player_id: (
            -ratings[player_id],
            -decisive_counts[player_id],
            by_id[player_id].starting_manual_rank,
            player_id,
        ),
    )


def replay(
    participants: list[ParticipantInput],
    actions: list[ActionInput],
) -> ReplayResult:
    ratings = {participant.player_id: 1000.0 for participant in participants}
    decisive_counts = {participant.player_id: 0 for participant in participants}
    recent_top_changes: list[bool] = []
    top_size = min(3, len(participants))

    for action in actions:
        if action.outcome not in {"a_win", "b_win"}:
            continue
        before = _ordered_ids(participants, ratings, decisive_counts)[:top_size]
        rating_a = ratings[action.player_a_id]
        rating_b = ratings[action.player_b_id]
        expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
        expected_b = 1 - expected_a
        score_a = 1.0 if action.outcome == "a_win" else 0.0
        score_b = 1.0 - score_a
        ratings[action.player_a_id] = round(
            rating_a + 32 * (score_a - expected_a),
            6,
        )
        ratings[action.player_b_id] = round(
            rating_b + 32 * (score_b - expected_b),
            6,
        )
        decisive_counts[action.player_a_id] += 1
        decisive_counts[action.player_b_id] += 1
        after = _ordered_ids(participants, ratings, decisive_counts)[:top_size]
        recent_top_changes.append(before != after)

    return ReplayResult(
        ratings=ratings,
        decisive_counts=decisive_counts,
        order=_ordered_ids(participants, ratings, decisive_counts),
        top_order_change_count=sum(recent_top_changes[-5:]),
    )


def pair_key(player_a_id: str, player_b_id: str) -> tuple[str, str]:
    if player_a_id <= player_b_id:
        return player_a_id, player_b_id
    return player_b_id, player_a_id


def select_next_pair(
    participants: list[ParticipantInput],
    actions: list[ActionInput],
    *,
    queue_mode: str,
    replay_result: ReplayResult,
) -> tuple[str, str] | None:
    participant_by_id = {
        participant.player_id: participant for participant in participants
    }
    resolved: set[tuple[str, str]] = set()
    skip_counts: Counter[tuple[str, str]] = Counter()
    for action in actions:
        key = pair_key(action.player_a_id, action.player_b_id)
        if action.outcome == "skip":
            skip_counts[key] += 1
        else:
            resolved.add(key)

    candidates = [
        pair_key(left.player_id, right.player_id)
        for left, right in combinations(participants, 2)
        if pair_key(left.player_id, right.player_id) not in resolved
    ]
    if not candidates:
        return None
    untried = [pair for pair in candidates if skip_counts[pair] == 0]
    pool = untried or candidates

    def manual_distance(pair: tuple[str, str]) -> int:
        return abs(
            participant_by_id[pair[0]].starting_manual_rank
            - participant_by_id[pair[1]].starting_manual_rank
        )

    def manual_pair_order(pair: tuple[str, str]) -> tuple[int, int, str, str]:
        ranks = sorted(
            (
                participant_by_id[pair[0]].starting_manual_rank,
                participant_by_id[pair[1]].starting_manual_rank,
            )
        )
        return ranks[0], ranks[1], pair[0], pair[1]

    counts = replay_result.decisive_counts
    if queue_mode == "uncertainty":
        pool.sort(
            key=lambda pair: (
                max(counts[pair[0]], counts[pair[1]]),
                abs(
                    replay_result.ratings[pair[0]]
                    - replay_result.ratings[pair[1]]
                ),
                counts[pair[0]] + counts[pair[1]],
                skip_counts[pair],
                manual_distance(pair),
                manual_pair_order(pair),
            )
        )
    else:
        pool.sort(
            key=lambda pair: (
                counts[pair[0]] + counts[pair[1]],
                max(counts[pair[0]], counts[pair[1]]),
                manual_distance(pair),
                skip_counts[pair],
                manual_pair_order(pair),
            )
        )
    chosen = pool[0]
    if (
        participant_by_id[chosen[0]].starting_manual_rank,
        chosen[0],
    ) <= (
        participant_by_id[chosen[1]].starting_manual_rank,
        chosen[1],
    ):
        return chosen
    return chosen[1], chosen[0]
