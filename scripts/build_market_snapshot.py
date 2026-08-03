from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

SUPPORTED_POSITIONS = {"QB", "RB", "WR", "TE"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip()).casefold()
    without_marks = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


def without_suffix(value: str) -> str:
    parts = normalize_name(value).split()
    if parts and parts[-1] in SUFFIXES:
        parts.pop()
    return " ".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the Friendly Hub's offline dynasty Superflex ECR snapshot."
    )
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("player_universe_json", type=Path)
    parser.add_argument("output_json", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_bytes = args.source_csv.read_bytes()
    with args.source_csv.open(encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    player_document = json.loads(args.player_universe_json.read_text(encoding="utf-8"))
    universe_rows = player_document.get("players")
    if not isinstance(universe_rows, list):
        raise TypeError("player universe must contain a players list")

    exact_index: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    suffix_index: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for player in universe_rows:
        if not isinstance(player, dict):
            continue
        name = player.get("name")
        position = player.get("position")
        if not isinstance(name, str) or position not in SUPPORTED_POSITIONS:
            continue
        exact_index[(normalize_name(name), position)].append(player)
        suffix_index[(without_suffix(name), position)].append(player)

    matched: list[tuple[float, str, dict[str, object], dict[str, str]]] = []
    unmatched_count = 0
    source_dates: set[str] = set()
    for row in source_rows:
        name = row.get("player", "").strip()
        position = row.get("pos", "").strip().upper()
        raw_ecr = row.get("ecr_2qb", "").strip()
        if position not in SUPPORTED_POSITIONS or not name or raw_ecr in {"", "NA"}:
            continue
        try:
            ecr = float(raw_ecr)
        except ValueError:
            continue
        if not math.isfinite(ecr) or ecr <= 0:
            continue
        candidates = exact_index.get((normalize_name(name), position), [])
        if len(candidates) != 1:
            candidates = suffix_index.get((without_suffix(name), position), [])
        if len(candidates) != 1:
            unmatched_count += 1
            continue
        source_date = row.get("scrape_date", "").strip()
        if source_date:
            source_dates.add(source_date)
        matched.append((ecr, name, candidates[0], row))

    if len(source_dates) != 1:
        raise ValueError("market source rows must share one non-empty scrape date")
    source_date = next(iter(source_dates))
    matched.sort(key=lambda item: (item[0], normalize_name(item[1])))

    seen_external_ids: set[str] = set()
    entries: list[dict[str, object]] = []
    for rank, (ecr, _source_name, player, _source_row) in enumerate(matched, start=1):
        external_id = player.get("external_id")
        player_name = player.get("name")
        position = player.get("position")
        if not isinstance(external_id, str) or not external_id:
            raise ValueError("every matched player must have an nflverse external ID")
        if external_id in seen_external_ids:
            raise ValueError(f"market snapshot repeats nflverse ID {external_id}")
        seen_external_ids.add(external_id)
        entries.append(
            {
                "market_rank": rank,
                "consensus_rank": ecr,
                "player_name": player_name,
                "search_name": normalize_name(str(player_name)),
                "position": position,
                "nflverse_id": external_id,
            }
        )

    document = {
        "schema_version": 1,
        "source": {
            "name": "DynastyProcess",
            "dataset": "values.csv",
            "url": "https://github.com/dynastyprocess/data/blob/master/files/values.csv",
            "license": "GPL-3.0",
            "license_url": "https://github.com/dynastyprocess/data/blob/master/LICENSE",
            "underlying_signal": "FantasyPros expert consensus rankings",
            "source_asset_updated_at": source_date,
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "transformed": True,
            "changes": (
                "Filtered to QB, RB, WR, and TE rows with ecr_2qb; conservatively "
                "matched normalized player name and position to the bundled nflverse "
                "universe; removed pick assets and unmatched identities; converted "
                "floating ECR order to a stable integer market rank."
            ),
        },
        "baseline": {
            "key": "dynasty_superflex_ecr",
            "label": "Dynasty Superflex expert consensus",
            "evidence_kind": "expert_consensus",
            "rank_type": "dynasty_2qb_ecr",
            "format": "dynasty_superflex_proxy",
            "player_count": len(entries),
            "unmatched_source_player_count": unmatched_count,
            "limitations": [
                "ECR_NOT_ADP",
                "TWO_QB_PROXY_FOR_SUPERFLEX",
                "TE_PREMIUM_NOT_EXPLICIT",
                "NO_AVAILABILITY_DISTRIBUTION",
            ],
        },
        "entries": entries,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
