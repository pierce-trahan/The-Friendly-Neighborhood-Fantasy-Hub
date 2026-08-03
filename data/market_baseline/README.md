# Bundled Market Baseline Data

`dynasty-superflex-ecr-2026-07-31.json` is a transformed, offline snapshot
derived from DynastyProcess's `files/values.csv` open-data file. The artifact
uses the `ecr_2qb` field as a dynasty Superflex proxy and matches rows
conservatively to the Hub's bundled nflverse player universe.

This signal is expert consensus ranking (ECR), not average draft position
(ADP). It has no completed-draft sample size, availability distribution, or
explicit tight-end-premium adjustment. Those limits travel with every new mock
snapshot and are displayed in the Mock Lab.

The transformed data artifact is distributed under the upstream repository's
GPL-3.0 license. The application code remains under the repository's MIT
license. Source, source date, transformation, content hash, license, and
license URL are embedded in the JSON artifact. The full upstream license is
preserved in `LICENSE-GPL-3.0.txt` beside the snapshot.

To rebuild after deliberately downloading an approved upstream file:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_market_snapshot.py `
  <path-to-values.csv> `
  .\data\player_universe\nflverse-players-2026.json `
  .\data\market_baseline\dynasty-superflex-ecr-YYYY-MM-DD.json
```

Never refresh this file automatically during application launch or a draft.
Review identity coverage, provenance, licensing, and mock behavior before
changing the release snapshot path.
