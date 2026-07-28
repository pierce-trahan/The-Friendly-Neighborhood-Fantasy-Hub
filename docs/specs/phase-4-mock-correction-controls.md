# Phase 4 Module Specification: Mock Correction Controls

**Status:** Approved implementation slice

**Date:** 2026-07-28

## Outcome

This module makes the existing Phase 3 correction, undo, pause/resume, and
recoverable-reset controls safe for seeded Phase 4 mocks.

The Phase 3 draft session remains authoritative for the active pick state.
Phase 4 preserves CPU decisions, strategy guidance, and mock configuration as
append-only audit evidence around that state. No correction action selects a
player, changes a strategy, or erases historical reasoning.

## Public Contract

The existing Phase 3 endpoints remain authoritative:

- `PATCH /api/v1/draft-sessions/{session_id}/picks/{overall_pick}`;
- `POST /api/v1/draft-sessions/{session_id}/undo`;
- `PATCH /api/v1/draft-sessions/{session_id}` for pause/resume; and
- `POST /api/v1/draft-sessions/{session_id}/reset`.

Reset accepts the existing draft revision plus an optional replacement mock
seed. A seed is rejected for live drafts.

The Phase 4 mock response reports reset replay status:

- `original`: the mock is not a reset replacement;
- `exact_replay`: seed and frozen simulation inputs match the source mock;
- `new_seed`: frozen simulation inputs match but the seed changed;
- `snapshot_changed`: the fresh candidate or other frozen simulation snapshot
  differs, so exact replay is not claimed; or
- `unavailable`: the source mock configuration cannot be compared safely.

## Invariants

1. A Phase 3 correction or undo and its Phase 4 bookkeeping commit or roll back
   together.
2. Accepted mock corrections and undos increment both the draft revision and
   mock revision exactly once.
3. A CPU decision row is never deleted or rewritten.
4. A corrected or undone CPU decision is historical. If the same CPU turn is
   run again, only the newly saved decision is active, even when it chooses the
   same player.
5. Correcting a CPU pick makes the manual pick authoritative and labels its
   saved CPU audit as manually corrected.
6. Correcting or undoing a user pick appends a new strategy checkpoint based on
   the current user roster. Earlier guidance remains readable.
7. Correcting or undoing a CPU pick does not fabricate a user-roster
   checkpoint.
8. Guidance history is ordered by save time, not overall pick, because undo may
   move the current pick backward.
9. Undo while paused leaves the mock paused.
10. Pause/resume never creates a CPU pick or strategy event.
11. Reset marks the old draft as reset and leaves all old mock audit rows
    readable.
12. Reset creates a linked empty draft and mock configuration in one
    transaction.
13. Reset copies strategy, randomness, engine versions, league-shape snapshot,
    and CPU profile snapshots.
14. Reset keeps the seed unless an explicit valid replacement is supplied.
15. Learning consent on the replacement mock is always `false`.
16. Reset uses the fresh Phase 3 candidate snapshot and never claims an exact
    replay when its frozen content fingerprint changed.
17. Live-draft behavior remains unchanged.

## Error and Recovery Rules

- stale draft revision: existing safe `409`;
- concurrent mock mutation during correction, undo, or reset:
  `MOCK.STALE_REVISION` with complete rollback;
- reset seed on a live draft: `DRAFT.SEED_NOT_APPLICABLE`, `422`;
- invalid mock seed: `MOCK.INVALID_SEED`, `422`;
- reset mock missing Phase 4 configuration: preserve Phase 3 compatibility and
  perform the ordinary draft reset;
- database failure: roll back draft and mock changes together.

## Acceptance Tests

1. Correcting a CPU pick preserves its decision audit as historical and labels
   it manually corrected.
2. Undoing and identically re-advancing a CPU pick reproduces the chosen player
   and score while creating a new active decision audit.
3. Correcting a user pick appends current-roster guidance without rewriting the
   prior checkpoint.
4. Undoing and re-picking a user selection produces distinct ordered guidance
   events with correct roster counts.
5. Undo while paused preserves pause and blocks CPU advancement.
6. Pause/resume changes no mock decision or guidance row.
7. Reset preserves the old draft and mock history and creates linked empty
   replacement state.
8. Unchanged snapshots and seed report `exact_replay`.
9. An explicit new seed reports `new_seed`.
10. A changed fresh candidate snapshot reports `snapshot_changed`.
11. Replacement learning consent is off even when the source mock opted in.
12. Stale or injected failing mutations leave draft picks, guidance, decisions,
    replacement rows, and both revisions unchanged.
13. Restart restores the corrected, undone, paused, or replacement state.
14. Live-draft correction, undo, pause/resume, and reset remain compatible.

## Deferred

- deleting historical CPU decisions or guidance;
- editing a seed in place;
- automated resume or background CPU loops;
- multi-step rewind in one request;
- replaying against historical candidate snapshots instead of the required
  fresh Phase 3 reset snapshot; and
- learning-summary behavior, which remains the next Phase 4 backend slice.
