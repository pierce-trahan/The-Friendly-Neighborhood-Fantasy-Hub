# Phase 5 Deterministic Alert Engine Fixtures

**Status:** Bounded implementation contract

**Date:** 2026-07-28

**Parent specification:** [Phase 5 Value and Trade-Up Alerts](phase-5-value-trade-up-alerts.md)

**Input contract:** [Phase 5 Evidence Import and Freshness Contract](phase-5-evidence-contract.md)

## Outcome

This contract implements Phase 5 step 3 as a pure Python rules module.

It calculates ranges and bands from already validated inputs. It does not read
or write SQLite, create saved alert events, expose an API, render a component,
select a player, or propose a real-world trade.

The same inputs always return the same output. There is no random draw,
network request, system clock read, floating-point score, or generative model.

## Version

- engine: `alert-engine-v1`;
- rules: `alert-rules-v1`;
- default conservative value gap: `6` overall picks;
- target-window safety buffer: `2` overall picks; and
- maximum returned cost references: `3`.

Changing a formula, boundary, or default requires a new version and new
cross-language expected fixtures.

## Public Types

### `IntegerRange`

An inclusive integer interval:

- `low`;
- `high`; and
- `low <= high`.

Market gaps may be negative. Pick coordinates and expected-selection ranges
must be positive. Pick values and incremental costs must be non-negative.

### `ConfidenceAssessment`

- level: `high`, `medium`, `low`, or `unavailable`; and
- stable sorted reason codes.

### `CurrentPickValue`

- overall pick; and
- source value range.

### `PickAssetValue`

- generic asset key;
- future season offset;
- round;
- source value range.

The type has no player field, ownership field, or offer action.

## Market Gap

For current overall pick `C` and expected window `[L, H]`:

```text
gap_low  = C - H
gap_high = C - L
```

A default value alert is eligible only when:

- the caller has already established personal qualification;
- confidence is not unavailable; and
- `gap_low >= 6`.

The engine never converts the range into a single displayed player score.

## Personal Qualification

The pure helper returns true when:

- `favorite` is true; or
- a positive tier order is no greater than the configured eligible tier count.

The default eligible tier count is `2`. A count of zero disables tier
qualification but does not disable explicit favorites.

This helper reads caller-supplied frozen facts only. It does not query a
Personal Board.

## Return Risk

For expected window `[L, H]` and next user pick `N`:

- `likely_to_return` when `L >= N`;
- `unlikely_to_return` when `H < N`;
- `uncertain` otherwise; and
- `unavailable` when either input is absent.

This is a range relationship, not a probability.

## Freshness

### Elapsed-day evidence

The caller supplies timezone-aware evidence and evaluation timestamps plus the
versioned policy thresholds.

Age is the difference between UTC calendar dates. Boundaries are inclusive:

- age through `fresh_through_days`: `fresh`;
- then through `aging_through_days`: `aging`;
- then through `stale_through_days`: `stale`;
- later: `expired`; and
- a future evidence date: `invalid`.

Thresholds must be non-negative and strictly increasing.

### Season-labeled production

- current season: `fresh`;
- one prior season: `aging`;
- older: `stale`;
- missing: `expired`; and
- future season: `invalid`.

### Birthdate validity

- valid: `fresh`;
- source conflict: `stale`; and
- missing or invalid: `expired`.

## Confidence

Confidence is unavailable when:

- mapping is not exact;
- the expected-selection window is absent;
- critical freshness is expired or invalid; or
- format compatibility is incompatible or unknown.

High requires:

- exact mapping;
- fresh evidence;
- exact format;
- expected-window width no greater than 8; and
- no critical limitation.

Medium requires:

- exact mapping;
- fresh or aging evidence;
- exact or family format;
- expected-window width no greater than 20; and
- no critical limitation.

All other usable inputs are low. Stale, partial-format, broad-window, and
critical-limitation reason codes remain visible.

## Target Pick Window

A target exists only for `unlikely_to_return`.

First intersect:

```text
unmade range    = [current overall pick, next user pick - 1]
expected range  = [expected low, expected high]
```

If there is no intersection, return unavailable.

For intersection `[I-low, I-high]` and safety buffer `B`:

```text
target_low  = max(current overall pick, I-low - B)
target_high = max(target_low, I-high - B)
```

The final high cannot reach or pass the next user pick.

The buffer deliberately moves the reference earlier. It does not claim that a
specific manager will select the player.

## Current-Pick Curve

The curve must contain unique positive overall picks and non-negative value
ranges. Both low and high endpoints must be non-increasing as overall picks
increase.

Exact listed picks return their source range.

An unlisted pick between two source points is interpolated independently for
both endpoints with exact rational arithmetic:

```text
value = left + (right - left) * offset / span
```

The low endpoint rounds down and the high endpoint rounds up so interpolation
does not manufacture false narrowness.

Picks outside the bounded curve return unavailable; extrapolation is forbidden.

## Incremental Pick-Only Cost

For a user next-pick range, earliest target range, and latest target range:

```text
increment_low  = max(0, latest_target_low - user_pick_high)
increment_high = max(0, earliest_target_high - user_pick_low)
```

The target window must end before the user pick.

The matcher returns individual generic future-round asset classes whose source
value ranges overlap the incremental range. It:

- accepts pick asset types only;
- rejects duplicate asset keys;
- sorts by source-range midpoint, season offset, round, and key;
- returns at most three; and
- does not combine assets or optimize packages.

Multi-asset enumeration, ownership, and offer construction remain deferred.

## Expected Fixture

`tests/fixtures/alert_engine/phase-5-engine-v1.expected.json` freezes:

- positive, boundary, and negative market gaps;
- all three available return-risk bands;
- every elapsed freshness boundary plus a future timestamp;
- target windows with and without the default buffer; and
- an interpolated trade-cost range matched to the synthetic pick curve.

The expected fixture contains no player recommendation or provider data.

## Test Plan

Every public rule branch receives at least one focused unit assertion:

- valid and invalid integer ranges;
- personal tier and favorite qualification;
- conservative gap threshold at 5 and 6;
- all return-risk bands and missing inputs;
- inclusive freshness boundaries;
- season and birthdate validity states;
- high, medium, low, and unavailable confidence paths;
- sorted, deduplicated reason codes;
- buffered, unbuffered, absent, and invalid target windows;
- exact, interpolated, and out-of-bounds curve lookups;
- curve duplicates and monotonicity rejection;
- incremental cost endpoint math;
- overlap boundaries, deterministic ordering, and three-result cap;
- duplicate asset rejection; and
- the full expected JSON fixture against the synthetic evidence curve.

The full backend regression suite must also pass.

## Acceptance Criteria

1. All functions are pure and persistence-free.
2. Identical inputs reproduce identical dataclass values.
3. The conservative gap threshold uses the low endpoint.
4. Missing inputs never become zero.
5. No probability is calculated or returned.
6. Freshness uses explicit UTC dates and versioned thresholds.
7. Confidence downgrades match the parent specification.
8. Target windows end before the next user pick.
9. Curve interpolation uses exact rational arithmetic and outward rounding.
10. Extrapolation is forbidden.
11. Cost references contain picks only and return at most three.
12. Expected fixtures and the full backend suite pass.

## Next Implementation Boundary

After this module is approved, Phase 5 step 4 may add SQLite persistence for
evidence snapshots, player signals, pick curves, alert configuration,
configuration revisions, evaluations, events, and trade references.

No migration or API work is included here.
