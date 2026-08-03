# Phase 6 Desktop Reports Workspace

**Status:** Bounded implementation contract

**Date:** 2026-08-03

**Parent specification:** [Phase 6 Post-Draft Report](phase-6-post-draft-report.md)

**Predecessor:** [Phase 6 Standalone Safe HTML Report Export](phase-6-report-html-export.md)

## Outcome

This contract implements Phase 6 step 10. The desktop application adds one
`Reports` workspace for explicitly generating an immutable report from a
completed draft, browsing board-wide report history, reading every report
section and limitation, previewing compatible comparisons, and downloading the
approved standalone HTML export.

The workspace is a film review room, not an awards show: it puts the saved tape
and construction notes in order without inventing a grade, ranking, projection,
or composite judgment.

## Read Model

The previously specified board endpoint is implemented here:

`GET /api/v1/boards/{board_id}/post-draft-reports`

It returns newest-first immutable summaries with bounded pagination and
optional `mode`, `completed_from`, `completed_to`, `strategy_key`,
`report_version`, and `league_shape_fingerprint` filters. Each summary includes
only the frozen identity needed by the workspace: draft format, team and round
counts, and nullable initial/final mock strategy identity.

The endpoint verifies that the Personal Board exists, reads saved report and
safe section rows only, exposes no player name or private-note search, and
creates or updates no row.

## Navigation and Loading

- `Reports` is a primary navigation destination.
- Opening it loads Personal Boards, completed draft summaries, and immutable
  board report history.
- Opening it never calls report generation.
- Changing boards clears report detail and comparison selection before loading
  the next saved history.
- Draft Room and Mock Lab code and actions remain unchanged.

## Explicit Generation

Completed draft summaries show either `Prepare report` or `Open saved report`.
`Prepare report` first refreshes the authoritative draft detail. A modal
confirmation names the draft, frozen revision, completion time, and records
that source state will not be modified.

Only `Generate saved report` calls the generation endpoint. An idempotent
response opens the existing report and explains that no duplicate was created.
A stale conflict refreshes the authoritative completed draft before another
confirmation. Closing the dialog restores focus to its trigger.

## Detail, Comparison, and Export

Report detail includes identity/version limits, roster inventory, every
registered section, decision moments, and evidence limits. Availability and
confidence are always written as text. Structured values and limitations live
inside keyboard-reachable native details controls and semantic tables.

Comparison selection:

- accepts two through four reports;
- disables reports with a different league-shape fingerprint or rules version
  after the first choice;
- shows mode, format, completion date, team/round shape, and mock strategy
  before preview;
- renders each server-approved section state, safe values, and exact deltas;
- labels `not_comparable` rather than filling missing metrics with zero; and
- introduces no overall judgment or persistence.

`Export HTML` is a direct local attachment action. The workspace describes it
as a standalone local file and uses no upload, publish, or share language.

## Accessibility and Recovery

- semantic heading hierarchy and table captions/scoped headers;
- text labels accompany every status;
- all controls are native keyboard targets;
- confirmation uses dialog semantics and restores focus;
- notices use alert or polite status roles;
- responsive single-column fallbacks preserve source order; and
- reduced-motion preferences disable workspace transitions.

API errors retain their safe message and recovery action. Generation, read,
comparison, and export failures never remove the saved source or report.

## Acceptance Criteria

1. Primary navigation exposes `Reports` and identifies the app as Phase 6.
2. Opening Reports performs no generation request.
3. Completed drafts and saved board report history are visible.
4. Board history supports every approved bounded filter and newest-first paging.
5. Generation requires a refreshed completed draft and explicit confirmation.
6. Confirmation identifies the draft, frozen revision, and completion time.
7. Idempotent generation opens the existing report without a duplicate claim.
8. Stale generation refreshes authoritative state and preserves recovery text.
9. Detail shows roster, all registered sections, availability, confidence,
   explanations, limitations, bounded moments, and evidence limits.
10. Unsupported long-term, liquidity, and fragility sections remain visible.
11. Two through four compatible reports can be previewed section by section.
12. Incompatible choices are disabled and mixed-support sections say
    `not_comparable`.
13. No overall score, rank, recommendation, projection, or composite judgment
    appears.
14. Export is one local standalone HTML attachment action.
15. Dialog, table, status, keyboard, responsive, and reduced-motion contracts
    are represented and tested.
16. The full repository verification gate passes.

## Next Implementation Boundary

After this module is reviewed, Phase 6 step 11 may perform only the final
specification trace, critical-gap fixes, and end-to-end offline live workflow
audit. It must not add a new product module or broaden V1 scope.
