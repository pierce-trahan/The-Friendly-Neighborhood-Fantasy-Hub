# Phase 6 Compatible Report Comparison Preview

**Status:** Bounded implementation contract

**Date:** 2026-08-03

**Parent specification:** [Phase 6 Post-Draft Report](phase-6-post-draft-report.md)

**Predecessor:** [Phase 6 Saved Strategy and Decision Moments](phase-6-strategy-decision-moments.md)

## Outcome

This contract implements Phase 6 step 8. The local API may compare two through
four immutable saved reports when they share the same league-shape fingerprint
and report-rules version. The preview is descriptive: it aligns saved sections
and approved counts without naming a winner, ranking a roster, or calculating a
composite score.

The first requested report is a display baseline only. Request order is
preserved, and a delta from the first report is arithmetic context rather than
a quality judgment.

This step adds no comparison persistence, HTML export, frontend workspace,
projection, recommendation, grade, or database migration.

## API Contract

`POST /api/v1/post-draft-report-comparisons/preview`

Request:

```json
{
  "report_ids": ["report-a", "report-b"]
}
```

Rules:

- exactly two through four ids;
- ids are unique and request order is authoritative;
- every id must resolve to a complete immutable report;
- all reports share one league-shape fingerprint;
- all reports share one report-rules version;
- a global compatibility failure returns `409` and no deltas;
- missing reports return `404`; and
- the endpoint performs no write or network request.

The response contains compatibility metadata, ordered safe report identities,
all registered report sections, per-report availability/confidence and approved
safe values, exact deltas from the first report where allowed, limitations, and
versioned explanatory text.

## Safe Report Identity

Each selected report exposes only:

- report and source-draft ids;
- frozen draft name, mode, completion time, format, team and round counts;
- report engine/rules/explanation versions;
- league-shape fingerprint; and
- initial/final strategy plus strategy-definition version when safely saved.

Current draft names, private notes, provider ids, source keys, CPU audit fields,
and raw JSON are prohibited.

## Section Compatibility

Every registered section appears in registry order.

A section is `comparable` only when every report marks it `supported` or
`limited`. Otherwise it is `not_comparable` and contains no deltas. The strategy
section also requires every selected report to be a mock and to contain the
same saved strategy-definition version. A live/mock mix is globally compatible
when league shape and report rules match, but its strategy section is
`not_comparable`.

Approved safe values and exact delta families are:

| Section | Safe values | Exact deltas |
|---|---|---|
| Draft summary | mode, format, team/round/user-pick/starter/bench counts | none |
| Position inventory | position counts | position counts |
| Starter coverage | total/filled slots, unfilled labels, depth counts | filled slots and depth counts |
| Concentration | categorical bands, position shares, gaps, surplus counts | none |
| Production, market, age risk | coverage, categorical band/freshness distributions | categorical distributions |
| Strategy story | pivot and guidance-state counts | pivot and guidance-state counts |
| Personal Board moments | qualifying and retained moment counts | retained moment count |
| Recorded alerts | full and included event counts, kind/status counts | full event count |
| Evidence limits | limited/unavailable section keys | none |

Long-term value, liquidity, player fragility, or any other unsupported section
remains `not_comparable`. No absent metric is interpreted as zero.

## Determinism, Privacy, and Language

- The preview is rebuilt from immutable safe report rows on every request.
- Report and section order are deterministic.
- Mapping keys are sorted before response serialization.
- Only validated integers, categorical codes, and generated labels enter the
  preview.
- The response excludes roster player names and all moment payloads because
  neither is needed for construction comparison.
- The words and concepts `winner`, `best`, `worst`, grade, projection,
  championship odds, expected points, objective value, and hindsight
  correctness are prohibited.
- Limitations always include `DESCRIPTIVE_COMPARISON_ONLY`,
  `NO_WINNER_OR_RANKING`, and `FIRST_REPORT_IS_DISPLAY_BASELINE`.

## Verification Strategy

Unit coverage proves allowlisted projection, exact signed deltas, missing-key
handling, section `not_comparable` behavior, mock-only strategy compatibility,
stable order, and forbidden-language absence.

API coverage proves two-to-four bounds, duplicate rejection, missing-report
handling, league/rules incompatibility rejection, mixed-mode strategy handling,
no persistence or source mutation, offline execution, and a response below the
`500` millisecond contract target for a normal four-report preview.

The full repository verifier remains the publication gate.

## Acceptance Criteria

1. Two through four unique compatible reports can be previewed offline.
2. Request order is preserved and the first report is labeled only as baseline.
3. League-shape or report-rules mismatch returns `409` without deltas.
4. Every registered section appears exactly once in registry order.
5. Unsupported or mixed-support sections are `not_comparable`.
6. Strategy comparison requires all-mock mode and one saved strategy version.
7. Exact deltas exist only for the approved count families.
8. Missing metrics are never guessed as zero.
9. The preview creates or updates no database row.
10. The response contains no private, raw, provider, player, moment, grade,
    winner, predictive, or hindsight content.
11. Equivalent requests produce identical content apart from transport metadata.
12. The full repository verification gate passes.

## Next Implementation Boundary

After this module is reviewed, Phase 6 step 9 may add only standalone safe HTML
export for one immutable report. It must add no JavaScript, external asset,
remote request, sharing workflow, comparison persistence, or desktop work.
