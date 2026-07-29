# Phase 5 Specification: Value and Trade-Up Alerts

**Status:** Approved for bounded implementation

**Date:** 2026-07-28

## How to Use This Document

- The product owner approves or changes the four product-gate decisions before
  implementation begins.
- The implementation engineer follows the source, persistence, deterministic
  evaluation, API, and desktop contracts in order.
- The auditor uses the privacy rules, test strategy, acceptance tests, and exit
  criteria before Phase 5 is called complete.

Related documents:

- [V1 roadmap](../../PROJECT_ROADMAP.md);
- [local-browser architecture](../adr/0001-local-browser-application-architecture.md);
- [local data model](../adr/0002-local-data-and-configuration-model.md);
- [module boundaries](../adr/0003-repository-and-module-structure.md);
- [Phase 2 Personal Board](phase-2-personal-board.md);
- [Phase 3 Draft Room](phase-3-draft-room.md);
- [Phase 4 Mock and Strategy Lab](phase-4-mock-strategy-lab.md);
- [editorial workstation UI](../design/editorial-workstation-ui.md); and
- [errors and logging standard](../standards/errors-and-logging.md).

## Outcome

Phase 5 adds explainable decision-point alerts to active live and mock drafts.

The feature helps the user notice when personal conviction, a
provenance-tracked market window, roster context, and the next user pick create
a meaningful decision. It may explain that a player has fallen beyond a market
range, warn that a personally valued player may not return, or show a bounded
pick-only trade-up reference.

The feature does not declare an objective steal, expose a market ranking as the
main draft board, select a player, submit a trade, or hide uncertainty behind a
single magic score.

## Product Approval Decision

The product owner approved the following four decisions on 2026-07-28.

### Gate 1: Evidence source boundary

**Approved decision:** V1 accepts versioned, provider-neutral local CSV
snapshots through preview and explicit commit. Development and public tests use
only a synthetic fixture. Direct provider synchronization, scraping, and
bundled proprietary data remain deferred.

Each committed snapshot must identify its source label, permitted-use basis,
league-format compatibility, as-of timestamp, and content hash. Unmapped or
ambiguous players do not produce alerts.

Options considered:

| Option | Benefit | Cost or risk | Recommendation |
| --- | --- | --- | --- |
| Local provider-neutral snapshot | Auditable, offline, source-replaceable, and compatible with public-repository privacy | The user must refresh and import data | Recommended |
| Direct provider integration now | Less manual refresh work | Adds credentials, terms, network, and mapping risk before the alert contract is proven | Defer |
| Personal Board as market evidence | No new import | Falsely treats personal conviction as independent market evidence | Reject |

### Gate 2: Alert trigger philosophy

**Approved decision:** Use a dual-evidence trigger. A player must have an
explicit personal-conviction signal and sufficient independent market evidence
before a value or return-risk alert may open.

The default personal qualifier is either:

- a player in one of the first two Personal Board tiers; or
- a player explicitly marked as a favorite.

The default market qualifier is a fresh or aging expected-selection window
whose conservative edge has been passed by at least six overall selections.
The user may change thresholds, but cannot convert missing evidence into high
confidence.

Options considered:

| Option | Benefit | Cost or risk | Recommendation |
| --- | --- | --- | --- |
| Personal plus market evidence | Centers the user's convictions while adding independent context | Some market movers will stay quiet when the user has no conviction | Recommended |
| Market-only alerts | Maximizes alert coverage | Recreates an ADP feed and anchors the user to consensus | Reject |
| Personal-only alerts | Works with no new source | Cannot make a supported return-risk or trade-up claim | Keep as a visible watchlist, not a Phase 5 market alert |

### Gate 3: Pick-only trade-up boundary

**Approved decision:** Show a target overall-pick window and, only when a
compatible pick-value curve exists, a generic pick-only cost band. Packages may
contain draft picks only. They are reference ranges, never exact offers or
claims about assets the user owns.

If the pick-value curve is missing, stale beyond its hard limit, or
format-incompatible, the player alert remains available but the cost section
says `Pick-only cost unavailable`.

Options considered:

| Option | Benefit | Cost or risk | Recommendation |
| --- | --- | --- | --- |
| Target window plus ranged pick-only reference | Fulfills the roadmap without implying certainty | Requires a second provenance-tracked curve | Recommended |
| Target window only | Simple and honest | Does not fully satisfy the planned cost-range deliverable | Safe fallback |
| Exact optimizer or player-plus-pick package | Looks actionable | Implies false precision and expands beyond V1 | Reject |

### Gate 4: Presentation and control

**Approved decision:** Keep all market fields out of Blind view. In decision
support views, show one compact alert rail with plain-language evidence,
confidence, freshness, and downside. Raw imported rank or pick-window fields
appear only in an explicit evidence drawer.

Alerts are enabled when a compatible snapshot is attached, but the user may:

- disable all alerts for one draft;
- dismiss one alert for the rest of that draft;
- snooze one alert for five saved picks or until the next user turn, whichever
  comes first; and
- reopen a dismissed or snoozed alert from alert history.

Options considered:

| Option | Benefit | Cost or risk | Recommendation |
| --- | --- | --- | --- |
| Context rail plus evidence drawer | Keeps the board personal-first while preserving auditability | Adds one deliberate inspection step | Recommended |
| Visible market columns | Easy comparison | Turns the draft room into an ADP board | Reject |
| Toast-only alerts | Minimal layout impact | Easy to miss and difficult to audit | Reject |

## Design Trade-offs

| Decision | Benefit | Cost accepted for V1 | Revisit trigger |
| --- | --- | --- | --- |
| Import frozen local evidence snapshots | Drafts remain reproducible and offline | Refresh is manual | A permitted authenticated source is approved |
| Evaluate alerts separately from draft mutations | A failed alert can never lose or block a saved pick | The client performs one idempotent follow-up request | Measured latency or reconciliation complexity becomes disruptive |
| Trigger on dual evidence | Protects the user's authority and reduces noise | Some consensus values do not alert | Users consistently request a market-only mode |
| Display ranges and bands, not a composite score | Avoids fake precision and makes disagreements visible | The engine cannot sort the board by a single value number | A later approved research module proves a useful calibrated model |
| Snapshot evidence per draft | Historical alerts remain explainable after imports change | Active drafts do not silently receive new data | The user explicitly replaces the attached snapshot |
| Keep alerts out of Blind view | Preserves the Phase 3 context-free contract | Users must change views to use Phase 5 guidance | The Blind product meaning is explicitly changed |

No new technology ADR is required. The accepted React, FastAPI, and SQLite
architecture remains sufficient. Phase 5 adds a bounded `alerts` domain and
does not introduce a background service, cloud dependency, or required
network.

## Existing Inputs and Known Gaps

### Available now

- canonical player identity and manual mapping;
- frozen draft candidate identity, position, rookie flag, team, and Personal
  Board context;
- Personal Board order, tier, and favorite state;
- league shape and scoring settings when a profile is attached;
- deterministic linear, snake, and third-round-reversal pick order;
- current overall pick, next user pick, completed picks, correction history,
  pause, reset, and restart recovery;
- current Phase 4 strategy and roster-construction checkpoint for mocks;
- local SQLite persistence and versioned migrations; and
- safe fixture, import-preview, and explicit-commit patterns.

### Not available as approved evidence

- a real market or expected-selection snapshot;
- player age or birthdate;
- production or projection data;
- a pick-value curve;
- traded-pick ownership;
- real-world trade execution;
- calibrated player-availability probabilities; or
- permission to redistribute a proprietary provider dataset.

The specification defines consumer contracts for these inputs. The first
implementation uses a deliberately synthetic fixture plus local imports. A
missing optional component remains visibly unavailable and never becomes a
zero, neutral fact, or guessed value.

## Scope

### Included

- local preview and commit for normalized Phase 5 evidence snapshots;
- canonical player mapping with unresolved-row reporting;
- source, format, freshness, and permitted-use metadata;
- optional expected-selection, market, win-now production, age-risk, and
  pick-value evidence;
- frozen Phase 5 evidence attachment per live or mock draft;
- deterministic value-over-current-pick ranges;
- deterministic next-user-pick return-risk bands;
- personal-conviction qualification;
- strategy-fit context when a mock has Phase 4 guidance;
- target pick windows;
- generic pick-only cost bands when supported;
- traceable alert inputs, explanations, limitations, and engine versions;
- separate confidence and freshness labels;
- disable, dismiss, snooze, and reopen controls;
- append-only alert history across correction and undo;
- restart-safe idempotent evaluation;
- decision-support UI that does not add market columns to the draft board; and
- synthetic offline fixtures and a full Entropy-shaped workflow audit.

### Excluded

- required network access;
- direct Sleeper or market-provider synchronization;
- scraping;
- bundled real or proprietary market data;
- visible ADP or market-rank columns on the candidate table;
- one objective player-value score;
- calibrated probability percentages;
- automated drafting;
- automated trade submission;
- player-plus-pick packages;
- a general trade calculator;
- traded-pick ownership tracking;
- auction or keeper valuation;
- waiver or in-season alerts;
- injury, film, scouting, contract, or news analysis;
- generative-AI recommendations;
- mobile push, email, or cloud notifications; and
- Phase 6 post-draft grading.

## Roadmap Traceability

| Phase 5 roadmap promise | Contract coverage |
| --- | --- |
| dynamic value-over-current-pick signal | Conservative expected-pick gap range recalculated at a saved draft revision |
| win-now production component | Optional provenance-tracked band; unavailable when evidence is missing |
| dynasty market component | Expected-selection and market bands remain independent from Personal Board rank |
| age-risk component | Optional source-backed band with downside language; unavailable when missing |
| strategy-fit component | Phase 4 checkpoint and roster context, never a forced player |
| "your guy may not return" alert | Personal qualifier plus expected window relative to the next user pick |
| configurable thresholds | Revision-guarded per-draft alert configuration |
| pick-only trade-up range | Target overall-pick interval and optional ranged pick-only cost |
| explanation | Saved trigger facts, component bands, limitations, and template keys |
| confidence and freshness | Independent labels with documented downgrade rules |
| dismissal and snooze | Persistent reversible event controls |

## Product Rules

1. Personal Board order remains authoritative.
2. Personal conviction and market evidence are stored and displayed as
   separate inputs.
3. No alert calls a player an objective `steal`, `must draft`, or `best pick`.
4. No Phase 5 action submits a player pick or trade.
5. Blind candidate responses and Blind UI remain free of Phase 5 fields and
   alerts.
6. A market-only signal cannot open a default value or return-risk alert.
7. Missing evidence is `unavailable`, never numeric zero.
8. Stale evidence lowers confidence; expired critical evidence suppresses the
   affected alert type.
9. Every visible claim identifies its input snapshot, engine version,
   freshness state, and limitations.
10. Expected-selection ranges are contextual evidence, not guaranteed
    availability.
11. V1 never displays a probability percentage.
12. Alert evaluation is deterministic for the same draft revision,
    configuration, evidence snapshot, and engine version.
13. A draft mutation succeeds or fails independently from alert evaluation.
14. Evaluation is idempotent for one draft revision and input fingerprint.
15. Corrections and undo do not erase historical alerts; invalidated alerts are
    marked superseded.
16. A snapshot attached to an active draft never changes silently.
17. Replacing an attached snapshot requires an explicit revision-guarded
    action and creates a new configuration revision.
18. Strategy fit may explain roster construction but cannot choose a player.
19. Win-now and age-risk language must include available downside evidence.
20. A cost range uses picks only and never implies the user owns an asset.
21. No generic package is described as a fair or accepted trade.
22. Alerts may be disabled without changing draft picks or Phase 4 mock
    decisions.
23. Dismissal and snooze affect presentation only, not historical evaluation.
24. Normal logs exclude player names, provider record IDs, Personal Board
    notes, raw imported rows, and package text.
25. Public fixtures contain fictional players, sources, and values.

## Terminology

- **Evidence snapshot:** one immutable local import containing source,
  format, freshness, player-signal, and optional pick-curve records.
- **Expected-selection window:** a low-to-high overall-pick interval describing
  where a source expects a player to be selected.
- **Market gap:** the range between the current overall pick and the
  expected-selection window.
- **Personal qualifier:** a user-controlled tier or favorite condition that
  makes a player eligible for default alerts.
- **Return-risk band:** `likely_to_return`, `uncertain`, `unlikely_to_return`,
  or `unavailable`.
- **Component band:** `strong_support`, `support`, `neutral`, `caution`, or
  `unavailable`.
- **Freshness state:** `fresh`, `aging`, `stale`, or `expired`.
- **Confidence:** `low`, `medium`, or `high`; confidence is never a probability.
- **Target pick window:** a bounded set of overall picks before the user's next
  selection where a trade-up could be considered.
- **Pick-only cost band:** one or more generic draft-pick asset ranges derived
  from a compatible source curve.
- **Evaluation:** an idempotent calculation for one saved draft revision.
- **Alert event:** a saved explanation produced by an evaluation.
- **Superseded event:** historical alert evidence no longer current after a
  correction, undo, configuration revision, or source replacement.

## High-Level Flow

1. The user previews a local Phase 5 evidence file.
2. The backend validates schema, provenance metadata, format, player mappings,
   ranges, and pick-curve rows without changing active evidence.
3. The user explicitly commits an accepted preview.
4. The user attaches one compatible evidence snapshot to a draft with alert
   settings.
5. The backend freezes a draft-specific alert configuration and evidence
   fingerprint.
6. After any saved draft mutation, the client submits one guarded alert
   evaluation request.
7. The backend reconciles alerts for that exact draft revision in one
   transaction.
8. The desktop refreshes the alert rail only in a decision-support view.
9. The user may inspect evidence, dismiss, snooze, reopen, disable, or act
   manually outside the Hub.
10. On restart, the next read/evaluation reconciles any saved draft revision
    that does not yet have an alert evaluation.

## Evidence Snapshot Contract

### Snapshot metadata

Every import contains:

- `schema_version`;
- user-facing `source_label`;
- local `source_kind`: `synthetic`, `user_entered`, `public`, or `licensed`;
- `permitted_use_confirmed`;
- `as_of`;
- `format_key`;
- `scoring_shape`;
- `team_count` compatibility, when relevant;
- source timezone, when timestamps are not UTC;
- optional private source reference;
- player-signal rows;
- optional pick-value rows; and
- a deterministic content hash calculated by the Hub.

`source_label` may appear in an evidence drawer. The private source reference,
provider record IDs, and raw rows remain local and are excluded from normal
responses, logs, and exports.

`permitted_use_confirmed` records the user's import assertion. It does not
override source terms or grant redistribution rights.

### Player-signal row

One row may contain:

- canonical mapping input;
- `expected_pick_low` and `expected_pick_high`;
- optional `market_band`;
- optional `win_now_production_band`;
- optional `age_risk_band`;
- optional age or production observation timestamp;
- per-field source timestamp when different from the snapshot;
- optional format limitation codes; and
- private source record reference.

Requirements:

- range endpoints are positive integers;
- `expected_pick_low <= expected_pick_high`;
- an expected-pick endpoint cannot exceed the snapshot's declared supported
  draft depth;
- categorical bands use approved enums;
- empty cells remain absent, not zero;
- one canonical player appears at most once per snapshot; and
- ambiguous or unmatched rows never become active player signals.

### Pick-value row

One row describes one pick-only asset class:

- asset key;
- season offset;
- round;
- optional current-draft overall pick;
- value low and high;
- source timestamp; and
- format limitation codes.

The imported curve must be monotonic within a comparable asset family.
Invalid inversions block commit rather than being silently repaired.

### Preview and commit

Preview reports:

- total, valid, matched, ambiguous, unmatched, invalid, and ignored rows;
- missing required metadata;
- format compatibility;
- freshness state;
- whether a usable expected-selection window exists;
- whether a usable pick-value curve exists;
- warnings and limitation codes; and
- the resulting content hash.

Commit requires the preview identifier and hash. Repeating the same commit is
idempotent. A changed file requires a new preview.

## Freshness and Compatibility

Freshness is calculated from the evidence `as_of`, not the import time.

Proposed V1 defaults:

| Evidence | Fresh | Aging | Stale | Expired |
| --- | ---: | ---: | ---: | ---: |
| expected-selection and dynasty market | 0-7 days | 8-21 days | 22-45 days | over 45 days |
| pick-value curve | 0-30 days | 31-60 days | 61-90 days | over 90 days |
| in-season production band | 0-14 days | 15-30 days | 31-60 days | over 60 days |
| offseason production band | current labeled season | one prior labeled season | older | unknown season |
| age-risk input derived from birthdate | current | current | source conflict | missing or invalid |

Freshness effects:

- `fresh` permits high confidence when all other requirements pass;
- `aging` caps confidence at medium;
- `stale` caps confidence at low and adds a visible warning;
- `expired` suppresses any alert that requires that evidence; and
- optional expired components remain `unavailable` without suppressing a
  value alert whose critical expected-selection evidence is still usable.

Compatibility is evaluated separately:

- exact league shape may support high confidence;
- an approved compatible family may support medium confidence;
- a partial format match caps confidence at low; and
- an incompatible format suppresses market and cost claims.

## Deterministic Alert Evaluation

### Evaluation boundary

Alert evaluation is a separate, idempotent write after authoritative draft
state is saved. It does not run inside Phase 3 pick, correction, undo, or Phase
4 CPU transactions.

The request contains:

- exact draft revision;
- exact alert-configuration revision;
- expected current overall pick, when active; and
- the client-visible last evaluation revision.

The backend re-reads authoritative draft and alert state. Stale coordinates
return `409` without changing events.

An evaluation fingerprint includes:

- alert engine and rule versions;
- draft session and revision;
- active-pick snapshot;
- available-candidate identity;
- user roster counts;
- next user pick;
- frozen Personal Board qualifier fields;
- current mock strategy revision, when present;
- alert settings revision;
- evidence snapshot content hash; and
- freshness-policy version.

### Candidate eligibility

A default alert candidate must:

- be available in the draft snapshot;
- have an exact canonical signal mapping;
- satisfy the configured Personal Board qualifier;
- have no active session dismissal;
- have passed any active snooze boundary; and
- have the critical evidence required by the alert kind.

A player added late to the draft may alert only after an explicit mapped signal
is attached. Name-only matching at evaluation time is forbidden.

### Value-over-current-pick range

Given:

- current overall pick `C`;
- expected-selection low `L`; and
- expected-selection high `H`;

the market gap is:

```text
gap_low  = C - H
gap_high = C - L
```

Positive values mean the draft has moved later than the imported window.

The default value trigger requires `gap_low >= 6`. This uses the conservative
edge of the source range. The UI may say:

> Your board is stronger than the imported market window here. That window has
> passed by 8-13 selections.

It may not say:

> This player is a 10-pick steal.

### Return-risk band

Given the next scheduled user pick `N`:

- `likely_to_return` when `L >= N`;
- `unlikely_to_return` when `H < N`;
- `uncertain` when `[L, H]` overlaps `N`; and
- `unavailable` when the window or next user pick is missing.

This is a range comparison, not a probability model. Corrections or undo may
change `N`, availability, and the current band.

### Evidence components

Each component remains separate:

- `personal_conviction`: tier, favorite, and manual-rank facts;
- `dynasty_market`: expected-selection and optional market band;
- `win_now_production`: source-backed band or unavailable;
- `age_risk`: source-backed band or unavailable;
- `strategy_fit`: current Phase 4 roster checkpoint and position fit, or
  unavailable; and
- `return_risk`: expected window relative to next user pick.

The engine does not add these components into a public total score.

`win_now_production` and `age_risk` must expose both supporting and cautionary
language when available. Strategy fit may raise the presentation priority of
an already qualified alert, but cannot make a market-ineligible player alert.

### Alert kinds

V1 supports:

- `value_watch`;
- `return_risk`;
- `trade_up_window`; and
- `evidence_warning`.

One player may have more than one kind. The desktop groups them into one player
alert rather than stacking duplicate cards.

### Confidence

High confidence requires:

- exact canonical mapping;
- fresh critical evidence;
- exact league-format compatibility;
- expected-selection width of 8 picks or fewer; and
- no critical limitation.

Medium confidence requires:

- fresh or aging evidence;
- exact or approved-family format compatibility; and
- expected-selection width of 20 picks or fewer.

All other usable evidence is low confidence. Stale evidence is always low.
Expired or incompatible critical evidence is unavailable and cannot open its
alert kind.

Confidence is displayed as a label with reasons. It is never rendered as a
percentage.

## Trade-Up Reference

### Target pick window

A trade-up window may appear only when:

- the candidate has an open `return_risk` alert;
- the band is `unlikely_to_return`;
- the user's next pick exists;
- at least one unmade pick exists before the user's next pick; and
- alerts are enabled.

The engine intersects the imported expected-selection window with the unmade
picks before the user's next pick, then applies the versioned safety buffer.
The result is rendered as a range of overall picks and round/pick labels.

If the intersection is empty, no trade-up window appears.

### Pick-only cost band

Cost references require a fresh, compatible, monotonic pick-value curve.

The engine:

1. values the user's next current-draft pick as a range;
2. values every target pick in the target window as a range;
3. calculates the incremental range without collapsing endpoints;
4. finds generic pick-only asset classes whose value ranges overlap that
   increment; and
5. returns at most three bounded reference packages, ordered from least to most
   expensive.

Packages:

- contain picks only;
- use generic asset labels;
- never include a player;
- never assume ownership;
- never use an unbounded search;
- never claim fairness or acceptance likelihood; and
- always include source, freshness, confidence, and verification language.

The interface says:

> Reference only: moving into picks 42-45 maps to a future second through a
> future first on the attached pick curve. Verify your assets and league rules.

The interface does not say:

> Offer your 2027 first. This is fair.

## Alert Lifecycle

### Open and update

Evaluation creates an event only when its deterministic key is new. Repeating
the same evaluation returns the existing event.

When the same alert remains valid at a later draft revision:

- its `last_confirmed_revision` advances;
- its current evidence snapshot is replaced;
- its original creation evidence remains audit-readable; and
- the event is not duplicated.

### Supersede

Correction, undo, source replacement, configuration change, player selection,
or changed evidence may invalidate an alert. The next evaluation marks it
`superseded` and records a reason.

Superseded history is read-only.

### Dismiss

Dismissal hides one player alert for the remainder of that draft. It does not
delete the event or change evaluation facts.

### Snooze

The default snooze ends at the earlier of:

- five newly saved picks; or
- the next user turn.

Snooze may be reversed manually. An alert whose underlying risk materially
worsens remains snoozed until the chosen boundary; V1 does not secretly break
the user's suppression choice.

### Disable

Disabling alerts:

- is revision guarded;
- suppresses new presentation;
- preserves configuration and event history;
- changes no draft or mock state; and
- may be reversed.

## Persistence Model

Phase 5 owns these SQLite records.

### `alert_evidence_snapshot`

- identifier;
- schema version;
- source label;
- source kind;
- permitted-use confirmation;
- private source reference;
- format and scoring shape;
- supported draft depth;
- source `as_of`;
- imported timestamp;
- content hash;
- status;
- created timestamp.

### `alert_player_signal`

- identifier;
- evidence snapshot identifier;
- canonical player identifier;
- expected-pick low and high;
- optional market band;
- optional win-now production band;
- optional age-risk band;
- field timestamps;
- limitation codes;
- private source record reference.

Unique on evidence snapshot and canonical player.

### `alert_pick_value_signal`

- identifier;
- evidence snapshot identifier;
- asset key;
- season offset;
- round;
- optional current-draft overall pick;
- value low and high;
- source timestamp;
- limitation codes.

### `draft_alert_configuration`

- identifier;
- draft session identifier;
- evidence snapshot identifier;
- enabled;
- personal qualifier mode;
- eligible tier count;
- minimum conservative gap;
- snooze pick count;
- engine version;
- rule version;
- freshness-policy version;
- revision;
- created and updated timestamps.

### `draft_alert_configuration_revision`

- identifier;
- configuration identifier;
- sequence number;
- previous and next evidence snapshot identifiers;
- previous and next settings snapshots;
- reason;
- created timestamp.

### `draft_alert_evaluation`

- identifier;
- configuration identifier;
- draft revision;
- input fingerprint;
- current overall pick;
- next user pick;
- candidate count;
- opened, updated, and superseded counts;
- limitation codes;
- evaluated timestamp.

Unique on configuration and input fingerprint.

### `draft_alert_event`

- identifier;
- configuration identifier;
- canonical player identifier;
- alert kind;
- status: `open`, `snoozed`, `dismissed`, or `superseded`;
- confidence;
- freshness;
- first and last confirmed draft revisions;
- original and current evidence JSON;
- explanation template keys;
- limitation codes;
- snooze boundary;
- dismissal and supersession timestamps;
- created and updated timestamps.

### `draft_alert_trade_reference`

- identifier;
- event identifier;
- target overall-pick low and high;
- target round/pick labels;
- cost-range JSON;
- pick-curve snapshot identifier;
- explanation template key;
- limitation codes;
- created timestamp.

All configuration, evaluation, event, and trade-reference rows cascade with the
draft session. Evidence snapshots are retained independently so historical
drafts remain explainable.

## API Contract

All state-changing routes require the existing local write guard.

### Evidence imports

- `POST /api/v1/alert-evidence-imports/preview`
  - previews an uploaded local file;
  - performs no active evidence mutation.
- `POST /api/v1/alert-evidence-imports/{preview_id}/commit`
  - requires the preview content hash;
  - commits one immutable evidence snapshot.
- `GET /api/v1/alert-evidence-snapshots`
  - lists bounded metadata without private references or raw rows.
- `GET /api/v1/alert-evidence-snapshots/{snapshot_id}`
  - returns summary, mapping counts, compatibility, freshness, and limitations.

### Draft configuration

- `POST /api/v1/draft-sessions/{session_id}/alert-configuration`
  - attaches one evidence snapshot and settings;
  - requires the current draft revision.
- `PATCH /api/v1/draft-sessions/{session_id}/alert-configuration`
  - enables, disables, changes thresholds, or replaces the snapshot;
  - requires the exact configuration revision and draft revision.
- `GET /api/v1/draft-sessions/{session_id}/alert-configuration`
  - returns safe configuration and current evidence metadata.

### Evaluation and alerts

- `POST /api/v1/draft-sessions/{session_id}/alerts/evaluate`
  - reconciles one exact saved draft revision;
  - returns current grouped alerts plus evaluation metadata.
- `GET /api/v1/draft-sessions/{session_id}/alerts`
  - lists current or historical events with bounded pagination.
- `GET /api/v1/draft-sessions/{session_id}/alerts/{alert_id}`
  - returns the safe evidence explanation and trade reference.
- `PATCH /api/v1/draft-sessions/{session_id}/alerts/{alert_id}`
  - dismisses, snoozes, or reopens one event;
  - requires the exact configuration revision and expected status.

No route selects a player, changes a Phase 4 CPU decision, or executes a trade.

## Desktop Interaction Contract

### Draft setup

An optional `Decision support` section shows:

- attached evidence snapshot;
- format compatibility;
- freshness;
- default threshold summary;
- alerts enabled state; and
- a direct route to preview/import evidence.

Creating a draft never requires Phase 5 evidence.

### Decision-support views

Personal, Position, and Tier views may show a narrow alert rail. The candidate
table does not gain visible market-rank or ADP columns.

Each grouped alert shows:

- player identity;
- personal reason;
- alert kind;
- plain-language market gap or return-risk band;
- optional production, age-risk, and strategy context;
- downside or limitation;
- confidence;
- freshness;
- target pick window and cost availability;
- `Inspect evidence`;
- `Snooze`;
- `Dismiss`; and
- no draft or trade submission button.

### Evidence drawer

The drawer may show:

- snapshot source label;
- source `as_of`;
- format compatibility;
- expected-selection window;
- calculation operands and rule version;
- component bands;
- confidence reasons;
- freshness reasons;
- target and cost ranges;
- limitations; and
- event history.

It excludes private provider references, raw rows, Personal Board notes, and
internal identifiers.

### Blind view

Blind view:

- does not request or render the alert rail;
- shows no alert badge, market count, or hidden signal;
- keeps the Phase 3 Blind candidate response unchanged; and
- may show only a neutral reminder that decision support is unavailable in
  Blind view.

### Keyboard

- `a` focuses the alert rail outside form fields;
- `e` opens evidence for the focused alert;
- `s` opens snooze controls;
- `Escape` closes the evidence drawer;
- no single key dismisses an alert or confirms a pick.

## Correction, Undo, Pause, Reset, and Recovery

### Correction and undo

Draft correction and undo commit first under Phase 3 rules. The subsequent
evaluation:

- recalculates available players and next user pick;
- supersedes alerts no longer valid;
- reopens a previously superseded condition only as a new current evaluation;
- preserves original event evidence; and
- never rewrites pick or CPU audit history.

### Pause

A paused draft may read, dismiss, snooze, reopen, disable, or inspect alerts.
It may evaluate the currently saved revision, but no timer-based behavior runs
in the background.

### Reset

Reset preserves the old draft and its alert history. The replacement draft may
copy the evidence snapshot and settings only through an explicit
`copy_alert_configuration` choice. A copied configuration starts with revision
zero and no copied open/dismissed events.

### Recovery

On restart:

- saved draft state remains authoritative;
- configuration and alert history restore from SQLite;
- the client compares draft and evaluation revisions;
- a missing current evaluation is reconciled idempotently; and
- no network refresh is required.

## Error and Recovery Rules

Required codes include:

- `ALERT_EVIDENCE_INVALID`;
- `ALERT_EVIDENCE_MAPPING_REQUIRED`;
- `ALERT_EVIDENCE_PERMISSION_UNCONFIRMED`;
- `ALERT_EVIDENCE_NOT_FOUND`;
- `ALERT_EVIDENCE_INCOMPATIBLE`;
- `ALERT_EVIDENCE_EXPIRED`;
- `ALERT_PICK_CURVE_INVALID`;
- `ALERT_CONFIGURATION_NOT_FOUND`;
- `ALERT_CONFIGURATION_STALE_REVISION`;
- `ALERT_DRAFT_STALE_REVISION`;
- `ALERT_EVALUATION_STALE`;
- `ALERT_EVENT_NOT_FOUND`;
- `ALERT_EVENT_STALE_STATUS`; and
- `ALERT_EVALUATION_FAILED`.

Errors state:

- what remained unchanged;
- which evidence or revision conflicted; and
- the next safe action.

An alert failure never claims that a draft pick failed when the draft mutation
was already saved.

## Privacy and Logging

- Public fixtures use fictional sources, players, identifiers, and values.
- Raw uploaded files remain local and are not copied into the public
  repository.
- Private source references and provider record IDs remain SQLite-internal.
- Normal responses expose source label and freshness, not raw source records.
- Normal logs use internal snapshot, evaluation, and correlation IDs only.
- Logs exclude player display names, Personal Board notes, raw values, package
  text, and provider identifiers.
- Blind responses contain no alert configuration, event, source, confidence,
  freshness, or market fields.
- Draft CSV export remains unchanged and excludes Phase 5 evidence.
- A future Phase 6 report must define its own safe alert-summary export.

## Limits and Performance

- at most 1,000 player-signal rows per evidence snapshot;
- at most 500 pick-value rows per snapshot;
- at most 500 draft candidates evaluated per revision;
- at most 25 current grouped alerts returned by default;
- at most 3 cost references per player alert;
- bounded pagination for history;
- no unbounded package search;
- no live provider request during evaluation;
- target under 250 milliseconds for a 500-candidate local evaluation; and
- target under 100 milliseconds for cached current-alert reads.

Performance limits are verified on sanitized local fixtures and must not weaken
transaction, privacy, or confidence rules.

## Test Strategy

### Coverage gates

- every documented deterministic rule branch has at least one focused fixture;
- no global line-coverage percentage substitutes for the rule and workflow
  gates below;
- unit tests for every deterministic range, trigger, band, compatibility, and
  freshness rule;
- migration upgrade, downgrade, constraint, uniqueness, and cascade tests;
- import preview, mapping, commit, idempotency, and rollback integration tests;
- configuration, evaluation, lifecycle, recovery, and privacy integration
  tests;
- OpenAPI and generated TypeScript contract checks;
- frontend interaction, accessibility, Blind-view, and stale-state tests;
- a full offline Entropy-shaped workflow audit;
- full backend and frontend regression suites;
- production build; and
- dependency audit.

### Unit tests

- market-gap endpoint math;
- exact-boundary gap threshold;
- all four return-risk bands;
- personal qualifier modes;
- freshness boundaries by evidence type;
- confidence caps;
- format compatibility;
- missing versus neutral component behavior;
- value, return-risk, and warning triggers;
- target-window intersection;
- monotonic pick-curve validation;
- bounded cost-range matching;
- no player assets in packages;
- deterministic fingerprinting;
- idempotent event keys;
- explanation-template completeness; and
- forbidden objective-language scan.

### Persistence tests

- migration round trip;
- immutable evidence snapshots;
- one canonical player per snapshot;
- range constraints;
- history-profile-independent alerts;
- configuration revision uniqueness;
- evaluation fingerprint uniqueness;
- event status constraints;
- evidence retention after draft deletion policy;
- draft-owned cascade; and
- transaction rollback on late failure.

### Integration tests

- preview performs no active mutation;
- ambiguous mappings block those player signals;
- explicit commit and duplicate commit behavior;
- permission confirmation required;
- incompatible format handling;
- attach and replace snapshot;
- evaluate active live and mock drafts;
- exact revision guards;
- correction and undo reconciliation;
- restart catches up a missing evaluation;
- paused, completed, and reset behavior;
- disable, dismiss, snooze, and reopen;
- expired expected-pick evidence suppresses market alerts;
- missing pick curve preserves the player alert with cost unavailable;
- Phase 4 CPU picks remain identical with alerts enabled or disabled;
- normal API responses omit private references;
- Blind candidate response remains structurally unchanged; and
- draft CSV export remains Phase 5-free.

### Frontend tests

- evidence preview warnings and explicit commit;
- optional setup does not block draft creation;
- alert rail appears only in decision-support views;
- Blind view makes no alert request;
- grouped alert and evidence drawer;
- confidence, freshness, downside, and limitation labels;
- unavailable components are not rendered as zero;
- snooze, dismiss, reopen, and disable;
- no pick or trade is sent from an alert control;
- stale guard refreshes authoritative state;
- keyboard commands ignore form fields; and
- accessible focus and status announcements.

### Live workflow audit

- load a synthetic compatible evidence and pick-value snapshot;
- create an Entropy-shaped 10-team, 24-round third-round-reversal mock;
- attach default alert configuration;
- verify alerts do not change same-seed Phase 4 CPU picks;
- trigger a value alert, return-risk alert, and trade-up reference;
- inspect all component, confidence, freshness, and limitation evidence;
- switch to Blind view and verify no alert or market context appears;
- dismiss and snooze separate alerts;
- pivot Phase 4 strategy and verify only later strategy context changes;
- correct and undo CPU and user picks;
- interrupt and restart between draft mutation and alert evaluation;
- reconcile the missed evaluation exactly once;
- disable and re-enable alerts without changing draft state;
- complete the mock offline; and
- inspect history without provider references or private notes.

### Known coverage gaps at specification time

- no approved real market snapshot exists;
- no approved real pick-value curve exists;
- no approved production or age-risk source exists;
- no visual-regression harness is configured; and
- no GitHub Actions workflow currently runs repository checks.

Synthetic fixtures can prove deterministic behavior and privacy boundaries.
They cannot establish real-world predictive accuracy or permission to
redistribute source data.

## Acceptance Tests

1. Previewing evidence changes no active snapshot or draft.
2. Committing requires permitted-use confirmation and the preview hash.
3. Identical content commits idempotently.
4. Ambiguous or unmatched players cannot produce alerts.
5. Invalid or inverted ranges are rejected.
6. Incompatible format evidence cannot produce a market or cost claim.
7. Personal Board order and market evidence remain separate fields.
8. A default market-only candidate does not open a value alert.
9. A personally qualified candidate opens only above the conservative gap
   threshold.
10. Market-gap calculation matches the documented endpoint math.
11. Return-risk bands match the expected window and next user pick.
12. No V1 response contains an availability probability.
13. Missing optional evidence is unavailable, not zero or neutral.
14. Freshness boundaries and confidence caps match the documented policy.
15. Expired critical evidence suppresses only the dependent alert kind.
16. Identical inputs and versions reproduce identical alerts.
17. Repeating one evaluation creates no duplicate event.
18. A failed evaluation changes no draft pick or mock decision.
19. Restart reconciles a saved draft revision exactly once.
20. Correction and undo supersede invalid alerts without deleting history.
21. Phase 4 CPU picks are identical with alerts enabled and disabled.
22. Strategy fit affects explanation priority only after market eligibility.
23. Value alerts never use objective `steal`, `must draft`, or `best pick`
    language.
24. Win-now and age-risk evidence includes limitations and downside.
25. A trade-up window never extends beyond the next user pick.
26. Missing, expired, or incompatible pick curves show cost unavailable.
27. Every cost reference contains picks only and no ownership claim.
28. No alert control submits a pick or trade.
29. Disabling alerts changes no draft, pick, CPU decision, or event history.
30. Snooze ends at the documented saved-pick or user-turn boundary.
31. Dismissed and snoozed alerts can be reopened.
32. Blind candidate responses remain structurally Phase 5-free.
33. Blind UI requests and renders no alert evidence.
34. Normal logs and responses exclude private source references, raw rows,
    provider IDs, and Personal Board notes.
35. Draft CSV export remains Phase 5-free.
36. A full Entropy-shaped mock completes offline within the performance limits.

## Exit Criteria

Phase 5 is complete when:

- the four product-gate decisions are approved;
- a synthetic and a user-supplied local evidence snapshot can be previewed,
  mapped, committed, and attached;
- value and return-risk alerts are deterministic and traceable;
- every alert separates personal, market, strategy, production, and age-risk
  evidence;
- missing or stale data visibly reduces the claim;
- no visible composite objective-value score exists;
- trade-up output is pick-only, ranged, and manually actionable;
- alerts can be disabled, dismissed, snoozed, and reopened;
- Blind view remains context-free;
- draft writes remain independent and recoverable;
- the full Entropy-shaped offline workflow passes; and
- full backend, frontend, migration, contract, privacy, build, and dependency
  checks pass.

## Recommended Implementation Order

1. Approve the four product-gate decisions.
2. Approve the evidence schema, synthetic fixture, mapping, and freshness
   policy.
3. Add deterministic gap, return-risk, confidence, target-window, and cost-band
   unit fixtures.
4. Add evidence, configuration, evaluation, event, and trade-reference
   persistence.
5. Add preview and explicit-commit evidence import APIs.
6. Add draft configuration and frozen evidence attachment.
7. Add idempotent evaluation and safe alert-read APIs.
8. Add disable, dismiss, snooze, reopen, correction, undo, reset, and recovery
   integration.
9. Add the desktop decision-support rail and evidence drawer.
10. Run specification audit, fix critical gaps, and complete the offline live
    workflow audit.

Each implementation step receives its own bounded contract, tests, audit, and
reviewable commit before the next step begins.

The bounded contract for implementation step 2 is recorded in
[Phase 5 Evidence Import and Freshness Contract](phase-5-evidence-contract.md).

## Deferred Revisit

- direct authenticated market-provider refresh;
- approved redistribution of real provider datasets;
- multiple-source consensus and disagreement analysis;
- calibrated availability probabilities;
- traded-pick ownership;
- exact league-specific offer optimization;
- player-plus-pick trade calculation;
- auction and keeper values;
- injury, contract, news, scouting, or film inputs;
- push notifications;
- Phase 6 post-draft use of alert history; and
- season-long alerts.
