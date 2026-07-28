from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from friendly_hub.domains.mocks.definitions import (
    COMPONENT_BOUNDS,
    CPU_ENGINE_VERSION,
    MAX_RANDOM_CONSIDERATION_COUNT,
    MAX_RANDOMNESS,
    MAX_SEED,
    RNG_VERSION,
    SUPPORTED_FALLBACK_ARCHETYPES,
)

_RANDOM_VARIATION_PURPOSE = "candidate-random-variation"
_DRAW_DENOMINATOR = 1 << 64


@dataclass(frozen=True)
class DeterministicDraw:
    canonical_input: str
    digest_hex: str
    numerator: int

    @property
    def value(self) -> float:
        return self.numerator / _DRAW_DENOMINATOR


@dataclass(frozen=True)
class CandidateInput:
    player_id: str
    position: str
    practice_index: int


@dataclass(frozen=True)
class CandidateScoreInput:
    player_id: str
    practice_index: int
    starter_need: int = 0
    depth_need: int = 0
    archetype_fit: int = 0
    duplication_penalty: int = 0


@dataclass(frozen=True)
class ScoreComponents:
    board_order: int
    starter_need: int
    depth_need: int
    archetype_fit: int
    duplication_penalty: int
    random_variation: int

    @property
    def total(self) -> int:
        return sum(
            (
                self.board_order,
                self.starter_need,
                self.depth_need,
                self.archetype_fit,
                self.duplication_penalty,
                self.random_variation,
            )
        )


@dataclass(frozen=True)
class ScoredCandidate:
    player_id: str
    total_score: int
    components: ScoreComponents
    random_draw: DeterministicDraw


def normalize_seed(seed: str) -> str:
    if not isinstance(seed, str) or not seed or not seed.isascii() or not seed.isdecimal():
        raise ValueError("seed must be an unsigned decimal string")
    value = int(seed)
    if value > MAX_SEED:
        raise ValueError("seed must fit in an unsigned 64-bit integer")
    return str(value)


def content_fingerprint(snapshot: object) -> str:
    try:
        canonical_snapshot = json.dumps(
            snapshot,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("snapshot must contain only finite JSON values") from exc
    return hashlib.sha256(canonical_snapshot.encode("utf-8")).hexdigest()


def fallback_archetype_for_slot(seed: str, draft_slot: int) -> str:
    """Assign a stable synthetic profile without depending on database row IDs."""
    assignment_fingerprint = content_fingerprint(
        {
            "purpose": "fallback-profile-assignment",
            "supported_archetypes": SUPPORTED_FALLBACK_ARCHETYPES,
        }
    )
    draw = deterministic_draw(
        seed=seed,
        fingerprint=assignment_fingerprint,
        overall_pick=1,
        selecting_slot=draft_slot,
        purpose="fallback-profile-assignment",
        draw_index=0,
        stable_key=str(draft_slot),
    )
    return SUPPORTED_FALLBACK_ARCHETYPES[
        draw.numerator % len(SUPPORTED_FALLBACK_ARCHETYPES)
    ]


def deterministic_draw(
    *,
    seed: str,
    fingerprint: str,
    overall_pick: int,
    selecting_slot: int,
    purpose: str,
    draw_index: int,
    stable_key: str = "",
    rng_version: str = RNG_VERSION,
    engine_version: str = CPU_ENGINE_VERSION,
) -> DeterministicDraw:
    normalized_seed = normalize_seed(seed)
    if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
        raise ValueError("fingerprint must be a lowercase SHA-256 hex digest")
    if not _is_integer(overall_pick) or overall_pick < 1:
        raise ValueError("overall_pick must be at least 1")
    if not _is_integer(selecting_slot) or selecting_slot < 1:
        raise ValueError("selecting_slot must be at least 1")
    if not isinstance(purpose, str) or not purpose:
        raise ValueError("purpose must not be empty")
    if not _is_integer(draw_index) or draw_index < 0:
        raise ValueError("draw_index must not be negative")
    if (
        not isinstance(rng_version, str)
        or not rng_version
        or not isinstance(engine_version, str)
        or not engine_version
    ):
        raise ValueError("engine and RNG versions must not be empty")
    if not isinstance(stable_key, str):
        raise ValueError("stable_key must be a string")

    canonical_input = json.dumps(
        [
            engine_version,
            rng_version,
            normalized_seed,
            fingerprint,
            overall_pick,
            selecting_slot,
            purpose,
            draw_index,
            stable_key,
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(canonical_input.encode("utf-8")).digest()
    return DeterministicDraw(
        canonical_input=canonical_input,
        digest_hex=digest.hex(),
        numerator=int.from_bytes(digest[:8], byteorder="big", signed=False),
    )


def random_variation(draw: DeterministicDraw, randomness: int) -> int:
    _validate_randomness(randomness)
    exact_variation = Fraction(
        (2 * draw.numerator - _DRAW_DENOMINATOR) * 2 * randomness,
        _DRAW_DENOMINATOR,
    )
    return round(exact_variation)


def practice_board_score(candidate_count: int, practice_index: int) -> int:
    if not _is_integer(candidate_count) or candidate_count < 1:
        raise ValueError("candidate_count must be at least 1")
    if (
        not _is_integer(practice_index)
        or practice_index < 0
        or practice_index >= candidate_count
    ):
        raise ValueError("practice_index must identify a frozen candidate")
    return (candidate_count - practice_index) * 100


def build_consideration_set(
    candidates: Sequence[CandidateInput],
    *,
    randomness: int,
    unfilled_starter_positions: Iterable[str] = (),
    emphasized_position: str | None = None,
) -> tuple[CandidateInput, ...]:
    _validate_randomness(randomness)
    ordered = _validate_and_order_candidates(candidates)
    random_window = min(
        1 + randomness // 5,
        MAX_RANDOM_CONSIDERATION_COUNT,
    )
    included_ids = {candidate.player_id for candidate in ordered[:random_window]}
    for position in sorted(set(unfilled_starter_positions)):
        included_ids.update(
            candidate.player_id
            for candidate in _top_at_position(ordered, position, count=3)
        )
    if emphasized_position:
        included_ids.update(
            candidate.player_id
            for candidate in _top_at_position(
                ordered,
                emphasized_position,
                count=3,
            )
        )
    return tuple(candidate for candidate in ordered if candidate.player_id in included_ids)


def score_candidates(
    candidates: Sequence[CandidateScoreInput],
    *,
    candidate_count: int,
    seed: str,
    fingerprint: str,
    overall_pick: int,
    selecting_slot: int,
    randomness: int,
) -> tuple[ScoredCandidate, ...]:
    _validate_randomness(randomness)
    if not candidates:
        raise ValueError("at least one candidate must be scored")
    player_ids = [candidate.player_id for candidate in candidates]
    practice_indices = [candidate.practice_index for candidate in candidates]
    if any(not isinstance(player_id, str) or not player_id for player_id in player_ids):
        raise ValueError("player_id must not be empty")
    if len(player_ids) != len(set(player_ids)):
        raise ValueError("candidate player IDs must be unique")
    if len(practice_indices) != len(set(practice_indices)):
        raise ValueError("candidate practice indices must be unique")

    scored: list[ScoredCandidate] = []
    for candidate in candidates:
        draw = deterministic_draw(
            seed=seed,
            fingerprint=fingerprint,
            overall_pick=overall_pick,
            selecting_slot=selecting_slot,
            purpose=_RANDOM_VARIATION_PURPOSE,
            draw_index=0,
            stable_key=candidate.player_id,
        )
        components = ScoreComponents(
            board_order=practice_board_score(
                candidate_count,
                candidate.practice_index,
            ),
            starter_need=candidate.starter_need,
            depth_need=candidate.depth_need,
            archetype_fit=candidate.archetype_fit,
            duplication_penalty=candidate.duplication_penalty,
            random_variation=random_variation(draw, randomness),
        )
        _validate_components(components, candidate_count)
        scored.append(
            ScoredCandidate(
                player_id=candidate.player_id,
                total_score=components.total,
                components=components,
                random_draw=draw,
            )
        )
    return tuple(
        sorted(
            scored,
            key=lambda candidate: (-candidate.total_score, candidate.player_id),
        )
    )


def select_candidate(scored_candidates: Sequence[ScoredCandidate]) -> ScoredCandidate:
    if not scored_candidates:
        raise ValueError("at least one scored candidate is required")
    return min(
        scored_candidates,
        key=lambda candidate: (-candidate.total_score, candidate.player_id),
    )


def _validate_randomness(randomness: int) -> None:
    if not _is_integer(randomness):
        raise ValueError("randomness must be an integer")
    if randomness < 0 or randomness > MAX_RANDOMNESS:
        raise ValueError(f"randomness must be between 0 and {MAX_RANDOMNESS}")


def _validate_components(components: ScoreComponents, candidate_count: int) -> None:
    values: Mapping[str, int] = {
        "board_order": components.board_order,
        "starter_need": components.starter_need,
        "depth_need": components.depth_need,
        "archetype_fit": components.archetype_fit,
        "duplication_penalty": components.duplication_penalty,
        "random_variation": components.random_variation,
    }
    for name, value in values.items():
        if not _is_integer(value):
            raise ValueError(f"{name} score must be an integer")
        bound = COMPONENT_BOUNDS[name]
        maximum = candidate_count * 100 if name == "board_order" else bound.maximum
        if value < bound.minimum or (maximum is not None and value > maximum):
            raise ValueError(f"{name} score is outside the {CPU_ENGINE_VERSION} bounds")


def _validate_and_order_candidates(
    candidates: Sequence[CandidateInput],
) -> tuple[CandidateInput, ...]:
    player_ids = [candidate.player_id for candidate in candidates]
    practice_indices = [candidate.practice_index for candidate in candidates]
    if any(not isinstance(player_id, str) or not player_id for player_id in player_ids):
        raise ValueError("player_id must not be empty")
    if len(player_ids) != len(set(player_ids)):
        raise ValueError("candidate player IDs must be unique")
    if len(practice_indices) != len(set(practice_indices)):
        raise ValueError("candidate practice indices must be unique")
    if any(
        not _is_integer(candidate.practice_index) or candidate.practice_index < 0
        for candidate in candidates
    ):
        raise ValueError("practice_index must not be negative")
    if any(
        not isinstance(candidate.position, str) or not candidate.position.strip()
        for candidate in candidates
    ):
        raise ValueError("candidate position must not be empty")
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (candidate.practice_index, candidate.player_id),
        )
    )


def _top_at_position(
    candidates: Sequence[CandidateInput],
    position: str,
    *,
    count: int,
) -> tuple[CandidateInput, ...]:
    normalized_position = position.strip().upper()
    if not normalized_position:
        return ()
    return tuple(
        candidate
        for candidate in candidates
        if candidate.position.strip().upper() == normalized_position
    )[:count]


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)
