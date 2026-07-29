from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from string import Formatter

from friendly_hub.domains.reports.definitions import (
    BALANCED_MAXIMUM_BASIS_POINTS,
    BLOCKING_EVIDENCE_STATES,
    EXPLANATION_TEMPLATES,
    FLEX_SLOT_TYPES,
    HIGHLY_CONCENTRATED_ABOVE_BASIS_POINTS,
    LIMITED_COVERAGE_MINIMUM_BASIS_POINTS,
    MAXIMUM_STARTER_SLOTS,
    MAXIMUM_USER_ROSTER_PICKS,
    SUPPORTED_COVERAGE_MINIMUM_BASIS_POINTS,
    SUPPORTED_SLOT_ELIGIBILITY,
    UNSUPPORTED_SECTION_REASONS,
    Availability,
    ConcentrationBand,
    Confidence,
    DraftMode,
    EvidenceState,
    SlotType,
    StrategyHistoryState,
)


@dataclass(frozen=True)
class StarterSlot:
    slot_order: int
    slot_key: str
    slot_type: SlotType
    eligible_positions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _is_integer(self.slot_order) or self.slot_order < 0:
            raise ValueError("slot_order must be a non-negative integer")
        if not isinstance(self.slot_key, str) or not self.slot_key:
            raise ValueError("slot_key must not be empty")
        if self.slot_type not in SUPPORTED_SLOT_ELIGIBILITY:
            raise ValueError("slot_type is not supported")
        if not isinstance(self.eligible_positions, tuple):
            raise ValueError("eligible_positions must be a tuple")
        if (
            not self.eligible_positions
            or len(self.eligible_positions) != len(set(self.eligible_positions))
            or any(
                not isinstance(position, str) or not position
                for position in self.eligible_positions
            )
        ):
            raise ValueError("eligible_positions must contain unique positions")
        if set(self.eligible_positions) != SUPPORTED_SLOT_ELIGIBILITY[self.slot_type]:
            raise ValueError("eligible_positions do not match the supported slot type")


@dataclass(frozen=True)
class RosterPlayer:
    canonical_player_id: str
    overall_pick: int
    primary_position: str
    fantasy_positions: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.canonical_player_id, str)
            or not self.canonical_player_id
        ):
            raise ValueError("canonical_player_id must not be empty")
        if not _is_integer(self.overall_pick) or self.overall_pick < 1:
            raise ValueError("overall_pick must be a positive integer")
        if not isinstance(self.primary_position, str) or not self.primary_position:
            raise ValueError("primary_position must not be empty")
        if not isinstance(self.fantasy_positions, tuple):
            raise ValueError("fantasy_positions must be a tuple")
        if (
            len(self.fantasy_positions) != len(set(self.fantasy_positions))
            or any(
                not isinstance(position, str) or not position
                for position in self.fantasy_positions
            )
        ):
            raise ValueError("fantasy_positions must contain unique positions")


@dataclass(frozen=True)
class StarterAssignment:
    slot_order: int
    slot_key: str
    canonical_player_id: str


@dataclass(frozen=True)
class StarterCoverageResult:
    availability: Availability
    confidence: Confidence
    starter_slots_total: int
    starter_slots_filled: int
    starter_coverage_basis_points: int
    assignments: tuple[StarterAssignment, ...]
    unfilled_slot_keys: tuple[str, ...]
    ambiguous_flex_slot_keys: tuple[str, ...]
    depth_counts: tuple[tuple[str, int], ...]
    reason_codes: tuple[str, ...]
    limitation_codes: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceCoverageResult:
    coverage_basis_points: int
    availability: Availability
    confidence: Confidence
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class ConcentrationResult:
    maximum_share_basis_points: int
    bands: tuple[ConcentrationBand, ...]


@dataclass(frozen=True)
class SectionState:
    availability: Availability
    confidence: Confidence
    reason_codes: tuple[str, ...]


def canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("value must contain only finite JSON values") from exc


def content_fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def evaluate_starter_coverage(
    *,
    starter_slots: Sequence[StarterSlot] | None,
    roster: Sequence[RosterPlayer],
) -> StarterCoverageResult:
    ordered_roster = _validated_roster(roster)
    if starter_slots is None:
        return StarterCoverageResult(
            availability="unavailable",
            confidence="unavailable",
            starter_slots_total=0,
            starter_slots_filled=0,
            starter_coverage_basis_points=0,
            assignments=(),
            unfilled_slot_keys=(),
            ambiguous_flex_slot_keys=(),
            depth_counts=_depth_counts(ordered_roster, assigned_player_ids=set()),
            reason_codes=("STARTER_SHAPE_UNAVAILABLE",),
            limitation_codes=(),
        )

    ordered_slots = _validated_slots(starter_slots)
    maximum_count = _maximum_matching_size(ordered_slots, ordered_roster)
    chosen_edges = _lexicographically_smallest_maximum_assignment(
        ordered_slots,
        ordered_roster,
        maximum_count,
    )
    assigned_by_slot = {
        slot_order: player_id for slot_order, _, player_id in chosen_edges
    }
    slot_by_order = {slot.slot_order: slot for slot in ordered_slots}
    assignments = tuple(
        StarterAssignment(
            slot_order=slot_order,
            slot_key=slot_by_order[slot_order].slot_key,
            canonical_player_id=player_id,
        )
        for slot_order, _, player_id in chosen_edges
    )
    assigned_player_ids = {assignment.canonical_player_id for assignment in assignments}
    incomplete_eligibility = _has_incomplete_eligibility(ordered_roster)
    ambiguous_flex_slot_keys = _ambiguous_flex_slot_keys(
        ordered_slots,
        ordered_roster,
        assigned_by_slot,
        maximum_count,
    )
    if incomplete_eligibility:
        availability: Availability = "limited"
        confidence: Confidence = "low"
        limitation_codes = ("PLAYER_ELIGIBILITY_INCOMPLETE",)
    else:
        availability = "supported"
        confidence = "high"
        limitation_codes = ()
    reason_code = (
        "STARTER_ASSIGNMENT_COMPLETE"
        if maximum_count == len(ordered_slots)
        else "STARTER_ASSIGNMENT_PARTIAL"
    )
    return StarterCoverageResult(
        availability=availability,
        confidence=confidence,
        starter_slots_total=len(ordered_slots),
        starter_slots_filled=maximum_count,
        starter_coverage_basis_points=maximum_count * 10_000 // len(ordered_slots),
        assignments=assignments,
        unfilled_slot_keys=tuple(
            slot.slot_key
            for slot in ordered_slots
            if slot.slot_order not in assigned_by_slot
        ),
        ambiguous_flex_slot_keys=ambiguous_flex_slot_keys,
        depth_counts=_depth_counts(ordered_roster, assigned_player_ids),
        reason_codes=(reason_code,),
        limitation_codes=limitation_codes,
    )


def evaluate_evidence_coverage(
    *,
    covered_players: int,
    roster_players: int,
    evidence_state: EvidenceState,
) -> EvidenceCoverageResult:
    if not _is_integer(roster_players) or roster_players < 1:
        raise ValueError("roster_players must be a positive integer")
    if (
        not _is_integer(covered_players)
        or covered_players < 0
        or covered_players > roster_players
    ):
        raise ValueError("covered_players must be between zero and roster_players")
    if evidence_state not in ("usable", "expired", "incompatible", "invalid"):
        raise ValueError("evidence_state is not supported")

    basis_points = covered_players * 10_000 // roster_players
    if evidence_state in BLOCKING_EVIDENCE_STATES:
        return EvidenceCoverageResult(
            coverage_basis_points=basis_points,
            availability="unavailable",
            confidence="unavailable",
            reason_codes=(f"EVIDENCE_STATE_{evidence_state.upper()}",),
        )
    if basis_points >= SUPPORTED_COVERAGE_MINIMUM_BASIS_POINTS:
        return EvidenceCoverageResult(
            coverage_basis_points=basis_points,
            availability="supported",
            confidence="medium",
            reason_codes=("EVIDENCE_COVERAGE_SUPPORTED",),
        )
    if basis_points >= LIMITED_COVERAGE_MINIMUM_BASIS_POINTS:
        return EvidenceCoverageResult(
            coverage_basis_points=basis_points,
            availability="limited",
            confidence="low",
            reason_codes=("EVIDENCE_COVERAGE_LIMITED",),
        )
    return EvidenceCoverageResult(
        coverage_basis_points=basis_points,
        availability="unavailable",
        confidence="unavailable",
        reason_codes=("EVIDENCE_COVERAGE_BELOW_MINIMUM",),
    )


def evaluate_concentration(
    *,
    total_user_picks: int,
    position_pick_counts: Mapping[str, int],
    unfilled_distinct_starter_positions: int,
) -> ConcentrationResult:
    if not _is_integer(total_user_picks) or total_user_picks < 1:
        raise ValueError("total_user_picks must be a positive integer")
    if not isinstance(position_pick_counts, Mapping) or not position_pick_counts:
        raise ValueError("position_pick_counts must not be empty")
    normalized_counts: dict[str, int] = {}
    for position, count in position_pick_counts.items():
        if not isinstance(position, str) or not position:
            raise ValueError("position keys must not be empty")
        if not _is_integer(count) or count < 0:
            raise ValueError("position counts must be non-negative integers")
        normalized_counts[position] = count
    if sum(normalized_counts.values()) != total_user_picks:
        raise ValueError("position counts must sum to total_user_picks")
    if (
        not _is_integer(unfilled_distinct_starter_positions)
        or unfilled_distinct_starter_positions < 0
    ):
        raise ValueError(
            "unfilled_distinct_starter_positions must be a non-negative integer"
        )

    maximum_basis_points = max(normalized_counts.values()) * 10_000 // total_user_picks
    if maximum_basis_points <= BALANCED_MAXIMUM_BASIS_POINTS:
        share_band: ConcentrationBand = "balanced_distribution"
    elif maximum_basis_points <= HIGHLY_CONCENTRATED_ABOVE_BASIS_POINTS:
        share_band = "concentrated"
    else:
        share_band = "highly_concentrated"

    bands: list[ConcentrationBand] = [share_band]
    if unfilled_distinct_starter_positions:
        if share_band == "balanced_distribution":
            bands.clear()
        bands.append("coverage_gap")
    return ConcentrationResult(
        maximum_share_basis_points=maximum_basis_points,
        bands=tuple(bands),
    )


def strategy_section_state(
    *,
    draft_mode: DraftMode,
    history_state: StrategyHistoryState = "valid",
) -> SectionState:
    if draft_mode not in ("live", "mock"):
        raise ValueError("draft_mode is not supported")
    if history_state not in ("valid", "incomplete", "corrupt"):
        raise ValueError("history_state is not supported")
    if draft_mode == "live":
        return SectionState(
            availability="not_applicable",
            confidence="unavailable",
            reason_codes=("LIVE_STRATEGY_NOT_APPLICABLE",),
        )
    if history_state == "valid":
        return SectionState(
            availability="supported",
            confidence="high",
            reason_codes=("MOCK_STRATEGY_HISTORY_AVAILABLE",),
        )
    if history_state == "incomplete":
        return SectionState(
            availability="limited",
            confidence="low",
            reason_codes=("MOCK_STRATEGY_HISTORY_LIMITED",),
        )
    return SectionState(
        availability="unavailable",
        confidence="unavailable",
        reason_codes=("MOCK_STRATEGY_HISTORY_CORRUPT",),
    )


def unsupported_section_state(section_key: str) -> SectionState:
    if not isinstance(section_key, str) or section_key not in UNSUPPORTED_SECTION_REASONS:
        raise ValueError("section_key is not an always-unavailable V1 section")
    return SectionState(
        availability="unavailable",
        confidence="unavailable",
        reason_codes=(UNSUPPORTED_SECTION_REASONS[section_key],),
    )


def render_explanation(
    *,
    template_key: str,
    values: Mapping[str, str | int],
) -> str:
    if not isinstance(template_key, str) or template_key not in EXPLANATION_TEMPLATES:
        raise ValueError("template_key is not supported")
    if not isinstance(values, Mapping):
        raise ValueError("values must be a mapping")
    template = EXPLANATION_TEMPLATES[template_key]
    required = {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name is not None
    }
    supplied = set(values)
    if supplied != required:
        raise ValueError("values must match the template placeholders exactly")
    if any(
        not isinstance(value, (str, int)) or isinstance(value, bool)
        for value in values.values()
    ):
        raise ValueError("template values must be strings or integers")
    return template.format_map(values)


def _validated_slots(slots: Sequence[StarterSlot]) -> tuple[StarterSlot, ...]:
    if not isinstance(slots, Sequence) or isinstance(slots, (str, bytes)):
        raise ValueError("starter_slots must be a sequence")
    if not slots or len(slots) > MAXIMUM_STARTER_SLOTS:
        raise ValueError(
            f"starter_slots must contain between 1 and {MAXIMUM_STARTER_SLOTS} slots"
        )
    if any(not isinstance(slot, StarterSlot) for slot in slots):
        raise ValueError("starter_slots must contain StarterSlot values")
    ordered = tuple(sorted(slots, key=lambda slot: slot.slot_order))
    if [slot.slot_order for slot in ordered] != list(range(len(ordered))):
        raise ValueError("slot_order values must be unique and contiguous from zero")
    slot_keys = [slot.slot_key for slot in ordered]
    if len(slot_keys) != len(set(slot_keys)):
        raise ValueError("slot_key values must be unique")
    return ordered


def _validated_roster(roster: Sequence[RosterPlayer]) -> tuple[RosterPlayer, ...]:
    if not isinstance(roster, Sequence) or isinstance(roster, (str, bytes)):
        raise ValueError("roster must be a sequence")
    if not roster or len(roster) > MAXIMUM_USER_ROSTER_PICKS:
        raise ValueError(
            f"roster must contain between 1 and {MAXIMUM_USER_ROSTER_PICKS} players"
        )
    if any(not isinstance(player, RosterPlayer) for player in roster):
        raise ValueError("roster must contain RosterPlayer values")
    player_ids = [player.canonical_player_id for player in roster]
    overall_picks = [player.overall_pick for player in roster]
    if len(player_ids) != len(set(player_ids)):
        raise ValueError("canonical_player_id values must be unique")
    if len(overall_picks) != len(set(overall_picks)):
        raise ValueError("overall_pick values must be unique")
    return tuple(
        sorted(
            roster,
            key=lambda player: (player.overall_pick, player.canonical_player_id),
        )
    )


def _maximum_matching_size(
    slots: Sequence[StarterSlot],
    roster: Sequence[RosterPlayer],
) -> int:
    ordered_players = tuple(
        sorted(
            roster,
            key=lambda player: (player.overall_pick, player.canonical_player_id),
        )
    )
    player_by_id = {
        player.canonical_player_id: player for player in ordered_players
    }
    matched_slot_by_player: dict[str, StarterSlot] = {}

    def augment(slot: StarterSlot, visited_players: set[str]) -> bool:
        for player_id, player in player_by_id.items():
            if player_id in visited_players or not _player_eligible(player, slot):
                continue
            visited_players.add(player_id)
            previous_slot = matched_slot_by_player.get(player_id)
            if previous_slot is None or augment(previous_slot, visited_players):
                matched_slot_by_player[player_id] = slot
                return True
        return False

    return sum(
        augment(slot, set())
        for slot in sorted(slots, key=lambda item: item.slot_order)
    )


def _lexicographically_smallest_maximum_assignment(
    slots: Sequence[StarterSlot],
    roster: Sequence[RosterPlayer],
    maximum_count: int,
) -> tuple[tuple[int, int, str], ...]:
    ordered_players = tuple(
        sorted(
            roster,
            key=lambda player: (player.overall_pick, player.canonical_player_id),
        )
    )
    used_player_ids: set[str] = set()
    chosen: list[tuple[int, int, str]] = []

    for index, slot in enumerate(slots):
        eligible = [
            player
            for player in ordered_players
            if player.canonical_player_id not in used_player_ids
            and _player_eligible(player, slot)
        ]
        options: list[RosterPlayer | None] = [*eligible, None]
        for option in options:
            next_used = set(used_player_ids)
            if option is not None:
                next_used.add(option.canonical_player_id)
            remaining_players = tuple(
                player
                for player in ordered_players
                if player.canonical_player_id not in next_used
            )
            achievable = (
                len(chosen)
                + (1 if option is not None else 0)
                + _maximum_matching_size(slots[index + 1 :], remaining_players)
            )
            if achievable != maximum_count:
                continue
            if option is not None:
                chosen.append(
                    (
                        slot.slot_order,
                        option.overall_pick,
                        option.canonical_player_id,
                    )
                )
                used_player_ids.add(option.canonical_player_id)
            break
        else:
            raise AssertionError("maximum assignment could not be reconstructed")
    return tuple(chosen)


def _ambiguous_flex_slot_keys(
    slots: Sequence[StarterSlot],
    roster: Sequence[RosterPlayer],
    assigned_by_slot: Mapping[int, str],
    maximum_count: int,
) -> tuple[str, ...]:
    ambiguous: list[str] = []
    for slot in slots:
        chosen_player_id = assigned_by_slot.get(slot.slot_order)
        if slot.slot_type not in FLEX_SLOT_TYPES or chosen_player_id is None:
            continue
        remaining_slots = tuple(
            candidate for candidate in slots if candidate.slot_order != slot.slot_order
        )
        for alternative in roster:
            if (
                alternative.canonical_player_id == chosen_player_id
                or not _player_eligible(alternative, slot)
            ):
                continue
            remaining_players = tuple(
                player
                for player in roster
                if player.canonical_player_id != alternative.canonical_player_id
            )
            if 1 + _maximum_matching_size(
                remaining_slots,
                remaining_players,
            ) == maximum_count:
                ambiguous.append(slot.slot_key)
                break
    return tuple(ambiguous)


def _player_eligible(player: RosterPlayer, slot: StarterSlot) -> bool:
    return bool(set(player.fantasy_positions).intersection(slot.eligible_positions))


def _has_incomplete_eligibility(roster: Sequence[RosterPlayer]) -> bool:
    supported_positions = set().union(*SUPPORTED_SLOT_ELIGIBILITY.values())
    return any(
        not player.fantasy_positions
        or any(
            position not in supported_positions
            for position in player.fantasy_positions
        )
        for player in roster
    )


def _depth_counts(
    roster: Sequence[RosterPlayer],
    assigned_player_ids: set[str],
) -> tuple[tuple[str, int], ...]:
    counts = Counter(
        player.primary_position
        for player in roster
        if player.canonical_player_id not in assigned_player_ids
    )
    all_positions = sorted({player.primary_position for player in roster})
    return tuple((position, counts[position]) for position in all_positions)


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
