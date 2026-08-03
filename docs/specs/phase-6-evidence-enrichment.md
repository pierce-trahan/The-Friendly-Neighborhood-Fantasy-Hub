# Phase 6 Attached-Evidence Report Enrichment

**Status:** Bounded implementation contract

**Date:** 2026-08-02

**Parent specification:** [Phase 6 Post-Draft Report](phase-6-post-draft-report.md)

**Generation contract:** [Phase 6 Completed-Draft Report Generation API](phase-6-report-generation-api.md)

## Outcome

This contract implements Phase 6 step 6. A completed-draft report may enrich
exactly three sections from the Phase 5 evidence snapshot already attached to
that draft:

- `year_one_production_context`;
- `dynasty_market_context`; and
- `age_risk_profile`.

The enrichment is a replay of saved categorical context, not a new model run.
It is like adding the verified stat packet to a completed game recap: the
packet may add context, but it cannot rewrite what happened or pretend to
contain conclusions it never measured.

This step does not add strategy reconstruction, decision moments, report
comparison, HTML export, desktop UI, projections, long-term value, liquidity,
or player fragility.

## Saved Input Boundary

Generation reads only the draft's current `draft_alert_configuration`, its
attached committed or superseded `alert_evidence_snapshot`, and matched
`alert_player_signal` rows for players on the user's frozen roster.

The report does not search for a newer snapshot, silently substitute evidence,
or mutate Phase 5 rows. The alert configuration's enabled flag is preserved in
the fingerprint, but disabling live alert delivery does not erase the
categorical evidence that was attached during the draft.

Missing snapshots, malformed saved JSON, future-dated configuration changes,
invalidated evidence, unknown compatibility, and incompatible formats fail
closed. The three section slots remain visible as unavailable.

## Completion-Time Freshness

Freshness is evaluated against the saved `draft.completed_at`, never report
generation time. This makes replay and restart deterministic.

| Field | Fresh | Aging | Stale | Expired |
| --- | ---: | ---: | ---: | ---: |
| market band and expected-pick window | through 7 days | through 21 days | through 45 days | after 45 days |
| year-one production band | through 14 days | through 30 days | through 60 days | after 60 days |

Age-risk evidence follows the approved Phase 5 validity policy: a present,
non-future categorical value is fresh, a recorded source conflict is stale,
and a missing or invalid timestamp is unusable. This is not an age calculation
and does not infer age from a name, season, or provider record.

Fresh, aging, and stale values may count toward coverage. Stale evidence caps
confidence at low. Expired, invalid, missing, incompatible, and unknown values
do not count.

## Format Compatibility

Compatibility is recalculated from the saved draft and snapshot during report
generation:

- `exact` may support medium confidence;
- `family` may support medium confidence and carries a visible family-format
  limitation;
- `partial` caps confidence at low and carries its modifier differences; and
- `incompatible` or `unknown` makes all three enriched sections unavailable.

The report exposes only safe compatibility labels and reason codes. It does not
expose snapshot ids, provider keys, namespaces, or private source references.

## Coverage and Confidence

Coverage is calculated independently for each categorical field over the
user's frozen roster:

- at least 80% usable coverage is `supported`;
- at least 50% but below 80% is `limited`; and
- below 50% is `unavailable`.

Basis points use the existing deterministic integer calculation. Confidence is
never higher than medium because Phase 5 evidence is categorical and may come
from one source. Limited coverage, partial compatibility, or stale evidence
caps confidence at low. Unavailable sections use unavailable confidence.

Each section records roster count, covered and uncovered counts, basis-point
coverage, band distribution, freshness counts, reason codes, limitation codes,
and safe provenance.

## Expected-Selection Context

When both the market band and expected-pick window are usable, the market
section compares the saved window with the player's actual overall selection:

- `before_expected_window`;
- `within_expected_window`; or
- `after_expected_window`.

This is observational context only. It is not a reach/steal grade, objective
value claim, trade recommendation, or prediction that the player would have
returned.

## Fingerprint, Persistence, and Privacy

The canonical report input replaces the step 5 null alert placeholder with a
versioned safe evidence document containing configuration versions, snapshot
content hash and status, compatibility, and only the matched roster signals
used by the report. A draft with no attached evidence receives an explicit
versioned `attached: false` document.

This changes the fingerprint boundary from the earlier core-only generator
while keeping already generated reports immutable. Repeating identical saved
inputs returns the same report idempotently.

Each frozen report-player row stores only display identity and sanitized
categorical values, timestamps, freshness labels, expected-pick endpoints, and
limitation codes. Normal report responses continue to omit this internal
player-evidence document. Safe section provenance exposes source label,
source-as-of time, compatibility, completion-time freshness, and freshness
policy version.

The following never enter normal report responses or safe persisted evidence:

- private snapshot references;
- private source-record references;
- source player keys;
- raw imported rows;
- provider ids or namespaces; and
- pick-value evidence not used by these three sections.

This module needs no migration and writes no Phase 5 row.

## Verification

Automated coverage proves:

- exact compatible evidence enriches all three registered section slots;
- 80% and 50% coverage boundaries map to supported and limited states;
- below-minimum coverage is unavailable;
- partial compatibility caps confidence and incompatible evidence fails closed;
- market and production evidence expire at the completion-time boundary;
- age-risk validity remains categorical rather than inferred;
- actual selection is classified against the saved expected window;
- missing evidence remains explicit and contains no step 6 deferral marker;
- generation does not change snapshots, signals, or alert configuration;
- source keys and private references do not leak;
- safe report-player evidence contains only the approved sanitized field subset; and
- identical generation remains idempotent.

The full backend, frontend, migration, contract, build, and dependency gates
remain required before publication.

## Acceptance Criteria

1. Only the three approved optional sections receive Phase 5 enrichment.
2. Freshness is evaluated at saved draft completion time.
3. Coverage uses the approved 50% and 80% boundaries independently per field.
4. Enriched confidence never exceeds medium.
5. Partial, stale, expired, invalid, unknown, and incompatible states fail
   closed at their approved boundaries.
6. Expected-selection context is observational and uses no grading language.
7. Missing evidence remains visible and honest.
8. Private and raw source information is excluded from report transport and
   safe persistence.
9. Source domains remain unchanged.
10. Fingerprint replay is deterministic and idempotent.
11. No deferred Phase 6 feature is pulled into this module.
12. The full repository verification gate passes.

## Next Implementation Boundary

Phase 6 step 7 implements this boundary in the
[saved strategy and decision-moment contract](phase-6-strategy-decision-moments.md).
The next boundary is compatible comparison preview, without export, desktop
work, grades, projections, or automated advice.
