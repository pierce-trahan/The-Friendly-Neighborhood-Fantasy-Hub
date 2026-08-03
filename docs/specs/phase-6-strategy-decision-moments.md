# Phase 6 Saved Strategy and Decision Moments

**Status:** Bounded implementation contract

**Date:** 2026-08-03

**Parent specification:** [Phase 6 Post-Draft Report](phase-6-post-draft-report.md)

**Generation contract:** [Phase 6 Completed-Draft Report Generation API](phase-6-report-generation-api.md)

**Evidence predecessor:** [Phase 6 Attached-Evidence Report Enrichment](phase-6-evidence-enrichment.md)

## Outcome

This contract implements Phase 6 step 7. A completed report may now replay
three forms of saved decision history:

- Phase 4 strategy revisions and guidance for mocks;
- bounded Personal Board choice moments reconstructed from the frozen draft
  candidate snapshot and completed pick order; and
- saved Phase 5 alert events and pick-only trade-up references.

The module works like a postgame film log. It can show the formation, the saved
coaching note, and the decision that occurred. It cannot claim that one caused
the other, award a grade, or rewrite the play after the fact.

This step does not add report comparison, HTML export, Reports UI, outcome
projections, player recommendations, trade execution claims, or a composite
strategy score.

## Architecture and Data Flow

Generation remains one local SQLite transaction:

```text
completed draft and frozen candidates
              |
              +-- saved mock revisions and guidance -- strategy story
              |
              +-- ordered completed picks ------------ board reconstruction
              |
              +-- saved alert configuration/events --- alert history
                                                        |
                                                        v
                                      safe versioned history document
                                                        |
                                      fingerprint, sections, moment rows
```

The source rows are read-only. Report header, player, section, and moment rows
still commit atomically or not at all. No migration is required because the
Phase 6 moment table and its four approved moment kinds already exist.

## Mock Strategy Story

Live drafts keep `strategy_story` as `not_applicable`.

For mocks, generation reads only the attached `mock_configuration`, ordered
`mock_strategy_revision` rows, and saved `mock_guidance_event` rows. CPU seed,
random audit, alternatives, manager references, learning consent, and private
pivot notes are prohibited inputs.

A valid story records:

- the initial saved strategy;
- ordered pivots with previous strategy, next strategy, and effective pick;
- counts for `on_plan`, `watch`, `off_plan_viable`, `risk_checkpoint`, and
  `insufficient_evidence` guidance;
- final frozen roster position counts;
- each saved guidance event's observed counts and target ranges;
- open, acknowledged, and dismissed interaction counts; and
- inherited reason and limitation codes.

No adherence percentage is calculated. A pivot is an observed change in plan,
not a failure.

Strategy history states are:

- `valid`: supported with high confidence;
- `incomplete`: limited with low confidence when a required saved row is
  missing but the remaining history is safely readable; and
- `corrupt`: unavailable when ordering, references, JSON, or safe field types
  cannot be trusted.

At most `60` strategy revisions and `60` guidance events are accepted, matching
the maximum supported user roster. Larger histories fail closed as corrupt.

Each saved pivot and guidance event receives a deterministic report moment.
Guidance summaries contain only categorical state, confidence, saved counts,
target ranges, interaction status, template keys, and safe codes.

## Personal Board Choice Moments

The engine reconstructs candidate availability before each user pick by
removing players selected at earlier overall picks. It uses only the frozen
candidate fields already saved with the draft:

- canonical player id and display identity;
- primary position;
- manual rank;
- tier order; and
- favorite flag.

Current Personal Board rows and all Personal Board notes are prohibited.

At each user pick, the engine compares the selected player's saved manual rank
with the highest-ranked still-available frozen candidate. A moment qualifies
only when the selected player ranked lower and at least one condition holds:

- rank delta is at least `5`;
- the passed player was a saved favorite; or
- both players had saved tiers and the passed player's tier order was better.

Missing ranks do not create guessed comparisons. A tier claim requires both
tier orders; an un-tiered player is not silently treated as belonging to a
worse tier.

Repeated passing on the same highest-ranked player collapses to the earliest
qualifying observation. The summary separately records the last later user
pick at which that player remained available.

At most `10` moments are retained using the approved priority:

1. favorite passed;
2. tier difference descending;
3. rank delta descending; and
4. user pick ascending.

Each safe summary includes selected and passed display identity, positions,
saved ranks and tiers, favorite status, rank delta, the first and last observed
user picks, and whether the passed player was later drafted by the user,
another slot, or not drafted. The required limitation is
`PERSONAL_BOARD_OBSERVATION_ONLY`; the prose never calls the choice a mistake,
reach, steal, win, or loss.

A valid frozen board reconstruction is supported with high confidence even
when zero moments qualify.

## Recorded Alert Moments

Generation never evaluates the Phase 5 alert engine. It reads only the draft's
saved alert configuration, its saved `draft_alert_event` rows through the
completed draft revision, and the newest saved pick-only trade reference for
each event.

The section's historical states are:

- `not_configured`;
- `disabled_at_completion`;
- `configured_no_events`;
- `available`; or
- `unavailable_due_to_corruption`.

The first four are supported historical observations. Disabled configurations
may still show events saved before disablement. Corrupt rows make the section
unavailable and produce no alert moment projection.

At most `20` events are retained, ordered by first confirmed draft revision,
event kind, and canonical event id. The section still records the full safe
event count and whether the detail list was truncated.

Alert summaries may contain:

- saved event kind, status, confidence, and freshness;
- first and last confirmed draft revision;
- snooze, dismissal, or superseded lifecycle fields;
- whitelisted evidence ranges and categorical component bands;
- the saved target pick window;
- ranged pick-only cost and future-round references;
- whether the player was later drafted by the user, another slot, or not
  drafted; and
- safe reason, explanation-template, and limitation codes.

They exclude raw evidence JSON, provider ids, source namespaces, snapshot ids,
private source references, asset keys, ownership claims, and any player-plus-
pick package. A saved trade-up window is not evidence that a trade occurred.

## Determinism and Fingerprinting

The canonical report input receives
`phase6-saved-decision-history-v1` documents for strategy, Personal Board
reconstruction, and alerts. The documents include safe saved inputs, aggregate
states, deterministic moment keys, and a content fingerprint for any complete
safe history that exceeds the displayed detail limit.

Changing saved strategy or alert history creates a new report fingerprint.
Identical source history returns the existing report idempotently. Current
board edits, generation time, private notes, and unsaved retrospective
calculations never affect the fingerprint.

## Privacy and Language Boundary

Normal report reads expose only the approved `safe_summary`, reason codes, and
limitation codes stored in immutable moment rows.

The module prohibits:

- Personal Board notes;
- private strategy pivot notes;
- CPU seed, randomness, alternatives, and scoring audit;
- private alert or evidence references;
- raw upload or raw event JSON;
- claims that an alert caused a pick;
- claims that a trade occurred;
- grading, winners, objective value, or outcome predictions; and
- newly generated retrospective alerts.

## Verification Strategy

Unit coverage proves:

- board availability reconstruction before every user pick;
- exact rank-delta, favorite, and better-tier qualification;
- missing-rank and missing-tier fail-closed behavior;
- repeated-pass deduplication and top-10 priority;
- later-drafted user, other-slot, and not-drafted labels;
- strategy ordering, safe JSON parsing, and incomplete/corrupt states;
- saved guidance state and interaction counts;
- alert historical-state distinctions;
- alert ordering, top-20 truncation, and safe evidence whitelisting;
- trade references contain only ranges and generated labels; and
- deterministic moment keys and forbidden-language scans.

Completed-draft integration coverage proves:

- live strategy remains not applicable;
- a completed mock replays saved pivots and guidance only;
- zero Personal Board moments is supported;
- qualifying Personal Board moments contain no notes;
- not-configured, disabled, no-event, available, and corrupt alert states;
- report header, sections, players, and moments remain atomic;
- source mock, board, draft, alert, and evidence rows remain unchanged;
- identical generation remains idempotent and restart-safe; and
- normal responses exclude all prohibited fields.

The full backend, frontend, contract-generation, production-build, dependency,
privacy, and whitespace gates remain required before publication.

## Acceptance Criteria

1. Mock strategy story uses only saved revisions and guidance events.
2. Pivots are observations and never counted as failure.
3. Live strategy remains `not_applicable`.
4. Board moments reconstruct availability from the frozen snapshot and picks.
5. The exact rank, favorite, tier, deduplication, and top-10 rules are stable.
6. Personal Board notes never enter fingerprint, persistence, response, or log.
7. Only saved Phase 5 events create alert moments.
8. Alert configuration states remain distinguishable and honest.
9. Alert detail is capped at 20 without losing the full event count.
10. Pick-only trade references contain ranges and no ownership or execution
    claim.
11. Private, raw, provider, random, and internal fields never enter safe output.
12. Moment keys and report fingerprints are deterministic.
13. Generation mutates no source-domain row.
14. New report rows remain atomic and idempotent.
15. Comparison, export, and frontend work remain deferred.
16. The full repository verification gate passes.

## Next Implementation Boundary

Phase 6 step 8 implements this boundary in the
[compatible report comparison contract](phase-6-report-comparison.md). The next
boundary is standalone safe HTML export without scripts, external assets,
remote requests, comparison persistence, or desktop work.
