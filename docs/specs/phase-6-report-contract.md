# Phase 6 Report Definitions and Expected-Fixture Contract

**Status:** Bounded implementation contract

**Date:** 2026-07-29

**Parent specification:** [Phase 6 Post-Draft Report](phase-6-post-draft-report.md)

## Outcome

This contract implements Phase 6 step 2: freeze the report section registry,
availability thresholds, starter-assignment rules, explanation templates, and
fictional expected fixtures before report-engine, persistence, API, export, or
desktop code begins.

The versioned rules file is the report's show bible. The expected fixtures are
its shot list: they identify the exact inputs and results the later engine must
reproduce without giving that engine permission to invent new product meaning.

## Approved Product Decisions Applied

1. The report is an evidence ledger, not a grade or composite score.
2. Reports are completed-draft-only immutable snapshots.
3. Core saved state always powers the report; optional compatible Phase 5
   evidence enriches only the fields it actually supports.
4. Decision moments remain observational, comparisons declare no winner, and
   the first export format is standalone offline HTML.

These decisions were approved by the product owner on 2026-07-29.

## Authorized Artifacts

- [report definitions JSON Schema](../schemas/post-draft-report-definitions.schema.json);
- [expected-fixture JSON Schema](../schemas/post-draft-report-expected-fixtures.schema.json);
- [V1 report definitions](../requirements/post-draft-report-definitions.v1.json);
- `tests/fixtures/post_draft_reports/phase-6-report-v1.expected.json`; and
- offline contract tests for schema validity, semantic boundaries, fictional
  fixture safety, stable hashing, and forbidden explanation language.

This step does not authorize:

- report-domain Python modules;
- a database migration;
- report persistence;
- an API route;
- HTML export;
- frontend navigation or components; or
- any mutation of drafts, boards, mocks, alerts, or evidence.

## Version Contract

The V1 artifacts freeze three independent versions:

- `post-draft-report-rules-v1`: section meanings, thresholds, limits, and
  deterministic calculation policies;
- `post-draft-report-explanations-v1`: template text and required
  placeholders; and
- `post-draft-report-fixtures-v1`: fictional expected cases used by later
  engine tests.

The future engine receives its own version when Phase 6 step 3 begins. Changing
one of the three versions above requires a reviewed contract change and new or
updated expected fixtures.

## Stable Section Registry

The V1 registry has fourteen keys:

1. `draft_summary`;
2. `position_inventory`;
3. `starter_coverage`;
4. `roster_concentration`;
5. `year_one_production_context`;
6. `dynasty_market_context`;
7. `age_risk_profile`;
8. `long_term_value`;
9. `liquidity`;
10. `player_fragility`;
11. `strategy_story`;
12. `personal_board_choice_moments`;
13. `recorded_alert_moments`; and
14. `evidence_limits`.

Separating long-term value, liquidity, and player fragility gives each roadmap
promise a visible unavailable state rather than hiding it inside another
section.

Every generated section later uses the approved availability enum:
`supported`, `limited`, `unavailable`, or `not_applicable`. Confidence is
`high`, `medium`, `low`, or `unavailable`.

## Availability and Confidence Rules

### Direct saved-state sections

Draft summary, position inventory, and evidence limits are `supported` with
`high` confidence after report eligibility succeeds.

Starter coverage and roster concentration are:

- `supported` with `high` confidence when the league shape and all required
  player eligibility are normalized;
- `limited` with `low` confidence when a usable maximum assignment exists but
  one or more rostered players has unknown or unsupported eligibility; and
- `unavailable` with `unavailable` confidence when league starter shape cannot
  be normalized.

### Optional categorical evidence

Year-one production, dynasty market, and age-risk sections use the same usable
roster coverage thresholds:

- below `50%`: `unavailable`;
- at least `50%` and below `80%`: `limited`; and
- at least `80%`: `supported`.

The boundary calculation uses integer counts:

```text
coverage_basis_points = floor(covered_players * 10_000 / roster_players)
```

The thresholds are therefore exactly `5000` and `8000` basis points. A zero
player roster is invalid report input, not an unavailable evidence case.

Baseline confidence is:

- `medium` for supported compatible usable evidence;
- `low` for limited compatible usable evidence; and
- `unavailable` when the section is unavailable.

All three categorical evidence sections are capped at `medium`. Incompatible,
invalid, or expired evidence makes the section unavailable regardless of
coverage. Freshness and format limitations may reduce confidence but never
raise it above the cap.

### Explicitly unsupported sections

Long-term value, liquidity, and player fragility are always `unavailable` with
`unavailable` confidence in V1. A market band cannot satisfy long-term value or
liquidity, and rookie status cannot satisfy age or outcome evidence.

### Mode and event sections

- Strategy story is supported for a mock with valid saved strategy history,
  limited when its saved history is incomplete, and `not_applicable` for a
  live draft.
- Personal Board choice moments are a supported observation even when zero
  qualifying moments exist, provided the frozen board snapshot is valid.
- Recorded alert moments are a supported historical state when alerts were not
  configured, disabled, configured with no saved events, or configured with
  saved events. Corrupt saved event history makes the section unavailable.

## Starter Assignment

Starter assignment is coverage analysis, not lineup advice.

1. Expand the normalized starter configuration into slots with unique
   zero-based `slot_order`.
2. Create an edge only when a player's frozen fantasy-position eligibility is
   accepted by a slot.
3. Find every assignment with the maximum number of filled slots, using each
   player and slot at most once.
4. Represent an assignment as its filled edge tuples sorted by slot order:
   `(slot_order, overall_pick, canonical_player_id)`.
5. Choose the lexicographically smallest complete tuple list.
6. Keep unassigned rostered players in depth inventory under their frozen
   primary position.

An `ambiguous_flex_slot` is a configured flexible slot whose chosen player can
be replaced in at least one other maximum-cardinality assignment without
reducing the number of filled slots. This count describes assignment
ambiguity; it does not lower coverage or recommend a lineup.

Unknown eligibility never creates a guessed edge. If normalized starter shape
exists, the assignment may remain usable with a visible
`PLAYER_ELIGIBILITY_INCOMPLETE` limitation.

## Concentration Boundaries

Position share is calculated from user roster pick counts in basis points:

```text
position_share_basis_points =
  floor(position_pick_count * 10_000 / total_user_picks)
```

Construction bands are:

- `balanced_distribution`: maximum share is at most `4000` basis points and
  every distinct starter position is covered;
- `concentrated`: maximum share is greater than `4000` and at most `5500`;
- `highly_concentrated`: maximum share is greater than `5500`; and
- `coverage_gap`: at least one distinct configured starter position is
  unfilled.

`coverage_gap` may coexist with `concentrated` or `highly_concentrated`.
`balanced_distribution` cannot coexist with a coverage gap. The three
share-based bands are mutually exclusive.

## Explanation Contract

All result-characterizing prose comes from
`post-draft-report-explanations-v1`. Each template has:

- a stable key;
- an exact template string;
- a sorted list of required placeholders; and
- one of the approved section keys.

Template values are plain text. Later rendering must reject missing or extra
placeholder values and escape user-controlled text at the HTML boundary.

The forbidden-language list is mechanically scanned case-insensitively against
all template text and all rendered expected explanations. Exact
source-provided bands may be displayed only as quoted provenance; templates do
not adopt those labels as Hub judgments.

## Expected Fixture

The public fixture collection is deliberately fictional and includes:

- one complete Superflex roster with a flex-assignment tie;
- exact evidence-coverage cases at `49%`, `50%`, `79%`, and `80%`;
- concentration cases at `40%`, `41%`, `55%`, and `56%`, plus a coexisting
  starter-coverage gap;
- live and mock mode expectations;
- unavailable long-term, liquidity, and fragility expectations; and
- rendered explanation examples.

The fixture hash is SHA-256 over UTF-8 canonical JSON with sorted object keys
and compact separators, excluding only its own `content_hash` field. Equivalent
fixture content must therefore hash identically.

## Contract Tests

The bounded tests verify:

- both JSON Schemas are valid Draft 2020-12 schemas;
- definitions and expected fixtures validate;
- version, enum, registry, and template keys are unique;
- the registry contains exactly the fourteen approved section keys;
- thresholds implement the exact approved boundaries;
- starter slots, players, assignments, depth, and ambiguity expectations are
  internally consistent;
- fixture cases cover every required boundary;
- explanation placeholders match template contents;
- no template or rendered example contains forbidden language;
- all public identities and labels are fictional;
- prohibited private fields do not appear;
- the fixture content hash is stable; and
- representative malformed variants fail schema or semantic checks.

The tests validate the frozen contract, not production report calculations.
Phase 6 step 3 will make the pure engine reproduce these expectations.

## Acceptance Criteria

1. The four approved product decisions are recorded in the parent
   specification.
2. The section registry is strict, versioned, and complete.
3. Availability and confidence boundaries are mechanically testable.
4. `49%`, `50%`, `79%`, and `80%` evidence coverage produce the approved
   states.
5. `40%`, `41%`, `55%`, and `56%` position shares produce the approved bands.
6. Starter assignment maximizes filled slots before applying its stable
   tie-break.
7. Flex ambiguity and depth inventory have exact definitions and fictional
   expected results.
8. Unsupported roadmap sections remain visible and unavailable.
9. All explanation templates are versioned and free of prohibited verdict or
   predictive language.
10. Fixtures contain no real provider, league, player, or private source data.
11. Schemas reject unknown fields and representative invalid values.
12. Contract tests pass fully offline.

## Next Implementation Boundary

After this contract is reviewed, Phase 6 step 3 may add the pure deterministic
report definitions and engine needed to reproduce the expected fixtures.

Database migrations, report persistence, APIs, exports, and desktop components
remain out of scope until their later implementation steps.
