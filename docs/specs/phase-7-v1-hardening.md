# Phase 7 V1 Draft-Night Hardening Specification

**Status:** Frozen for implementation
**Release target:** V1.0.0
**Frozen:** 2026-08-03
**Roadmap boundary:** Phase 7 — Draft-Night Hardening

## Purpose

Phase 7 stabilizes the completed Draft Lab for a real draft-night rehearsal. It
does not add another analytical module. V1 is ready only when a non-technical
user can launch the Hub, complete and recover the core workflow without a
network connection, and leave with portable board and draft-state backups.

## Feature Freeze

No new recommendation type, data provider, deployment model, automated draft
action, or season-management workflow may enter V1. The following remain
deferred exactly as recorded in the roadmap:

- waiver and free-agent recommendations;
- projections and start/sit decisions;
- player-plus-pick trade calculation;
- automated drafting;
- required cloud infrastructure; and
- traditional desktop packaging beyond the approved local-browser launcher.

Only release-blocking correctness, recovery, clarity, accessibility, privacy,
performance, packaging, and documentation changes are permitted in Phase 7.

## Canonical Draft-Night Snapshot

The release rehearsal uses a privacy-safe representation of the public Sleeper
configuration refreshed on 2026-08-03 at 13:39:45 UTC. Provider account and
roster identifiers are deliberately excluded.

- league: Entropy, 2026 dynasty, pre-draft;
- teams: 10;
- lineup: 1 QB, 2 RB, 2 WR, 1 TE, 3 FLEX, 1 SUPER_FLEX, 10 bench;
- draft: 24-round snake with third-round reversal;
- pick timer: 120 seconds;
- user's assigned slot: 1;
- scheduled start: 2026-08-04 at 00:00:41 UTC; and
- core scoring: full PPR, four-point passing touchdowns, 0.5 TE reception
  premium, and 0.5 TE receiving-first-down premium.

The repository stores only normalized settings, timestamps, and anonymous slot
labels. A source refresh may change the rehearsal evidence, but it may not
silently rewrite an in-progress saved draft.

## Required Release Behavior

### Launch and shutdown

1. `Launch Friendly Hub.cmd` remains the one-click Windows entry point.
2. The launcher binds only to `127.0.0.1`, opens the system browser after the
   health endpoint succeeds, and keeps the service alive until the launcher
   window is closed or interrupted.
3. A missing environment or frontend build produces an actionable setup message
   and never modifies production data.
4. The release instructions distinguish first-time setup from routine launch.

### Persistence and recovery

1. Board edits and every draft mutation are committed locally before the UI
   reports success.
2. Restart restores the authoritative board, active pick, pick history, draft
   revision, alert history, mock strategy history, and completed reports.
3. Undo and correction remain revision-guarded and never create a duplicate
   active pick.
4. Reset remains explicit and does not erase the auditable session record.
5. Recovery instructions identify the local data directory and a reversible
   backup procedure.

### Offline operation and exports

1. The Entropy profile, player import fixture, personal board, Gut ELO, live
   draft, mock, alerts, and reports work without an external service after setup.
2. A 10-team, 24-round, slot-1 third-round-reversal mock completes with network
   connections blocked.
3. Personal Board CSV and draft-state CSV exports remain available from their
   primary workspaces.
4. Draft CSV preserves active pick order and excludes private notes, hidden
   recommendation inputs, seeds, and provider identifiers.
5. Post-draft HTML remains standalone and free of scripts or remote assets.

### Release clarity

1. The application identifies itself as V1 rather than an earlier phase or
   proof.
2. The Overview gives a non-technical user a short draft-night path and explains
   autosave, restart recovery, and the two critical CSV backups.
3. No unfinished or out-of-scope control is presented as usable.
4. Honest `unavailable` evidence states required by approved module contracts
   remain visible; they are not unfinished controls.
5. The desktop workspaces are readable at 1440 by 900 pixels without blocking
   the primary action.

## Release Verification

The release candidate must pass all of the following from a clean checkout:

- backend Ruff checks;
- the complete backend test suite;
- generated API contracts with no unexpected diff;
- frontend API generation and TypeScript checks;
- the complete frontend test suite;
- a production frontend build;
- a high-severity dependency audit;
- the Phase 7 slot-1 offline rehearsal;
- restart, autosave, undo, correction, board export, draft export, and report
  export assertions;
- a privacy scan of committed files and generated audit artifacts; and
- desktop visual smoke at the intended screen size.

## Release Gate and Rollback Triggers

V1 may publish only when there is no known data-loss defect, no blocker in the
core pick workflow, and all roadmap release-gate statements are evidenced in the
Phase 7 audit.

Stop the release and return to the last known-good `main` commit if any of these
occur:

- a saved board or pick is missing after restart;
- undo or correction corrupts active pick order;
- the full mock needs a network connection or cannot finish;
- either critical CSV export fails or leaks a private marker;
- the launcher binds outside localhost;
- a critical control is obscured at the target desktop size; or
- any required verification command fails.

The rollback is code-only. Production data must be copied to a timestamped local
backup before database recovery work; it must never be deleted as part of a
rollback.

## Acceptance Criteria

1. The refreshed sanitized snapshot matches the current 10-team, 24-round,
   third-round-reversal, slot-1 Entropy configuration.
2. A complete slot-1 mock passes offline within the established 120-second
   rehearsal guard.
3. Restart returns the exact saved draft revision, current pick, and history.
4. Undo and correction pass before the rehearsal finishes.
5. Board and draft CSV exports are available and privacy-safe.
6. The launcher and recovery documentation can be followed without developer
   terminology.
7. The desktop visual smoke passes at 1440 by 900 pixels.
8. All repository verification checks pass.
9. The final audit maps every Phase 7 checklist item and release gate to evidence.
10. The versioned release candidate is merged to `main` with a clean worktree.
