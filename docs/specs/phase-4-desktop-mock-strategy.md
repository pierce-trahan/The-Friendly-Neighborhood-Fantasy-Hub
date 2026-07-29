# Phase 4 Desktop Mock Strategy Module

Status: approved for implementation on `agent/phase-4-desktop-mock-strategy`

## Outcome

Add a dedicated desktop Mock Lab that exposes the approved Phase 4 mock
strategy APIs without placing simulation controls in the live Draft Room.
The Mock Lab is a practice rehearsal: CPU teams may advance, but the user's
team remains a manual, explicitly confirmed decision.

## Boundaries

### Included

- board-scoped mock history and recoverable session reopening;
- mock creation with seed, randomness, strategy, league shape, and user slot;
- a persistent `Practice simulation` strip with both revisions;
- one CPU pick per HTTP mutation;
- a frontend `Run to my pick` loop that waits for each saved response;
- a safe `Stop after current pick` control;
- manual, confirmed user picks from the Phase 3 candidate API;
- visible CPU profile source, last-decision explanation, guidance, strategy
  limitations, and recovery guidance;
- append-only strategy pivots that explain they affect future guidance only;
- default-off, reversible learning consent with plain-language copy;
- keyboard shortcuts `R` and `S` outside form fields; and
- a separate navigation destination so live sessions never show mock controls.

### Deferred

- automatic user picks or player recommendations;
- bulk or server-side run-to-user mutation;
- unlabeled row actions that advance a CPU pick;
- fake clocks, countdowns, or remote/background execution;
- history-derived manager claims without an approved normalized fixture; and
- visual-regression infrastructure.

## Component Contract

`MockWorkspace` owns one board-scoped rehearsal workspace:

1. It loads Personal Boards.
2. It lists mock summaries for the selected board.
3. It creates or reopens one full `MockSessionRead`.
4. It loads Phase 3 candidates for the active mock.
5. It serializes every mutation and refreshes authoritative state after a
   rejected revision guard.

The ordinary `DraftWorkspace` remains the live-room surface and receives no
mock automation controls.

## Run Loop State Machine

The client loop has four states: `idle`, `running`, `stopping`, and `error`.

- `Advance one CPU pick` sends one guarded request and stops.
- `Run to my pick` sends one guarded request, awaits the full saved response,
  renders it, then re-evaluates eligibility.
- `Stop after current pick` sets a local stop flag. An in-flight request may
  finish, but no next request begins.
- The loop stops on user turn, pause, completion, reset, explicit stop, or any
  error.
- A rejection triggers `GET /mock-sessions/{id}` before another action is
  allowed.

No interval, timer, optimistic pick, parallel request, or automatic user pick
is permitted.

## Interaction Contract

- Candidate rows use a two-step `Draft` then `Confirm pick` interaction.
- User-pick controls are enabled only when `user_on_the_clock` is true.
- Strategy pivots require the current mock revision and current overall pick.
- Strategy limitations and insufficient-evidence guidance remain visible.
- Fallback CPU profiles are labeled `Fallback model`, never learned behavior.
- Learning consent starts off unless the saved session explicitly says
  otherwise, and changing it never changes picks.
- `R` starts a run only when CPU advancement is currently allowed.
- `S` requests a stop only while a run is active.
- Both shortcuts ignore inputs, selects, textareas, and editable content.

## Acceptance Tests

1. Mock creation submits all visible settings and defaults learning consent off.
2. A single advance sends exact draft, mock, pick, and slot guards.
3. Run-to-user sends one request at a time and stops on the user slot.
4. Stop prevents the next request after the current response.
5. Errors refresh the server-owned session before controls are re-enabled.
6. No user pick is sent without explicit two-step confirmation.
7. Strategy pivots leave completed picks intact and render new guidance.
8. Limitations and fallback profile labels are visible.
9. Learning consent is off by default and reversible.
10. `R` and `S` do nothing inside form fields.
11. The live Draft Room has no mock-run controls.
12. Typecheck, frontend tests, production build, and repository verification
    pass before publication.
