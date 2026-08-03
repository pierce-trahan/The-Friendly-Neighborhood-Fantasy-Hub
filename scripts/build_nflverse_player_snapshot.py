from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

SOURCE_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
)
LICENSE_URL = "https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md"
POSITION_MAP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "K": "K"}
STATUS_MAP = {
    "ACT": "active",
    "DEV": "active",
    "INA": "inactive",
    "CUT": "inactive",
    "RLS": "inactive",
    "NWT": "inactive",
    "PUP": "reserve",
    "RES": "reserve",
    "RSR": "reserve",
    "RSN": "reserve",
    "SUS": "reserve",
}
POSITION_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the offline Friendly Hub player snapshot from nflverse players.csv."
    )
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--source-updated-at", required=True)
    return parser.parse_args()


def integer(value: str | None) -> int | None:
    try:
        return int(value or "")
    except ValueError:
        return None


def build_snapshot(input_csv: Path, season: int, source_updated_at: str) -> dict[str, object]:
    content = input_csv.read_bytes()
    players_by_identity: dict[tuple[str, str, str | None], dict[str, object]] = {}
    seen_ids: set[str] = set()
    with input_csv.open(encoding="utf-8-sig", newline="") as input_file:
        for row in csv.DictReader(input_file):
            raw_position = (row.get("position") or "").strip().upper()
            position = POSITION_MAP.get(raw_position)
            last_season = integer(row.get("last_season"))
            rookie_season = integer(row.get("rookie_season"))
            if position is None or not (
                (last_season is not None and last_season >= season - 1)
                or rookie_season == season
            ):
                continue

            external_id = (row.get("gsis_id") or "").strip()
            name = " ".join((row.get("display_name") or "").split())
            if not external_id or not name:
                raise ValueError("Every included player must have a GSIS ID and display name.")
            if external_id in seen_ids:
                raise ValueError(f"Duplicate GSIS ID in included player pool: {external_id}")
            seen_ids.add(external_id)

            team = (row.get("latest_team") or "").strip().upper() or None
            player: dict[str, object] = {
                "name": name,
                "position": position,
                "fantasy_positions": [position],
                "team": team,
                "status": STATUS_MAP.get(
                    (row.get("status") or "").strip().upper(), "unknown"
                ),
                "rookie_class": rookie_season,
                "is_rookie": rookie_season == season,
                "provider": "nflverse",
                "external_id": external_id,
                "include": True,
            }
            identity_key = (name.casefold(), position, team)
            existing = players_by_identity.get(identity_key)
            if existing is not None:
                existing_id = str(existing["external_id"])
                if external_id.startswith("00-") and not existing_id.startswith("00-"):
                    players_by_identity[identity_key] = player
                    continue
                if existing_id.startswith("00-") and not external_id.startswith("00-"):
                    continue
                raise ValueError(
                    f"Ambiguous duplicate identity in included player pool: {name} {position}"
                )
            players_by_identity[identity_key] = player

    players = list(players_by_identity.values())

    players.sort(
        key=lambda player: (
            POSITION_ORDER[str(player["position"])],
            str(player["name"]).casefold(),
            str(player["external_id"]),
        )
    )
    return {
        "schema_version": 1,
        "source": {
            "name": "nflverse",
            "dataset": "players",
            "url": SOURCE_URL,
            "license": "CC BY 4.0",
            "license_url": LICENSE_URL,
            "source_asset_updated_at": source_updated_at,
            "source_sha256": hashlib.sha256(content).hexdigest(),
            "transformed": True,
            "changes": (
                "Filtered to recent fantasy positions; mapped FB to RB; retained only name, "
                "GSIS ID, latest team, position, status, and rookie season; resolved exact "
                "identity duplicates by preferring the canonical 00- GSIS ID."
            ),
        },
        "snapshot": {
            "season": season,
            "minimum_last_season": season - 1,
            "player_count": len(players),
        },
        "players": players,
    }


def main() -> None:
    args = parse_args()
    document = build_snapshot(args.input_csv, args.season, args.source_updated_at)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {document['snapshot']['player_count']} players to {args.output_json}")


if __name__ == "__main__":
    main()
