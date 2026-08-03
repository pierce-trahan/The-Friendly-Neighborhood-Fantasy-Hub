# Phase 7 V1 Release Audit

**Status:** PASS — ready for V1.0.0 publication
**Audit date:** 2026-08-03
**Specification:**
[Phase 7 V1 Draft-Night Hardening](../specs/phase-7-v1-hardening.md)
**Target:** Windows local-browser application at 1440 by 900 pixels

## Release Decision

The V1 release gate passes. No known data-loss defect or core pick-workflow
blocker remains. The current release candidate completes the canonical Entropy
startup shape without an external service, restores accepted work after
restart, provides Personal Board and draft-state CSV exports, produces a
standalone post-draft report, creates verified private database backups, and
launches only on localhost.

Phase 7 remained a hardening boundary. No waiver, projection, automated draft,
player-plus-pick trade, season-management, cloud, or unapproved data feature was
introduced.

## Canonical Rehearsal Evidence

The public Sleeper configuration was refreshed read-only on 2026-08-03 at
13:39:45 UTC and sanitized before repository use. The committed snapshot
records:

- 10 teams;
- 24 startup rounds;
- 120-second pick timer;
- snake order with third-round reversal;
- user slot 1 with anonymous remaining slots;
- full PPR;
- 0.5 TE reception premium; and
- 0.5 TE receiving-first-down premium.

Provider account, league, roster, and manager identifiers are absent from the
fixture and committed audit evidence.

`backend/tests/test_phase7_v1_release.py` completed a slot-1 offline rehearsal
with 260 fictional players and 240 picks. It exercised:

- the user opening from pick 1;
- correction of the first pick;
- undo and repick;
- process restart after an accepted pick;
- exact revision, pick-history, and current-pick restoration;
- all remaining user and CPU picks with network connections blocked;
- completed-draft report generation;
- Personal Board CSV export;
- draft-state CSV export and private-marker scan; and
- standalone HTML export with no script or remote asset.

Result: pass in 7.00 seconds, below the 120-second guard.

## Cross-Phase Workflow Evidence

`scripts/audit_phase6_workflow.py` passed again against the V1 candidate:

- three completed 10-team, 24-round, third-round-reversal drafts;
- 720 completed picks;
- three deterministic reports restored identically after restart;
- idempotent report generation;
- saved alert evidence present;
- compatible comparison and standalone HTML export;
- no network connection during report operations;
- unchanged source domains; and
- response, log, CSV, and HTML privacy scans passed.

Observed Phase 6 audit timings in seconds:

| Operation | Result |
|---|---:|
| Report generation | 0.0395, 0.0215, 0.0167 |
| Saved report reads | 0.0602, 0.0043, 0.0032 |
| Idempotent generation | 0.0241 |
| Comparison | 0.0042 |
| Standalone HTML export | 0.0039 |

## Backup and Launcher Evidence

Four Phase 7 backup and launcher tests passed:

1. SQLite backup uses the SQLite backup API, passes `PRAGMA integrity_check`,
   stores a SHA-256 manifest, and leaves the source byte-for-byte unchanged.
2. A manual backup still works when automatic backup preference is disabled.
3. Retention removes only managed expired backup ZIPs and leaves unrelated
   files untouched.
4. The launcher creates the verified pre-launch backup and binds Uvicorn only
   to `127.0.0.1:8765`.

The user-facing `scripts/backup.ps1` rehearsal created and verified a private
backup ZIP successfully. The recovery guide preserves both the current database
and selected backup before any restore; restore is not automatic because an
older backup could replace newer picks.

## Desktop Visual Audit

The built production interface was served from a temporary local data directory
and inspected in the in-app browser with an explicit 1440 by 900 viewport.

- Overview identified `Local Draft Lab · V1.0` and application `v1.0.0`.
- Local database health and the no-network core posture were visible.
- The refreshed Entropy timestamp rendered as August 3, 2026, 8:39 AM CDT.
- The draft-night call sheet and primary `Rehearse a mock` action were visible
  in the first viewport; the action bottom was at 882 pixels.
- Document width was 1425 pixels within a 1440-pixel viewport, with no
  horizontal overflow.
- Boards and Draft room empty states explained the next required action.
- V1 workspace labels replaced developmental phase labels.
- Browser console warning and error count was zero.

No unfinished or out-of-scope control was visible. Approved `unavailable`
evidence states remain because they are honest module behavior rather than
unfinished features.

## Full Repository Verification

`scripts/verify.ps1` passed after the final compatibility fix:

| Check | Result |
|---|---|
| Ruff | Pass |
| Backend tests | 149 passed in 73.33 seconds |
| OpenAPI generation | Pass |
| Frontend API generation | Pass |
| TypeScript | Pass |
| Frontend tests | 39 passed across 10 files |
| Production build | Pass |
| npm high-severity audit | 0 vulnerabilities |

The first full run correctly stopped the release when the refreshed TE reception
premium exposed an ambiguity in the alert-format parser. The parser now selects
the unscoped base reception rule for PPR and keeps scoped TE bonus rules
separate. The 24 directly affected Phase 5/6 tests passed, followed by the clean
149-test full run above.

## Privacy and Publication Checks

- committed fixture contains no public-provider account, league, roster, or
  manager identifiers;
- targeted forbidden-identifier scan: zero hits;
- likely secret-assignment scan: zero hits;
- test data and browser audit data remained under ignored temporary paths;
- production data was not used by automated tests; and
- generated contracts match the current API.

## Roadmap and Release-Gate Traceability

| Phase 7 requirement | Evidence | Result |
|---|---|---|
| Freeze non-critical features | Frozen specification and release diff | Pass |
| Actual settings and pick order | Refreshed sanitized slot-1 fixture | Pass |
| Full-speed mock | 240-pick offline Phase 7 rehearsal | Pass |
| Autosave, recovery, undo, export | Restart, correction, undo, CSV, HTML assertions | Pass |
| Refresh and timestamp data | 2026-08-03 UTC source timestamp visible in UI | Pass |
| No-network fallback | Blocked-socket rehearsal and draft-night guide | Pass |
| Intended desktop size | 1440 by 900 visual and overflow inspection | Pass |
| Hide unfinished controls | V1 label and workspace audit | Pass |
| Simple launch and recovery | CMD launcher, pre-launch backup, V1 guide | Pass |
| No known data-loss bug | Full persistence suite and backup integrity tests | Pass |
| No core pick blocker | Complete mock plus cross-phase 720-pick run | Pass |
| Understandable critical controls | Visual audit and explicit call sheet | Pass |
| Board and draft-state backups | Primary-workspace CSV exports | Pass |

## Rollback Readiness

If a post-publication launch, migration, persistence, pick-order, or export
regression is discovered, stop using the affected build and return code to the
last known-good `main`. Preserve the current data directory and newest verified
backup before any database recovery. Never delete production data as part of a
code rollback.
