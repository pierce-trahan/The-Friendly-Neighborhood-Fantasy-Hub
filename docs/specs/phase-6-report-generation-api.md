# Phase 6 Completed-Draft Report Generation API

**Status:** Bounded implementation contract

**Date:** 2026-08-02

**Parent specification:** [Phase 6 Post-Draft Report](phase-6-post-draft-report.md)

**Persistence contract:** [Phase 6 Post-Draft Report Persistence](phase-6-report-persistence.md)

**Step 6 successor:** [Phase 6 Attached-Evidence Report Enrichment](phase-6-evidence-enrichment.md)

## Outcome

This contract implements Phase 6 step 5: completed-draft eligibility,
consistent saved-input loading, deterministic input fingerprinting, atomic
core-report persistence, idempotent generation, and read/list transport.

The module is the report equivalent of locking picture before a postgame film
review. It verifies that the saved draft is actually complete, freezes the
inputs used by the core report, writes the whole artifact in one transaction,
and returns the same artifact when the identical cut is requested again.

This step does not add:

- Phase 5 categorical evidence enrichment;
- mock strategy history or guidance detail;
- Personal Board or recorded-alert moment rows;
- cross-report comparison;
- HTML export; or
- desktop Reports components.

Those boundaries remain assigned to Phase 6 steps 6 through 10.

## Eligibility Gate

A generation request succeeds only when:

- the draft exists and has `completed` status;
- the requested revision and completion timestamp exactly match the saved
  completed draft;
- the draft has exactly `team_count * round_count` pick rows;
- every pick contains one unique canonical player;
- each active pick has matching saved revision history;
- every drafted player exists in the frozen candidate snapshot;
- the frozen candidate snapshot contains between 1 and 500 players;
- the draft-team snapshot is complete and has exactly one user slot;
- the user roster contains between 1 and 60 picks;
- a live draft has a valid saved league profile;
- a mock has a valid saved `mock_configuration`; and
- the saved starter shape normalizes to the six V1 slot types.

Active, paused, incomplete, corrupt, or missing-shape drafts fail without a
report write and without changing any source row.

## Normalized League Shape

The compatibility fingerprint contains only normalized report meaning:

- team and round counts;
- linear or snake format and third-round-reversal state;
- league type;
- ordered starter slots with stable occurrence keys;
- bench, taxi, and injured-reserve counts;
- TE-premium presence; and
- visible normalization limitations.

Supported starter slot types remain `QB`, `RB`, `WR`, `TE`, `FLEX`, and
`SUPER_FLEX`. `SF` and `SUPERFLEX` normalize to `SUPER_FLEX`; unknown or
misconfigured eligibility fails closed rather than guessing.

Mocks use the league shape already frozen in `mock_configuration`. Live drafts
use their saved local league profile at generation time, then freeze the
normalized result inside the immutable report fingerprint and summary.

## Canonical Input and Idempotency

The internal canonical input document includes:

- draft id, name, board id, mode, configuration, revision, and completion time;
- ordered saved teams;
- ordered active picks;
- every frozen candidate field used by the report;
- normalized league shape;
- the safe mock-configuration fingerprint and strategy-definition version,
  when applicable;
- explicit `null` placeholders for Phase 5 evidence and step 7 moment inputs;
  and
- report engine, rules, and explanation-template versions.

It excludes Personal Board notes, provider ids, private source references,
CPU seed/random audit, private strategy notes, report id, and generation time.
SHA-256 over UTF-8 canonical JSON becomes `input_fingerprint`.

The `(draft_session_id, input_fingerprint)` uniqueness boundary provides
idempotency:

- a new fingerprint produces `201` and a new report;
- an existing identical fingerprint produces `200`, `idempotent: true`, and
  the original report; and
- a uniqueness race rolls back the losing transaction and returns the already
  committed report when one exists.

Later enrichment and decision-moment steps replace their explicit `null`
input blocks with safe saved inputs. That changes the fingerprint while
preserving any already generated core-only report as an immutable historical
artifact.

## Core Report Projection

Generation writes all fourteen registered section keys in stable order.

Supported core sections:

- draft summary;
- position inventory and Phase 4 early/middle/late windows;
- deterministic maximum starter coverage;
- depth after starter assignment;
- roster-construction concentration; and
- evidence limits.

Always-unavailable V1 claims remain visible:

- long-term dynasty outcome value;
- liquidity; and
- player injury, contract, or role fragility.

Step-bounded states remain explicit:

- production, market, and age-risk enrichment identify the Phase 6 step 6
  deferral;
- mock strategy history identifies the Phase 6 step 7 deferral;
- Personal Board and recorded-alert moments identify the Phase 6 step 7
  deferral; and
- live strategy story is `not_applicable`.

These states prevent an intermediate backend from labeling missing logic as a
zero-event observation or inventing an evidence result. Step 6 and step 7 must
replace the deferrals from saved approved inputs before desktop exposure.

## Atomic Persistence

One transaction writes, in order:

1. `post_draft_report`;
2. the frozen user-roster player rows;
3. all fourteen section rows; and
4. any future deterministic moment rows.

The step 5 generator creates no moment rows. A constraint failure during the
last section flush rolls back the header, players, and every section. Retry is
safe. Drafts, picks, revisions, candidates, teams, boards, league profiles,
mocks, alerts, and evidence are read-only inputs.

Frozen player display names are projected through safe report JSON rather than
re-read from the mutable player universe. The frozen draft name is read from
the persisted `draft_summary` metrics. Normal API reads therefore do not
recalculate display identity from current board or player state.

## API Contract

### Generate

`POST /api/v1/draft-sessions/{session_id}/post-draft-reports`

Request:

```json
{
  "draft_revision": 240,
  "expected_completed_at": "2026-08-02T19:00:00Z"
}
```

The request requires the existing local mutation guard.

Response status:

- `201` for a newly committed report; or
- `200` for an idempotent existing report.

### Read one

`GET /api/v1/post-draft-reports/{report_id}`

Returns the safe report summary, all section states, frozen roster rows,
bounded moment list, compatibility fields, limitations, and capability flags.
Comparison and export flags remain unavailable until their later steps.

### List for a draft

`GET /api/v1/draft-sessions/{session_id}/post-draft-reports`

Supports `limit` from 1 through 100 and non-negative `offset`. Results are
newest first and use frozen report identity.

The board-wide filtered list remains deferred until the strategy filter can
be backed by the approved step 7 strategy story instead of inferred data.

## Response Privacy

Normal responses exclude:

- internal input fingerprint;
- raw database JSON strings;
- Personal Board notes;
- provider ids and provider row keys;
- private source references;
- raw evidence;
- private strategy notes;
- CPU seed, randomness, and random audit;
- manager internal references; and
- source-domain mutation controls.

Logs contain report id, draft id, and version identifiers, never roster names
or contents.

## Errors and Recovery

The bounded implementation returns the approved codes:

- `REPORT_DRAFT_NOT_COMPLETE`;
- `REPORT_DRAFT_STALE_REVISION`;
- `REPORT_DRAFT_INCOMPLETE`;
- `REPORT_LEAGUE_SHAPE_UNAVAILABLE`;
- `REPORT_NOT_FOUND`; and
- `REPORT_GENERATION_FAILED`.

Each generation error states that the source draft and existing reports remain
unchanged and gives a local recovery action.

## Verification

Focused automated coverage proves:

- active and paused rejection;
- exact revision and completion-time guards;
- missing league-shape rejection;
- completed live generation;
- completed Phase 4 mock generation;
- all fourteen stable section rows;
- deterministic starter assignment and concentration reuse;
- source-row equality before and after generation;
- response privacy;
- identical replay status and identity;
- restart read equality;
- bounded draft-list reads; and
- rollback of header, players, sections, and moments after a forced late
  section constraint failure.

The existing report contract, engine, persistence, migration, backend,
frontend, build, and dependency gates remain required before publication.

## Acceptance Criteria

1. Active, paused, incomplete, or stale drafts cannot generate a report.
2. Completed live and valid mock drafts generate fully offline.
3. League and candidate inputs fail closed when they cannot be normalized.
4. Identical inputs return the original report idempotently.
5. Every new report writes atomically or not at all.
6. Generation changes no source-domain row.
7. Core starter, depth, inventory, and concentration outputs reuse the approved
   deterministic engine.
8. All fourteen section slots remain visible with honest availability states.
9. Unsupported and not-yet-enriched claims never receive invented values.
10. Reads survive restart without recalculation.
11. Normal responses exclude private and internal fields.
12. The full repository verification gate passes offline except for the
    dependency audit's normal registry access.

## Next Implementation Boundary

Phase 6 step 6 now implements this boundary in the
[attached-evidence enrichment contract](phase-6-evidence-enrichment.md).
The next boundary is step 7: saved mock-strategy story and bounded Personal
Board or recorded-alert moments, without comparison, export, or desktop work.
