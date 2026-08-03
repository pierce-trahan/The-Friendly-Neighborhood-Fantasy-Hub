# V1 Bundled Player Universe Addendum

## Outcome

The Hub opens with a useful NFL player universe already stored in its local
SQLite database. A user does not have to create players, load demonstration
data, or connect to the internet before building a board.

## Approved Source and Attribution

The release snapshot is a transformed subset of the nflverse `players.csv`
dataset published through `nflverse-data`:

- source: <https://github.com/nflverse/nflverse-data/releases/tag/players>
- upstream loader contract: <https://github.com/nflverse/nflreadr/blob/main/R/load_players.R>
- license: CC BY 4.0
- license text: <https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md>

The committed snapshot preserves the source URL, upstream asset timestamp,
upstream SHA-256 hash, transformation notice, season, and row count. This
project is not affiliated with or endorsed by nflverse or the NFL.

## Snapshot Boundary

V1 includes records whose nflverse position is QB, RB, FB, WR, TE, or K and
whose latest season is the snapshot season or the preceding season, plus every
rookie whose rookie season equals the snapshot season. FB maps to the Hub's RB
position because V1 does not define a separate FB position.

Only these fields are retained:

- display name;
- GSIS ID, namespaced as an nflverse external ID;
- latest team;
- normalized fantasy position;
- normalized roster status; and
- rookie season and current-rookie flag.

Birth dates, physical measurements, colleges, headshots, and unrelated source
IDs are deliberately excluded.

When upstream contains the same normalized name, position, and latest team
under both a canonical `00-` GSIS ID and a temporary-looking ID, the build
keeps the canonical GSIS record. Any less certain duplicate stops the build for
human review.

## First-Launch Contract

After database migration and before the local API becomes ready, the backend:

1. validates the complete bundled snapshot and its declared row count;
2. checks for a previously committed import with the same content hash;
3. reuses exact nflverse external-ID mappings without changing player fields;
4. skips uncertain name-and-position collisions rather than accepting them;
5. creates every remaining canonical player and nflverse mapping;
6. marks seeded records relevant; and
7. commits the player rows and one provenance import record atomically.

If validation or persistence fails, the transaction rolls back. A repeated
launch with the same snapshot creates no players and changes no user data.

## Refresh and User-Authority Rules

- Runtime launch never downloads player data.
- A maintainer refreshes the committed snapshot with the repository build
  script, reviews its diff and provenance, and ships it in a normal release.
- A later snapshot may add new nflverse IDs, but automatic seeding does not
  overwrite names, teams, statuses, rookie fields, rankings, tiers, or notes on
  existing canonical players.
- CSV import and manual corrections remain optional power-user tools.

## Acceptance Criteria

- a fresh offline launch returns a populated relevant player list;
- the committed snapshot contains no duplicate nflverse IDs;
- the declared count equals the stored snapshot rows;
- repeat launch is idempotent;
- existing exact-ID records and manual fields are preserved;
- uncertain name-only collisions are not silently merged or duplicated;
- a malformed or missing production snapshot cannot partially seed the DB;
- source, license, timestamp, hash, transformation, and pool policy are visible
  in repository documentation and the player workspace; and
- the full V1 verification suite, production build, and offline launch pass.
