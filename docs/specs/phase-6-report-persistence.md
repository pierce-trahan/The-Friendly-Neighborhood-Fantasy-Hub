# Phase 6 Post-Draft Report Persistence

**Status:** Bounded implementation contract

**Date:** 2026-07-29

**Parent specification:** [Phase 6 Post-Draft Report](phase-6-post-draft-report.md)

**Engine contract:** [Phase 6 Deterministic Report Engine Fixtures](phase-6-report-engine-fixtures.md)

## Outcome

This contract implements Phase 6 step 4: add the four SQLite persistence tables
that will later store one immutable report snapshot.

The schema can store:

- one report header tied to a completed draft revision and input fingerprint;
- the frozen user-roster player rows used by the report;
- one structured row per stable report section; and
- deterministic strategy, board-choice, guidance, and alert moments.

This step does not generate a report, load source-domain data, expose an API,
compare reports, enrich evidence, render HTML, or add a desktop component.

## Ownership

```text
draft_session
`-- post_draft_report
    |-- post_draft_report_player
    |-- post_draft_report_section
    `-- post_draft_report_moment
```

The report is draft-owned:

- deleting the source draft deliberately cascades through all report rows;
- creating or deleting a reset/replacement draft does not alter the source
  report; and
- player and board records are not report-owned and remain intact.

The schema does not add a foreign key from a reset draft to a report. A reset is
a separate draft and receives a separate future report.

## `post_draft_report`

The report header stores:

- UUID-style local id;
- source draft id;
- completed draft revision;
- canonical input fingerprint;
- normalized league-shape fingerprint;
- report engine, rule, and explanation versions;
- live or mock mode;
- generated and completed UTC timestamps;
- safe section-availability summary JSON; and
- report-level limitation codes JSON.

Constraints:

- `draft_revision >= 0`;
- both fingerprints are exactly 64 lowercase hexadecimal characters;
- version fields are non-empty and bounded to 64 characters;
- mode is `live` or `mock`;
- both JSON fields are valid SQLite JSON;
- `(draft_session_id, input_fingerprint)` is unique; and
- the draft foreign key cascades only on deliberate draft deletion.

The fingerprint uniqueness is the persistence half of idempotent generation.
The generation service in step 5 will compute the fingerprint and return the
existing row when it already exists.

## `post_draft_report_player`

Each frozen user-roster row stores:

- report id and canonical player id;
- overall and round pick;
- frozen primary and fantasy positions;
- optional starter-slot assignment;
- saved Personal Board rank, tier order, and favorite flag; and
- normalized safe evidence JSON.

Constraints:

- one player per report;
- one overall pick per report;
- positive overall and round picks;
- optional saved ranks and tiers are positive;
- fantasy-position and safe-evidence fields contain valid JSON;
- report deletion cascades; and
- canonical player deletion is restricted while a report references it.

Personal Board notes, provider ids, source row keys, private references, and raw
evidence have no columns in this table.

## `post_draft_report_section`

Each section row stores:

- stable section key;
- approved availability and confidence;
- structured metrics JSON;
- reason and limitation code arrays;
- explanation template key;
- rendered plain-language explanation; and
- safe provenance JSON.

Constraints:

- one section key per report;
- availability is `supported`, `limited`, `unavailable`, or
  `not_applicable`;
- confidence is `high`, `medium`, `low`, or `unavailable`;
- keys and explanations are non-empty;
- all JSON fields are valid; and
- report deletion cascades.

The schema does not create an overall score, grade, ranking, or winner field.

## `post_draft_report_moment`

Each moment row stores:

- deterministic moment key;
- moment kind;
- optional overall pick;
- optional primary and secondary canonical players;
- safe summary JSON; and
- reason and limitation code arrays.

Approved kinds:

- `personal_board_choice`;
- `strategy_pivot`;
- `strategy_guidance`; and
- `alert_event`.

Constraints:

- one moment key per report;
- optional overall pick is positive;
- primary and secondary players cannot be the same when both exist;
- all JSON fields are valid;
- player deletion is restricted while referenced; and
- report deletion cascades.

No moment kind can claim a trade occurred or add a retrospective alert. The
later generation service remains responsible for projecting only saved,
approved inputs.

## Immutability Triggers

Every report table has:

- an unconditional `BEFORE UPDATE` trigger; and
- a conditional `BEFORE DELETE` trigger.

Direct updates fail with a stable SQLite integrity error.

Direct deletion of a report fails while its source draft exists. Direct
deletion of a child row fails while its report exists. During a deliberate
source-draft cascade, the parent row is already absent at each child boundary,
so the conditional delete triggers permit the owned cascade.

This design protects saved snapshots while preserving the existing local
draft-deletion contract. It avoids soft-delete state that could later be
mistaken for a regenerated report.

## Indexes

The bounded indexes support later service reads without pre-designing API
queries:

- report by draft and completion time;
- report players by position;
- report sections by availability; and
- report moments by kind and overall pick.

Uniqueness indexes also support idempotent report lookup and deterministic
child identity.

## Transaction Boundary

The future generation service must insert:

1. report header;
2. all player rows;
3. all section rows; and
4. all moment rows

inside one explicit SQLite transaction.

The persistence tests prove that a late invalid section rolls back the earlier
header and player inserts. This step does not add the service that orchestrates
that transaction.

## Migration

Alembic revision `20260729_0009`:

- upgrades from `20260728_0008`;
- creates the four tables, constraints, foreign keys, indexes, and eight
  immutability triggers;
- downgrades by removing triggers, indexes, and child-to-parent tables; and
- round-trips back to the Phase 5 schema without leaving report artifacts.

The ORM models and migrated SQLite schema are mechanically compared for column,
index, and check-constraint parity.

## Test Plan

Focused persistence tests cover:

- migration from Phase 5 head to Phase 6 persistence;
- ORM/migration column parity;
- index and check-constraint parity;
- unique-key inspection;
- foreign-key cascade inspection;
- eight trigger installation;
- downgrade to `20260728_0008`;
- re-upgrade to head;
- atomic ORM row round-trip;
- immutable report, player, section, and moment rows;
- direct report and child deletion rejection;
- reset/replacement draft preservation;
- deliberate source-draft cascade;
- player and board preservation after cascade;
- duplicate report fingerprint;
- duplicate report player and overall pick;
- invalid lowercase fingerprint;
- invalid availability, confidence, moment kind, and JSON;
- duplicate section and moment identity; and
- rollback of every partially inserted row after a late failure.

The pure engine and approved contract fixtures remain part of the focused gate.
The full repository suite must also pass.

## Acceptance Criteria

1. Exactly four report-owned tables are added.
2. ORM and Alembic definitions remain structurally aligned.
3. One input fingerprint identifies at most one report per draft.
4. Player, pick, section, and moment identities are unique within a report.
5. Availability, confidence, mode, and moment-kind enums fail closed.
6. Fingerprints are lowercase SHA-256 values.
7. Structured fields reject malformed JSON.
8. Direct report mutation and deletion are blocked.
9. Reset/replacement drafts do not alter old reports.
10. Deliberate source-draft deletion cascades through every report row.
11. Player and board rows survive that cascade.
12. A late failure leaves no partial report.
13. Upgrade, downgrade, and re-upgrade pass offline.
14. No generation service, API, evidence enrichment, export, or frontend work
    is introduced.

## Next Implementation Boundary

After this module is reviewed, Phase 6 step 5 may add completed-draft
eligibility, consistent input loading, atomic report generation, fingerprint
idempotency, and generate/read/list API contracts.

That bounded implementation is recorded in
[Phase 6 Completed-Draft Report Generation API](phase-6-report-generation-api.md).

Optional Phase 5 enrichment, strategy and decision moments, comparison, HTML
export, and desktop work remain deferred to their later approved steps.
