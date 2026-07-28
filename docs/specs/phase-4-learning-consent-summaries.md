# Phase 4 Module Specification: Learning Consent and Mock Summaries

**Status:** Approved implementation slice

**Date:** 2026-07-28

## Outcome

This module lets the user explicitly include or exclude an individual local
mock from a future tendency-profile rebuild and browse bounded, privacy-safe
mock history summaries.

Consent does not run a profile rebuild, alter a pick, change strategy history,
upload data, or claim that mock-generated behavior is real manager evidence.
It only records whether the saved mock may be considered by a later local
rebuild that applies its own evidence thresholds.

## Public Contract

### Learning consent

`PATCH /api/v1/mock-sessions/{session_id}/learning`

Request:

```json
{
  "mock_revision": 3,
  "include_in_learning": true
}
```

The endpoint:

- accepts active, paused, completed, and reset mock history;
- requires the exact mock revision;
- increments the mock revision exactly once;
- records the most recent opt-in timestamp when enabled;
- records the most recent withdrawal timestamp when disabled;
- preserves earlier opt-in or withdrawal timestamps as audit context;
- changes no draft revision, pick, decision, strategy revision, or guidance
  event; and
- returns the full authoritative mock response.

Submitting the current value is rejected as an unchanged action.

### Mock summaries

`GET /api/v1/boards/{board_id}/mock-sessions`

Query parameters:

- `limit`: default `20`, minimum `1`, maximum `100`; and
- `offset`: default `0`, minimum `0`.

The response is stable newest-first by creation timestamp and session ID. Each
summary contains:

- session ID and name;
- draft status and completion state;
- seed and randomness;
- current strategy and pivot count;
- exact mock revision for guarded consent changes;
- draft format, third-round reversal, team count, round count, and user slot;
- creation, latest update, completion, and reset timestamps;
- inclusion state plus latest opt-in and withdrawal timestamps; and
- RNG, CPU-engine, and strategy-definition versions.

The summary contains no player, candidate, decision alternative, Personal
Board note, private pivot note, provider identifier, manager reference, or
source payload.

## Completion States

- `incomplete`: draft status is `active` or `paused`;
- `completed`: draft status is `completed`; and
- `reset`: the historical source draft was recoverably reset.

A reset mock remains readable and may be included or excluded because its
history was not deleted. Replacement mocks always begin excluded, as specified
by the correction-controls module.

## Consent Semantics

1. `include_in_learning` defaults to `false`.
2. Opt-in is local and per mock.
3. Withdrawal is reversible.
4. Re-enabling updates `learning_opted_in_at` and preserves the last withdrawal
   timestamp.
5. Disabling updates `learning_withdrawn_at` and preserves the last opt-in
   timestamp.
6. Consent takes effect only in a future profile rebuild.
7. Consent does not bypass the history-derived profile evidence thresholds.
8. No cloud sharing, background task, or automatic rebuild is introduced.
9. A fallback profile remains labeled synthetic.
10. The summary list does not aggregate tendencies or produce a confidence
    score.

## Error and Recovery Rules

- missing board or mock: safe `404`;
- live draft passed to the learning endpoint: existing safe `409`;
- stale mock revision: `MOCK.STALE_REVISION`, `409`;
- unchanged inclusion state: `MOCK.LEARNING_UNCHANGED`, `409`;
- invalid paging: request validation `422`;
- database failure: complete rollback with no timestamp or revision change.

## Performance

- summary paging is bounded to `100`;
- total count uses one aggregate query;
- pivot counts for the current page use one grouped query;
- no per-summary query;
- no player, pick, decision, guidance, or private-note rows are loaded; and
- learning mutation updates one configuration and reads one full response.

## Acceptance Tests

1. New mocks are excluded by default.
2. Enabling learning with the exact revision changes only consent metadata and
   mock revision.
3. Disabling and re-enabling are reversible and preserve audit timestamps.
4. Stale and unchanged requests change no state.
5. Active, paused, completed, and reset mock histories may be toggled.
6. Replacement mocks created by reset remain excluded.
7. An injected failure rolls back inclusion, timestamps, and revision.
8. Restart restores consent state and timestamps.
9. Board summaries are scoped to the requested board.
10. Summary ordering and offset pagination are stable newest-first.
11. Completion states map correctly for active, paused, completed, and reset
    mocks.
12. Pivot count is derived without exposing private pivot notes.
13. Summary responses contain all documented engine and configuration fields.
14. Summary responses structurally exclude player, note, provider, manager,
    decision, and guidance data.
15. Listing uses bounded aggregate queries without N+1 behavior.

## Deferred

- rebuilding history-derived CPU profiles;
- importing real manager draft history;
- combining mocks with real drafts;
- tendency calculations or confidence bands;
- deleting mock history;
- cloud synchronization; and
- the desktop history and consent interface.
