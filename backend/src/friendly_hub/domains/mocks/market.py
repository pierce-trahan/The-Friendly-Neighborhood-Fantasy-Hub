from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MarketEntry:
    market_rank: int
    consensus_rank: float
    search_name: str
    position: str


@dataclass(frozen=True)
class MarketSnapshot:
    label: str
    evidence_kind: str
    source_name: str
    source_url: str
    rank_type: str
    format: str
    source_as_of: str
    player_count: int
    limitations: tuple[str, ...]
    entries: tuple[MarketEntry, ...]


def load_market_snapshot(path: Path | None) -> MarketSnapshot | None:
    if path is None or not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("The bundled market baseline is not valid JSON.") from exc
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise RuntimeError("The bundled market baseline schema is not supported.")

    source = document.get("source")
    baseline = document.get("baseline")
    raw_entries = document.get("entries")
    if (
        not isinstance(source, dict)
        or source.get("name") != "DynastyProcess"
        or source.get("license") != "GPL-3.0"
        or not isinstance(baseline, dict)
        or baseline.get("evidence_kind") != "expert_consensus"
        or baseline.get("rank_type") != "dynasty_2qb_ecr"
        or not isinstance(raw_entries, list)
        or baseline.get("player_count") != len(raw_entries)
    ):
        raise RuntimeError("The bundled market baseline provenance is invalid.")

    entries: list[MarketEntry] = []
    seen_ranks: set[int] = set()
    seen_identities: set[tuple[str, str]] = set()
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise RuntimeError("The bundled market baseline contains an invalid row.")
        market_rank = raw.get("market_rank")
        consensus_rank = raw.get("consensus_rank")
        search_name = raw.get("search_name")
        position = raw.get("position")
        if (
            not isinstance(market_rank, int)
            or isinstance(market_rank, bool)
            or market_rank < 1
            or not isinstance(consensus_rank, (int, float))
            or isinstance(consensus_rank, bool)
            or consensus_rank <= 0
            or not isinstance(search_name, str)
            or not search_name
            or position not in {"QB", "RB", "WR", "TE"}
        ):
            raise RuntimeError("The bundled market baseline contains an invalid row.")
        identity = (search_name, position)
        if market_rank in seen_ranks or identity in seen_identities:
            raise RuntimeError("The bundled market baseline repeats a rank or player.")
        seen_ranks.add(market_rank)
        seen_identities.add(identity)
        entries.append(
            MarketEntry(
                market_rank=market_rank,
                consensus_rank=float(consensus_rank),
                search_name=search_name,
                position=position,
            )
        )
    if sorted(seen_ranks) != list(range(1, len(entries) + 1)):
        raise RuntimeError("The bundled market baseline ranks must be contiguous.")

    limitations = baseline.get("limitations")
    if not isinstance(limitations, list) or any(
        not isinstance(item, str) or not item for item in limitations
    ):
        raise RuntimeError("The bundled market baseline limitations are invalid.")
    required_text = {
        "label": baseline.get("label"),
        "source_name": source.get("name"),
        "source_url": source.get("url"),
        "rank_type": baseline.get("rank_type"),
        "format": baseline.get("format"),
        "source_as_of": source.get("source_asset_updated_at"),
    }
    if any(not isinstance(value, str) or not value for value in required_text.values()):
        raise RuntimeError("The bundled market baseline metadata is incomplete.")
    return MarketSnapshot(
        label=required_text["label"],
        evidence_kind=str(baseline["evidence_kind"]),
        source_name=required_text["source_name"],
        source_url=required_text["source_url"],
        rank_type=required_text["rank_type"],
        format=required_text["format"],
        source_as_of=required_text["source_as_of"],
        player_count=int(baseline["player_count"]),
        limitations=tuple(limitations),
        entries=tuple(sorted(entries, key=lambda entry: entry.market_rank)),
    )

