# Phase 3 Specification: Draft Room and Recoverable Draft State

**Status:** Approved for implementation

**Date:** 2026-07-26

## Outcome

Phase 3 adds a local draft room that is dependable enough to operate during a
real fantasy draft.

The module tracks draft order, completed picks, available players, the user's
next turn, and a stable snapshot of the draft board. Every write commits
immediately to SQLite, survives restart, and has an explicit correction path.

The draft room does not choose players. It keeps live state accurate while the
user remains the decision-maker.

## Scope

### Included

- live and mock draft sessions with a visible mode distinction;
- linear, snake, and third-round-reversal order calculation;
- configurable teams, team names, rounds, and user draft slot;
- a stable candidate snapshot from the relevant Player Universe and selected
  Personal Board;
- blind alphabetical, personal, positional, and tier views;
- available-player filtering and canonical-player search;
- immediate drafted-player removal;
- sequential pick entry;
- correction of any completed pick;
- undo of the latest completed pick;
- pause and resume;
- recoverable reset;
- current pick, selecting team, user-on-the-clock, and picks-until-user state;
- keyboard-friendly pick entry and undo;
- immediate transactional persistence and restart recovery; and
- human-readable draft-state CSV export.

### Excluded

- direct Sleeper or other provider live-draft synchronization;
- automated picks;
- CPU manager behavior and strategy simulation;
- auction drafts;
- keeper assignment;
- traded-pick ownership and future-pick trades;
- draft countdown enforcement or background alarms;
- ADP, consensus rank, market value, projections, or value alerts;
- roster-construction advice;
- player recommendations;
- player-and-pick trades;
- multi-user collaboration or cloud sync; and
- mobile-specific composition.

Mock automation belongs to Phase 4. Market and trade-up signals belong to Phase
5. V1 Phase 3 is a trustworthy manual draft-state instrument.

## Product Rules

1. A completed pick is never held only in browser memory.
2. Every state-changing request uses the existing local write guard and commits
   once.
3. The client submits the exact server revision. Stale or repeated writes are
   rejected without changing saved state.
4. Picks are entered sequentially. The server calculates the current pick and
   selecting team.
5. One canonical player may occupy at most one active pick in a session.
6. Correcting a pick makes the replaced player available and the replacement
   player unavailable in the same transaction.
7. Undo reverses only the latest active pick and reopens a completed draft when
   necessary.
8. Reset does not erase history. It closes the old session as reset and creates
   a new empty session with copied settings and a new candidate snapshot.
9. Draft order settings are frozen when a session starts.
10. The candidate and Personal Board context are snapshotted. Later imports or
    board edits do not silently rewrite an active or historical draft.
11. A player outside the original candidate snapshot may be found through
    canonical search and added as a late candidate when picked.
12. The blind alphabetical view never exposes manual rank, tier, note,
    favorite, Gut ELO, ADP, or market data.
13. The personal, position, and tier views may expose the user's snapshotted
    Personal Board context, but never provider or market rank.
14. Paused, completed, and reset sessions reject new picks.
15. Normal errors and logs do not contain Personal Board notes, provider IDs, or
    private league source payloads.

## Terminology

- **Session:** one recoverable live or mock draft.
- **Candidate:** a canonical player snapshotted into the session's available
  pool.
- **Board context:** the selected Personal Board's rank, tier, favorite, and
  optional note at session creation.
- **Draft slot:** a team's fixed position from `1` through `team_count`.
- **Overall pick:** the one-based sequential pick number.
- **Selecting slot:** the draft slot scheduled to make an overall pick.
- **Active pick:** the current saved assignment for an overall pick.
- **Correction:** replacement of the player assigned to an active pick.
- **Revision:** a monotonically increasing session integer changed by every
  accepted state mutation.
- **Picks until user:** the number of selections before the next scheduled pick
  belonging to the user's slot; `0` means the user is on the clock.

## Session Configuration

A session snapshots:

- name;
- mode: `live` or `mock`;
- selected Personal Board;
- optional internal league-profile reference;
- format: `linear` or `snake`;
- third-round reversal: on or off;
- team count from `2` through `32`;
- round count from `1` through `60`;
- user draft slot from `1` through `team_count`;
- optional pick-timer value for display only; and
- one display name per draft slot.

Third-round reversal is valid only for snake drafts. V1 reversal begins in round
three and cannot be assigned to another round.

The sanitized Entropy startup template is representable as:

- mode: `live`;
- format: `snake`;
- third-round reversal: on;
- teams: `10`;
- rounds: `24`; and
- display timer: `120` seconds.

The Entropy rookie template is representable as:

- format: `linear`;
- teams: `10`; and
- rounds: `3`.

Loading a league profile may prefill these fields, but the user confirms the
session configuration before creation. Provider draft identifiers never enter
the normal draft-session API.

## Draft Order Engine

The engine is a pure deterministic function of:

- format;
- third-round-reversal flag;
- team count;
- round count; and
- overall pick number.

For `team_count = N`:

### Linear

Every round selects slots `1` through `N`.

### Snake

- odd rounds select `1` through `N`;
- even rounds select `N` through `1`.

### Snake with third-round reversal

- round 1 selects `1` through `N`;
- round 2 selects `N` through `1`;
- round 3 also selects `N` through `1`;
- round 4 selects `1` through `N`; and
- later rounds alternate from that reversed parity.

For four teams:

| Round | Linear | Snake | Third-round reversal |
|---|---|---|---|
| 1 | 1, 2, 3, 4 | 1, 2, 3, 4 | 1, 2, 3, 4 |
| 2 | 1, 2, 3, 4 | 4, 3, 2, 1 | 4, 3, 2, 1 |
| 3 | 1, 2, 3, 4 | 1, 2, 3, 4 | 4, 3, 2, 1 |
| 4 | 1, 2, 3, 4 | 4, 3, 2, 1 | 1, 2, 3, 4 |
| 5 | 1, 2, 3, 4 | 1, 2, 3, 4 | 4, 3, 2, 1 |

The engine returns every pick's:

- overall pick;
- round;
- pick in round; and
- selecting slot.

The complete order is tested before persistence work uses it.

## Candidate Snapshot

Session creation snapshots:

1. every active relevant canonical player; and
2. every active entry on the selected Personal Board, even if the player is not
   currently marked relevant.

Duplicates collapse by canonical player ID.

Each candidate stores:

- canonical player ID;
- display name;
- primary position;
- fantasy positions;
- team;
- player status;
- rookie flag and rookie class;
- snapshot source: `relevant_pool`, `personal_board`, or `late_addition`;
- nullable starting manual rank;
- nullable starting tier name and color;
- starting favorite flag;
- nullable starting board note; and
- creation timestamp.

No provider identifier is stored in the candidate snapshot.

The normal response may include the board note only in personal and tier
contexts. Blind-view responses never include it.

V1 supports at most `2,000` candidates per session. A larger pool is rejected
with guidance to reduce the relevant universe.

## Draft Views

All views hide actively drafted candidates by default and may show them only
when the user enables a drafted-player audit filter.

### Blind alphabetical

Shows:

- display name;
- position;
- team;
- player status; and
- rookie label when applicable.

Sort is normalized display name, position, then canonical ID.

It does not return or render:

- manual rank;
- tier;
- note;
- favorite;
- Gut ELO rating or order;
- ADP;
- market value; or
- recommendation state.

### Personal

Shows Personal Board candidates first by starting manual rank, then unranked
candidates alphabetically. It may display snapshotted tier, favorite, and note.

The label is always `Personal rank`, never `Overall rank`.

### Position

Filters one or more canonical positions. Personal Board candidates sort by
starting manual rank; unranked candidates follow alphabetically with a visible
`Unranked` label.

### Tier

Groups ranked candidates by snapshotted tier order, then starting manual rank.
Unassigned Personal Board candidates appear in a separate group. Candidates
that were never on the board do not appear in tier view.

## Session State

Statuses:

- `active`;
- `paused`;
- `completed`; and
- `reset`.

Creation produces an active session at overall pick `1`.

The session completes after `team_count * round_count` active picks.

Pause:

- preserves current pick and all availability;
- rejects pick entry while paused; and
- survives restart.

Resume:

- returns a paused session to active;
- restores the same current pick; and
- does not change candidate or order snapshots.

Reset:

- requires the current revision;
- increments the old session revision once;
- marks the old session `reset`;
- creates a new active session linked by `reset_from_session_id`;
- copies configuration and team names;
- creates a fresh candidate snapshot from current local data; and
- leaves the old session readable and exportable.

## Pick Entry

A make-pick request contains:

- session revision;
- expected overall pick;
- canonical player ID; and
- optional client-entered timestamp for display, while server time remains
  authoritative.

The server validates:

- session is active;
- revision matches;
- expected overall pick equals the current pick;
- player exists canonically;
- player is not already assigned to another active pick; and
- total draft capacity is not exhausted.

If the player is outside the candidate snapshot, the server snapshots that
canonical player as a late addition before completing the pick.

Candidate addition and pick assignment commit in the same transaction.

## Correct Pick

Any active completed pick may replace its player.

A correction request contains:

- session revision;
- target overall pick;
- expected current player ID; and
- replacement canonical player ID.

The expected current player protects against correcting stale state.

The server:

1. validates the target and replacement;
2. rejects a replacement already used by another active pick;
3. appends a pick revision;
4. updates the active assignment;
5. makes the replaced player available;
6. removes the replacement from availability; and
7. increments the session revision once.

Round, pick-in-round, and selecting slot cannot be corrected because they come
from the frozen deterministic order. A configuration mistake uses recoverable
reset.

## Undo

Undo targets the latest active overall pick only.

The server:

- requires the current revision;
- appends an undo revision;
- clears the active player assignment for that pick;
- makes that player available;
- increments session revision;
- moves current pick back to that overall pick; and
- reopens a completed session as active.

Repeated undo may walk backward one pick at a time. Undo with no active picks
returns `409`.

## Persistence Model

### `draft_session`

- `id`: UUID string;
- `name`;
- `board_id`;
- nullable `league_profile_id`;
- `mode`;
- `format`;
- `third_round_reversal`;
- `team_count`;
- `round_count`;
- `user_slot`;
- nullable `pick_timer_seconds`;
- `status`;
- `revision`;
- nullable `reset_from_session_id`;
- `created_at`, `updated_at`, nullable `completed_at`, and nullable
  `reset_at`.

### `draft_team`

- `id`;
- `session_id`;
- `draft_slot`;
- `display_name`;
- `is_user`; and
- unique `(session_id, draft_slot)`.

### `draft_candidate`

- `id`;
- `session_id`;
- `player_id`;
- canonical display snapshot fields;
- board-context snapshot fields;
- `snapshot_source`;
- `created_at`; and
- unique `(session_id, player_id)`.

### `draft_pick`

- `id`;
- `session_id`;
- `overall_pick`;
- `round_number`;
- `pick_in_round`;
- `selecting_slot`;
- nullable `current_player_id`;
- `active`;
- `created_at`; and
- `updated_at`.

Unique constraints:

- `(session_id, overall_pick)`; and
- `(session_id, current_player_id)` for non-null active assignments.

### `draft_pick_revision`

- `id`;
- `session_id`;
- `pick_id`;
- `session_revision`;
- action kind: `made`, `corrected`, or `undone`;
- nullable `previous_player_id`;
- nullable `next_player_id`;
- `created_at`; and
- unique `(session_id, session_revision)`.

Pick revisions preserve audit and recovery history but normal draft-board
responses expose only current active state.

## API Contract

### Sessions

- `GET /api/v1/boards/{board_id}/draft-sessions`
  - newest-first summaries.
- `POST /api/v1/boards/{board_id}/draft-sessions`
  - validates configuration;
  - snapshots teams and candidates;
  - returns the full session at pick one.
- `GET /api/v1/draft-sessions/{session_id}`
  - full state, current pick, user distance, teams, picks, and view counts.
- `PATCH /api/v1/draft-sessions/{session_id}`
  - pause or resume with revision.
- `POST /api/v1/draft-sessions/{session_id}/reset`
  - performs recoverable reset and returns the new session.

### Candidate views

- `GET /api/v1/draft-sessions/{session_id}/candidates`
  - parameters: `view`, `search`, `position`, `include_drafted`, `limit`, and
    `offset`;
  - blind view uses a response schema that cannot contain board context.

### Picks

- `POST /api/v1/draft-sessions/{session_id}/picks`
  - saves the current pick.
- `PATCH /api/v1/draft-sessions/{session_id}/picks/{overall_pick}`
  - corrects a completed pick.
- `POST /api/v1/draft-sessions/{session_id}/undo`
  - undoes the latest active pick.

### Export

- `GET /api/v1/draft-sessions/{session_id}/export.csv`

CSV columns:

- session name;
- mode;
- format;
- third-round reversal;
- overall pick;
- round;
- pick in round;
- selecting slot;
- selecting team;
- player display name;
- player position;
- player team;
- pick recorded at; and
- correction count.

The export excludes provider IDs, Personal Board notes, ADP, market values, and
source payloads.

## Full Session Response

The session response includes:

- identity and immutable configuration;
- status and revision;
- teams;
- total picks and active pick count;
- nullable current overall pick, round, pick in round, and selecting team after
  completion or reset;
- user-on-the-clock boolean;
- nullable picks-until-user;
- active completed picks newest first;
- candidate total and available count;
- selected Personal Board identity;
- mode and blind-data guard flags;
- timestamps; and
- recovery guidance when paused, completed, or reset.

Candidate rows are loaded through the bounded candidate endpoint rather than
embedding up to 2,000 players in every session mutation response.

## Desktop Interaction Contract

The draft room follows the approved editorial-workstation direction.

### Persistent draft strip

Always visible:

- session mode;
- current overall and round pick;
- selecting team;
- user slot;
- picks until user;
- pause/resume;
- undo; and
- local-saved state.

### Main operating surface

- dense available-player table;
- view tabs for Blind, Personal, Position, and Tier;
- search and position filters;
- drafted-player audit toggle;
- explicit `Draft` action on each available row; and
- no market-rank column.

### Pick rail

- recent completed picks;
- selecting team and player;
- correction action;
- current-pick marker; and
- reset/export controls separated from fast entry.

### Keyboard

- `/` focuses player search;
- arrow keys move through visible candidate rows;
- `Enter` opens the explicit pick confirmation state for the focused row;
- `Escape` cancels that state;
- `U` invokes undo when focus is not inside a form field; and
- shortcuts are visible in the interface.

V1 may use a lightweight inline confirmation row rather than a modal. Pick
entry must never rely on an unlabeled row click.

## Autosave and Crash Recovery

- The backend is authoritative.
- The client does not optimistically remove a player before the server returns.
- Every mutation returns the committed revision and current draft state.
- Application restart runs migrations, opens SQLite, and restores the session
  from saved rows.
- There is no manual Save button.
- Browser storage may remember presentation choices such as the last view, but
  it never stores authoritative picks.
- A database error rolls back candidate and pick changes together.

## Privacy and Logging

- Draft sessions are local and private.
- Public fixtures use fictional players and sanitized league profiles.
- Provider league and draft IDs remain local source data and do not appear in
  normal responses, CSV exports, errors, or logs.
- Personal Board notes appear only in explicitly personal draft views.
- Blind responses are structurally incapable of containing board rank, tier,
  favorite, or note fields.
- Correlation IDs may appear in errors; player names and notes do not.

## Limits and Performance

- maximum teams: `32`;
- maximum rounds: `60`;
- maximum total picks: `1,920`;
- maximum candidates: `2,000`;
- default candidate page size: `75`;
- maximum candidate page size: `250`;
- pick entry and undo must complete within an interactive local request; and
- list endpoints use indexed, bounded queries without per-row count queries.

## Error and Recovery Rules

- missing board, session, player, or pick: safe `404`;
- archived board starting a new session: `409`;
- fewer than two candidates: `409`;
- invalid configuration: `422`;
- third-round reversal on linear draft: `422`;
- player already drafted: `409` with the existing pick number;
- stale revision, current pick, or correction target: `409`;
- pick while paused, completed, or reset: `409`;
- undo with no picks: `409`;
- correction to the same player: `422`;
- more than 2,000 candidates: `409`; and
- database failure: rollback with generic recovery guidance.

## Acceptance Tests

1. Linear, snake, and third-round-reversal orders match documented fixtures.
2. A valid session snapshots teams and the deduplicated relevant/board pool.
3. Archived boards and invalid configurations are rejected.
4. Session creation and every mutation survive application restart.
5. A current pick saves once and immediately disappears from available views.
6. A stale or repeated pick submit changes no state.
7. The same player cannot occupy two active picks.
8. A canonical player outside the snapshot can be added and picked
   transactionally.
9. Correction swaps availability and preserves pick/order metadata.
10. Stale correction targets change no state.
11. Undo returns the latest player to availability and current pick moves back.
12. Repeated undo walks backward and can reopen a completed session.
13. Pause/resume preserves the exact current pick and rejects paused writes.
14. Reset preserves the old session and creates a linked empty session.
15. Picks-until-user is correct at the beginning, on the clock, between user
    turns, and after completion.
16. Blind responses contain no rank, tier, note, favorite, Gut ELO, provider,
    ADP, or market fields.
17. Personal, position, and tier views sort exactly as specified.
18. Candidate paging remains deterministic after picks and corrections.
19. Export order matches active pick order and excludes private fields.
20. The desktop client submits exact revision/current-pick guards and recovers
    from a server rejection without optimistic loss.

## Exit Criteria

Phase 3 is complete when:

- a real 10-team, 24-round third-round-reversal startup is representable;
- every completed pick persists and can be corrected;
- restart restores the exact latest state;
- current pick and picks-until-user remain correct;
- the entire draft can operate without exposing ADP;
- blind mode structurally hides personal and market context;
- reset preserves history;
- the relevant player pool remains responsive; and
- full verification plus a desktop live workflow audit pass.
