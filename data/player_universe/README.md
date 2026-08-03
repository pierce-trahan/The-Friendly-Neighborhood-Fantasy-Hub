# Bundled Player Universe

`nflverse-players-2026.json` is a transformed snapshot derived from nflverse's
`players.csv` release. It is bundled so a fresh Friendly Hub installation has
players before any network connection or user import.

Source: <https://github.com/nflverse/nflverse-data/releases/tag/players>

License: [CC BY 4.0](https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md)

Upstream asset updated: 2026-08-02T09:52:58Z

Changes: the source was filtered to recent QB, RB/FB, WR, TE, and K records;
FB was mapped to RB; and only name, GSIS ID, latest team, position, status, and
rookie season were retained. One exact identity duplicate was resolved by
preferring the canonical `00-` GSIS ID. This project is not affiliated with or
endorsed by nflverse or the NFL.

To reproduce the artifact from an explicitly downloaded upstream CSV:

```powershell
python scripts/build_nflverse_player_snapshot.py `.data-staging/players.csv `
  data/player_universe/nflverse-players-2026.json `
  --season 2026 --source-updated-at 2026-08-02T09:52:58Z
```
