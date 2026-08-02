# Phase 6 Deterministic Report Engine Fixtures

**Status:** Bounded implementation contract

**Date:** 2026-07-29

**Parent specification:** [Phase 6 Post-Draft Report](phase-6-post-draft-report.md)

**Input contract:** [Phase 6 Report Definitions and Expected-Fixture Contract](phase-6-report-contract.md)

## Outcome

This contract implements Phase 6 step 3 as a pure Python rules module. It
reproduces the approved expected fixtures for:

- canonical JSON and fingerprints;
- deterministic maximum starter assignment;
- stable assignment tie-breaking;
- flex-assignment ambiguity;
- depth inventory;
- categorical evidence coverage;
- construction concentration;
- live/mock strategy-section state;
- explicitly unsupported V1 sections; and
- versioned explanation rendering.

The module does not read or write SQLite, load a draft, evaluate source
freshness, expose an API, render HTML, or create a frontend component.

## Versions

- engine: `post-draft-report-engine-v1`;
- rules: `post-draft-report-rules-v1`; and
- explanations: `post-draft-report-explanations-v1`.

Changing a calculation, tie-break, boundary, template, or canonicalization rule
requires a reviewed version change and updated expected fixtures.

## Runtime Definitions

`backend/src/friendly_hub/domains/reports/definitions.py` contains immutable
runtime constants for:

- engine, rule, and explanation versions;
- `5000` and `8000` evidence-coverage boundaries;
- `4000` and `5500` concentration boundaries;
- the six supported starter-slot types and their exact eligibility;
- blocking evidence states;
- always-unavailable V1 section reasons; and
- all approved explanation templates.

Tests compare every runtime template and version with the approved JSON
definitions so the executable rules cannot silently drift from the reviewed
contract.

## Canonical JSON and Fingerprints

`canonical_json`:

- sorts object keys;
- preserves array order;
- preserves explicit null values;
- emits compact UTF-8 JSON;
- rejects non-JSON objects; and
- rejects non-finite numbers.

`content_fingerprint` returns the lowercase SHA-256 digest of that canonical
UTF-8 representation.

The future service remains responsible for building the approved report input
document, normalizing timestamps to UTC, and excluding generated or private
fields before calling the pure fingerprint helper.

## Starter Input Types

### `StarterSlot`

- zero-based unique `slot_order`;
- stable `slot_key`;
- supported slot type; and
- the exact V1 eligibility set for that slot type.

### `RosterPlayer`

- canonical player id;
- unique positive overall pick;
- frozen primary position; and
- frozen fantasy-position eligibility.

An empty or unsupported fantasy-position set creates no guessed assignment
edge and makes an otherwise usable result visibly limited.

## Starter Assignment Algorithm

The engine:

1. validates and sorts slots by `slot_order`;
2. validates and sorts players by `(overall_pick, canonical_player_id)`;
3. finds the maximum bipartite-matching cardinality;
4. visits each slot in order;
5. tries eligible players in `(overall_pick, canonical_player_id)` order;
6. accepts the first choice that still permits the global maximum;
7. treats leaving a slot empty as the last choice;
8. records unmatched players as depth under frozen primary position; and
9. reports unfilled slots without converting coverage into lineup advice.

This realizes the approved lexicographically smallest list of
`(slot_order, overall_pick, canonical_player_id)` tuples while ensuring
maximum coverage takes priority over the tie-break.

### Flex ambiguity

For each assigned `FLEX` or `SUPER_FLEX` slot, the engine forces each other
eligible player into that slot and recomputes the remaining maximum matching.
The slot is ambiguous when at least one replacement preserves the global
filled-slot count.

Ambiguity is a roster-construction fact. It does not lower confidence, select a
lineup, or rank the interchangeable players.

### Availability

- normalized shape plus complete eligibility: `supported`, `high`;
- normalized shape plus unknown or unsupported eligibility: `limited`, `low`;
- missing normalized starter shape: `unavailable`, `unavailable`.

An incomplete but normalized roster may have unfilled slots while the
calculation itself remains supported.

## Categorical Evidence Coverage

The engine calculates:

```text
coverage_basis_points = floor(covered_players * 10_000 / roster_players)
```

For usable evidence:

- below `5000`: unavailable;
- `5000` through `7999`: limited with low confidence; and
- `8000` or higher: supported with medium confidence.

Expired, incompatible, or invalid evidence is unavailable regardless of
coverage. A zero-player roster and covered counts outside the roster bounds are
invalid inputs.

The helper is source- and section-neutral. A later service maps its stable
result into the section-specific approved reason and limitation codes.

## Construction Concentration

The engine verifies that position counts sum exactly to the roster-pick total,
then calculates the maximum position share in basis points.

- through `4000`: `balanced_distribution` when starter coverage has no gap;
- above `4000` through `5500`: `concentrated`;
- above `5500`: `highly_concentrated`; and
- any unfilled distinct starter position adds `coverage_gap`.

A coverage gap suppresses `balanced_distribution` and may coexist with either
concentration band.

## Section-State Helpers

`strategy_section_state` returns:

- valid mock history: supported/high;
- incomplete mock history: limited/low;
- corrupt mock history: unavailable/unavailable; and
- any live draft: not-applicable/unavailable.

`unsupported_section_state` accepts only:

- `long_term_value`;
- `liquidity`; and
- `player_fragility`.

Each remains unavailable with the approved reason code.

## Explanation Rendering

`render_explanation` accepts a supported template key plus an exact placeholder
mapping. It rejects:

- unknown template keys;
- missing placeholders;
- extra placeholders;
- boolean values; and
- values other than strings or integers.

The helper returns plain text. HTML escaping remains the responsibility of the
later export boundary.

## Test Plan

Focused unit tests cover:

- runtime-definition parity with the approved JSON contract;
- fixture reproduction independent of input order;
- maximum coverage before lexicographic tie-breaking;
- deterministic repeat results;
- expected flex ambiguity and depth counts;
- missing shape;
- incomplete eligibility;
- all `49%`, `50%`, `79%`, and `80%` evidence cases;
- expired, incompatible, and invalid evidence;
- all `40%`, `41%`, `55%`, and `56%` concentration cases;
- a concentration band coexisting with a coverage gap;
- mock, live, incomplete, and corrupt strategy states;
- all three unsupported V1 sections;
- every rendered explanation in the expected fixture;
- exact placeholder validation;
- canonical object-order invariance;
- array-order sensitivity;
- explicit null preservation;
- non-finite and non-JSON rejection; and
- representative malformed slot, roster, evidence, concentration, mode, and
  section inputs.

The existing Phase 6 contract tests remain part of the gate. The full backend
and repository regression suites must also pass.

## Performance Check

The maximum supported synthetic stress case uses:

- `60` rostered players;
- `60` `SUPER_FLEX` slots;
- maximum-cardinality assignment;
- lexicographic reconstruction; and
- ambiguity evaluation for every flexible slot.

The local verification run completed this calculation in approximately
`0.13 seconds`, below the Phase 6 one-second report-generation target before
any persistence or transport overhead exists.

This benchmark is a development check, not a promise that future database and
export work is free.

## Acceptance Criteria

1. All functions are deterministic, synchronous, offline, and persistence-free.
2. Runtime versions and templates match the approved JSON definitions.
3. Canonical fingerprints are stable across object-key ordering.
4. Non-finite and non-JSON fingerprint inputs fail closed.
5. Starter assignment fills the maximum eligible slot count.
6. The approved tuple order selects among equally maximal assignments.
7. Flex ambiguity and depth match the fictional expected fixture.
8. Missing or incomplete eligibility never creates a guessed edge.
9. Evidence availability matches every approved boundary and blocking state.
10. Concentration matches every approved boundary and gap combination.
11. Mode-specific and always-unavailable states match the approved fixtures.
12. Explanation rendering requires exact placeholder values.
13. No database, API, HTML, frontend, network, clock, randomness, or
    generative-model dependency is introduced.
14. Focused and full repository verification pass.

## Next Implementation Boundary

After this module is reviewed, Phase 6 step 4 may add only the report, player,
section, and moment persistence model plus migration and round-trip tests.

Completed-draft eligibility, generation APIs, optional evidence enrichment,
moments, comparisons, export, and desktop work remain out of scope.

The bounded step 4 implementation is recorded in
[Phase 6 Post-Draft Report Persistence](phase-6-report-persistence.md).
