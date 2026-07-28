from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DraftFormat = Literal["linear", "snake"]


@dataclass(frozen=True)
class DraftPickSlot:
    overall_pick: int
    round_number: int
    pick_in_round: int
    selecting_slot: int


def slots_for_round(
    draft_format: DraftFormat,
    third_round_reversal: bool,
    team_count: int,
    round_number: int,
) -> tuple[int, ...]:
    forward = tuple(range(1, team_count + 1))
    if draft_format == "linear":
        return forward
    reverse = tuple(reversed(forward))
    if third_round_reversal:
        if round_number == 1:
            return forward
        if round_number in {2, 3}:
            return reverse
        return forward if round_number % 2 == 0 else reverse
    return forward if round_number % 2 == 1 else reverse


def build_draft_order(
    draft_format: DraftFormat,
    third_round_reversal: bool,
    team_count: int,
    round_count: int,
) -> tuple[DraftPickSlot, ...]:
    order: list[DraftPickSlot] = []
    overall_pick = 1
    for round_number in range(1, round_count + 1):
        for pick_in_round, selecting_slot in enumerate(
            slots_for_round(
                draft_format,
                third_round_reversal,
                team_count,
                round_number,
            ),
            start=1,
        ):
            order.append(
                DraftPickSlot(
                    overall_pick=overall_pick,
                    round_number=round_number,
                    pick_in_round=pick_in_round,
                    selecting_slot=selecting_slot,
                )
            )
            overall_pick += 1
    return tuple(order)


def picks_until_slot(
    order: tuple[DraftPickSlot, ...],
    current_overall_pick: int | None,
    target_slot: int,
) -> int | None:
    if current_overall_pick is None:
        return None
    for pick in order[current_overall_pick - 1 :]:
        if pick.selecting_slot == target_slot:
            return pick.overall_pick - current_overall_pick
    return None
