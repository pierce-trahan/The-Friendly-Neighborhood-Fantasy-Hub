# Phase 6 Live Workflow and Specification Audit

**Status:** Passed

**Audit date:** 2026-08-03

**Scope:** Phase 6 Post-Draft Report

## Verdict

Phase 6 is complete. The immutable report ledger, deterministic construction
observations, optional evidence boundaries, saved decision history, compatible
comparison, standalone HTML export, and desktop Reports workspace satisfy the
approved V1 contract. No critical, high, or medium specification gap remains.

The audit used only fictional local data. It did not contact a provider,
download a real market dataset, expose a private league, or claim predictive
accuracy. Missing long-term, liquidity, contract, injury, and calibrated
outcome evidence remains visible instead of being guessed.

## Full Offline Workflow Evidence

The durable audit command is:

```powershell
.\.venv\Scripts\python.exe scripts\audit_phase6_workflow.py
```

It creates an isolated temporary database and 280-player fictional pool, then:

- completes two 10-team, 24-round, third-round-reversal mocks with different
  seeds, initial strategies, and saved strategy pivots;
- attaches one exact-compatible synthetic alert snapshot and records a saved
  alert event;
- completes a matching 10-team, 24-round live draft;
- processes 720 total picks fully offline;
- snapshots board, draft, pick, mock, and alert source responses before report
  generation and proves they are byte-equivalent afterward;
- blocks `socket.connect` during generation, restart reads, idempotent
  generation, comparison, and HTML export;
- generates three reports and restores all three identically after an
  application restart;
- repeats generation and receives the identical saved report idempotently;
- verifies the live strategy section is `not_applicable`;
- verifies missing long-term, liquidity, and player-fragility evidence remains
  `unavailable`;
- compares the two compatible mock reports without an overall judgment field;
- exports one standalone HTML document and scans it for scripts, remote URLs,
  external assets, and private markers;
- scans normal responses and application logs for private notes, provider/raw
  fields, private source references, random audit, and manager references; and
- confirms the pre-existing draft CSV contains no Phase 6 fields.

The final isolated run passed in 15.4 seconds. Report-operation timing was:

| Operation | Measured seconds | Contract target |
| --- | ---: | ---: |
| Mock report 1 generation | 0.0367 | under 1.0 |
| Mock report 2 generation | 0.0192 | under 1.0 |
| Live report generation | 0.0164 | under 1.0 |
| Slowest restart read | 0.0618 | under 0.1 |
| Idempotent generation | 0.0259 | under 1.0 |
| Two-report comparison | 0.0040 | under 0.5 |
| Standalone HTML export | 0.0040 | under 1.0 |

The HTML artifact was 26,649 bytes, below the 2 MiB guard.

## Desktop Evidence

The Phase 6 workspace was inspected from a temporary local database at the
default 1280-pixel viewport and a 760-pixel responsive viewport. The audit
verified:

- the application and navigation identify Phase 6 and expose `Reports`;
- opening Reports performs only board, draft-summary, and saved-history reads;
- no horizontal overflow at either viewport;
- two desktop history panels become one responsive column;
- the no-board state omits an empty selector;
- keyboard-native navigation, selection, details, and export controls are
  present; and
- the browser console contains no warning or error.

Component interaction tests additionally cover explicit generation
confirmation, the frozen revision payload, report section status text,
unsupported evidence visibility, compatibility filtering, `not_comparable`,
and the local export link.

## Acceptance Traceability

| ID | Result | Primary evidence |
| --- | --- | --- |
| 1 | Pass | `test_completed_live_report_is_atomic_idempotent_private_and_restart_safe`; `test_paused_and_missing_league_shape_reject_without_report_rows` |
| 2 | Pass | Completed-live generation test; full offline audit live report |
| 3 | Pass | Completed-mock history tests; full offline audit mock reports |
| 4 | Pass | Exact stale-revision integration assertion and source snapshot |
| 5 | Pass | Idempotent generation integration and restart audit |
| 6 | Pass | `test_reset_preserves_report_and_source_draft_delete_cascades` |
| 7 | Pass | Generation/evidence integration source scans; full audit byte-equivalent source snapshot |
| 8 | Pass | `test_late_section_failure_rolls_back_every_new_report_row`; persistence rollback test |
| 9 | Pass | Restart-safe generation test; three restart-identical audit reads |
| 10 | Pass | `test_live_report_reconstructs_and_deduplicates_frozen_board_choice` |
| 11 | Pass | Completed-live report roster assertions |
| 12 | Pass | Starter expected fixture and maximal-coverage engine tests |
| 13 | Pass | Stable tie-break fixture and engine test |
| 14 | Pass | Starter fixture depth assertions |
| 15 | Pass | Concentration expected-boundary engine test |
| 16 | Pass | Contract unsafe-variant and explanation-language tests |
| 17 | Pass | `test_missing_shape_and_incomplete_eligibility_fail_visibly` |
| 18 | Pass | Evidence boundary tests below 50 percent |
| 19 | Pass | Evidence boundary tests from 50 through 79 percent |
| 20 | Pass | Evidence boundary tests at 80 percent and medium confidence cap |
| 21 | Pass | Age-risk coverage boundary fixtures |
| 22 | Pass | Completion-time freshness integration and restart-identical reads |
| 23 | Pass | Elapsed/incompatible evidence integration tests |
| 24 | Pass | Missing-evidence section test and full offline audit |
| 25 | Pass | Missing-evidence section test and full offline audit |
| 26 | Pass | Market/evidence contract keeps market bands separate from liquidity |
| 27 | Pass | Missing-evidence section test and full offline audit |
| 28 | Pass | Unsupported-section contract and forbidden-variant tests |
| 29 | Pass | Saved mock strategy revisions/guidance integration tests |
| 30 | Pass | Strategy fixtures and pivot explanation tests |
| 31 | Pass | Completed-live report strategy assertion; full offline audit |
| 32 | Pass | Personal Board exact qualification boundary tests |
| 33 | Pass | Repeated-pass deduplication test |
| 34 | Pass | Frozen-board note privacy tests |
| 35 | Pass | Saved alert projection integration tests |
| 36 | Pass | Disabled/missing/corrupt alert-history distinctions |
| 37 | Pass | Pick-only safe alert projection test |
| 38 | Pass | Alert safe-summary assertions and forbidden-language scan |
| 39 | Pass | Compatible comparison unit/API tests and full offline audit |
| 40 | Pass | Comparison request validation and two-to-four API coverage |
| 41 | Pass | Incompatible comparison rejection and `not_comparable` coverage |
| 42 | Pass | Comparison safe-field tests; no overall judgment field in audit response |
| 43 | Pass | Standalone export integration and network-blocked audit export |
| 44 | Pass | Hostile draft/player escaping integration test; non-included team identity remains absent |
| 45 | Pass | Generation, evidence, comparison, export, log, and full-audit privacy scans |
| 46 | Pass | Phase 3/4/5 CSV regression tests and explicit full-audit Phase 6 token scan |
| 47 | Pass | Explanation fixture, section registry, and generated-report integration tests |
| 48 | Pass | Missing-evidence contract and report detail tests |
| 49 | Pass | Contract unsafe-language variants, comparison projection, and export scans |
| 50 | Pass | `scripts/audit_phase6_workflow.py`, 720 picks with every operation inside target |

## Repository Verification

The checked-in release gate covers Ruff, backend and migration tests, OpenAPI
generation, frontend API generation, TypeScript type checking, frontend tests,
the production build, and the high-severity npm dependency audit.

The final Phase 6 gate completed with:

- Ruff: passed;
- backend: 144 tests passed;
- OpenAPI and frontend API generation: passed with tracked outputs current;
- TypeScript type-check: passed;
- frontend: 39 tests across 10 files passed;
- production build: passed; and
- npm high-severity dependency audit: 0 vulnerabilities.

The sandboxed verifier cannot reach npm's advisory endpoint, so the same
read-only audit was repeated with registry access and passed.

## Findings and Approved Boundaries

No blocking product defect was found. The audit corrected three audit-fixture
issues (a nested board-entry display field, the alert metric key, and the log
filename glob) without changing application behavior. Desktop visual QA also
removed an empty selector from the no-board state.

One documentation gap was critical to release clarity: the roadmap still used
the historical word `score` and listed unsupported evidence families as if V1
could calculate them. The Phase 6 roadmap is updated with the approved
observation/availability model and explicit unavailable states.

These limitations remain approved and non-blocking:

1. No approved real production, age, contract, injury, or liquidity dataset is
   bundled.
2. No calibrated roster-strength, outcome, recommendation, or overall grading
   model exists in V1.
3. PDF packaging, cloud sharing, visual-regression automation, and GitHub
   Actions remain deferred.
4. Synthetic fixtures prove deterministic behavior and privacy boundaries,
   not real-world predictive accuracy.

## Release Checklist

- [x] All four Phase 6 product-gate decisions are recorded as approved.
- [x] Completed live and mock reports are immutable and restart-safe.
- [x] Identical generation is idempotent.
- [x] Core construction observations work without optional evidence.
- [x] Optional evidence enriches only supported sections.
- [x] Unsupported evidence families remain visibly unavailable.
- [x] Strategy, Personal Board, and saved alert moments are bounded and private.
- [x] Compatible comparison has no overall judgment field.
- [x] Standalone HTML export is offline, escaped, bounded, and read-only.
- [x] Reports workspace interaction, responsive layout, and console checks pass.
- [x] Full 720-pick offline workflow and repository verification pass.

### Rollback triggers

Do not release Phase 6 if report generation mutates a source domain, restart
changes an immutable report, incompatible reports receive deltas, unavailable
evidence is guessed, private/source fields leak, export requests a network
resource, generation/read/comparison/export exceeds its guard, or any release
gate fails.

Rollback is a revert of the Phase 6 merge commits, not a destructive database
downgrade. The forward migration and immutable report rows remain protected by
the repository verifier.

## Phase Gate

Phase 6 may be treated as complete. The next roadmap work is Phase 7
Draft-Night Hardening: stabilize and rehearse the V1 workflow rather than add a
new product module.
