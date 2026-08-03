# Project Roadmap

## North Star

The Friendly Neighborhood Fantasy Hub is a local-first fantasy football intelligence platform. Its purpose is not to give users a magic answer; it is to help them understand player value, uncertainty, roster construction, market behavior, and their own convictions well enough to make better decisions.

The first product milestone is a dependable draft-night companion. Later releases extend that same transparent decision-support philosophy into the season, the league, and the broader dynasty market.

## Roadmap Rules

Every feature should:

- help the user make or learn from a real decision;
- preserve manual control and overrides;
- explain its inputs, confidence, and tradeoffs;
- work from normalized, timestamped data;
- degrade safely when a source is stale or unavailable; and
- avoid presenting ADP, rankings, or calculator values as objective truth.

---

## Full Product Roadmap

### V1 — Draft Lab

**Outcome:** Users can build a personal board, practice multiple draft strategies, operate a reliable live draft room, and receive explainable alerts without being anchored to visible ADP.

Core capabilities:

- player universe and identity normalization;
- league and scoring configuration;
- personal rankings, tiers, notes, and imports/exports;
- Gut ELO pairwise comparisons;
- blind, alphabetical, positional, tier, and personal-board views;
- mock drafts with league-specific draft order;
- simple manager tendency profiles where reliable history exists;
- strategy-guided drafting;
- dynamic value-over-pick alerts;
- “your guy may not return” and pick-only trade-up guidance;
- complete draft controls: mark drafted, undo, pause, resume, reset, and recover;
- post-draft roster report; and
- source timestamps, confidence labels, and transparent explanations.

### V2 — Season Companion

**Outcome:** Users can evaluate their roster and possible trades throughout the season without relying on a single market number.

Planned capabilities:

- roster strength, age curve, depth, liquidity, and fragility views;
- trade-builder workspace;
- trade value ranges using multiple permitted sources;
- comparison of league behavior with market baselines;
- Sleeper transaction-history import;
- manager profiles based on league-specific actions;
- dynasty portfolio and future-pick tracking; and
- saved scenarios and decision notes.

Explicitly deferred until this phase:

- player-plus-pick trade calculation;
- ongoing roster management;
- trade-partner targeting; and
- season-long alerts.

### V3 — League Intelligence

**Outcome:** The Hub models how this specific league behaves, making local tendencies useful without pretending the sample is larger than it is.

Planned capabilities:

- drafting tendencies by manager;
- positional, age, and rookie preferences;
- pick-valuation and negotiation tendencies;
- trading frequency and roster-construction patterns;
- league-market gap analysis;
- opponent profiles for mock drafts; and
- confidence based on sample size and data recency.

### V4 — Market Intelligence

**Outcome:** Users can understand where personal and league beliefs differ from the broader dynasty market.

Planned capabilities:

- comparison across permitted market, ranking, and transaction-derived sources;
- value ranges rather than single-source verdicts;
- historical outcome backtesting;
- market movement and disagreement views;
- league-versus-market player and asset premiums; and
- clear source provenance, timestamps, and terms-of-use compliance.

### Later Exploration — Waiver and Opportunity Lab

This is deliberately not promised for V1–V4. Research should first determine whether the data is reliable enough to create useful recommendations.

Potential model:

> Net add value = free-agent value − drop-candidate value, adjusted for roster need, role opportunity, and schedule.

Possible inputs include usage changes, opportunity data, league availability, replacement level, and the cost of the corresponding roster move.

---

## V1 Detailed Roadmap

### V1 Scope Boundary

V1 is a **draft preparation and draft-night tool**. It is not a complete fantasy platform.

In scope:

- dynasty startup as the primary format;
- Superflex and configurable TE premium;
- redraft-compatible foundations where they do not delay dynasty work;
- a curated pool of roster-relevant players and rookies;
- manual and imported personal rankings;
- mock and live draft workflows; and
- pick-only trade-up decision support.

Out of scope:

- waiver recommendations;
- lineup optimization;
- weekly projections;
- full trade calculation involving players;
- global transaction scraping;
- automated drafting;
- generative-AI decisions; and
- required cloud infrastructure.

### Phase 0 — Foundation and Decisions

**Goal:** Establish a stable project skeleton before analytical features are added.

Deliverables:

- architecture decision: interface framework and local database;
- application configuration model;
- league/scoring settings schema;
- data-source registry with source and refresh timestamps;
- error and logging conventions;
- backup/export format; and
- a small representative test dataset.

Exit criteria:

- the app launches locally;
- configuration survives a restart;
- sample data loads without network access; and
- errors are understandable to a non-technical user.

### Phase 1 — Player Universe and Data Normalization

**Goal:** Create the trusted identity layer every later module depends on.

Deliverables:

- normalized player record and canonical internal ID;
- Sleeper ID and supported external-ID mappings;
- name, suffix, team, position, status, and rookie-class normalization;
- relevant-player-pool rules;
- conflict and unmatched-player review screen/report;
- manual correction support; and
- CSV import/export.

Suggested initial player-pool policy:

- players currently rostered in the target league;
- players inside a configurable market-relevance cutoff;
- all current rookies likely to be drafted or taxi eligible;
- manually added players; and
- no requirement to rank the entire Sleeper player database.

Exit criteria:

- repeat imports do not create duplicates;
- ambiguous matches are never silently accepted;
- manual corrections persist;
- inactive and irrelevant players can be filtered; and
- all downstream modules reference the canonical internal ID.

### Phase 2 — Personal Board, Tiers, and Gut ELO

**Goal:** Turn the user's evaluations into structured, editable draft data.

Deliverables:

- personal ranking board;
- tiers, notes, favorites, and manual ordering;
- pairwise Gut ELO comparisons;
- comparison queues by position, tier, and uncertainty;
- skip, undo, and “not enough information” controls;
- separate rookie and veteran workflows;
- convergence/progress indicator; and
- import/export of the completed board.

Rules:

- Gut ELO is a sorting aid, not a claim of objective player quality.
- Manual ordering always overrides calculated order.
- A user should never be forced to compare hundreds of irrelevant players.

Exit criteria:

- a user can create a useful board in a realistic session;
- interrupted comparison sessions can resume;
- repeated results are deterministic;
- manual edits are preserved; and
- the board exports in a human-readable format.

### Phase 3 — Draft Room and Draft State

**Goal:** Make the app trustworthy enough to operate during a real draft.

Deliverables:

- configurable teams, rounds, order, and third-round-reversal support;
- snake and linear draft handling;
- alphabetical, personal, positional, and tier views;
- drafted-player removal;
- mark drafted, correct pick, undo, pause, resume, and reset;
- current pick and picks-until-user display;
- keyboard-friendly fast entry;
- autosave and crash recovery;
- mock/live mode distinction; and
- draft-state export.

Exit criteria:

- every state-changing action can be corrected;
- a restart restores the latest draft state;
- no completed pick is lost in normal use;
- the board remains responsive with the full relevant player pool; and
- ADP can remain hidden throughout the workflow.

### Phase 4 — Mock Draft Engine and Strategy Lab

**Status:** Complete as of 2026-07-28. See the
[Phase 4 live workflow audit](docs/audits/phase-4-live-workflow-audit.md).

**V1.0.2 correction:** New mocks use a frozen, provenance-tracked dynasty
Superflex expert-consensus baseline for CPU valuation. This supersedes the
alphabetical unranked-player fallback as CPU strategy while leaving the user's
Personal Board authoritative. See the
[market-board corrective specification](docs/specs/v1.0.2-market-board-mock-cpu.md).

**Goal:** Let users practice roster-building philosophies and learn when to pivot.

Initial strategy guides:

- balanced;
- win now;
- productive struggle;
- hero RB;
- robust RB;
- wide-receiver heavy; and
- early quarterback for Superflex.

Deliverables:

- selectable strategy for each mock;
- simple CPU manager archetypes as fallback;
- league-manager profiles only when sufficient draft history exists;
- contextual nudges rather than locked selections;
- roster-construction checkpoints;
- off-plan-but-viable explanations;
- adjustable randomness; and
- mock history that only affects learned local signals when the user opts in.

Exit criteria:

- identical settings and random seed reproduce a mock;
- no strategy forces a player selection;
- the user can pivot strategies mid-draft;
- manager-history confidence is visible; and
- mocks can be excluded from learned tendencies.

### Phase 5 — Value and Trade-Up Alerts

**Status:** Complete as of 2026-07-29. See the
[Phase 5 specification](docs/specs/phase-5-value-trade-up-alerts.md) and the
[Phase 5 live workflow audit](docs/audits/phase-5-live-workflow-audit.md).

**Goal:** Surface decision points without exposing ADP as the primary interface.

Deliverables:

- dynamic value-over-current-pick signal;
- win-now production, dynasty market, age-risk, and strategy-fit components;
- “your guy may not return” risk alert;
- configurable alert thresholds;
- pick-only trade-up range;
- explanation of why an alert appeared;
- confidence and data-freshness labels; and
- dismissal/snooze controls.

Alert example:

> A player in your top tier is still available. Based on the hidden market range and the teams selecting before your next pick, he is unlikely to return. Consider moving up 4–7 spots; the estimated pick-only cost is shown as a range.

Guardrails:

- never label a player an objective “steal”;
- never show false precision;
- distinguish personal conviction from market evidence;
- show downside and age-related risk; and
- require manual confirmation for every real-world trade.

Exit criteria:

- each alert is traceable to its inputs;
- stale or missing market data lowers confidence rather than breaking the draft;
- alerts can be disabled;
- pick ranges respect the configured draft format; and
- no player-plus-pick calculator is implied.

### Phase 6 — Post-Draft Report

**Status:** Complete as of 2026-08-03. See the
[Phase 6 Post-Draft Report specification](docs/specs/phase-6-post-draft-report.md)
and the
[Phase 6 live workflow and specification audit](docs/audits/phase-6-live-workflow-audit.md).

**Goal:** Turn each completed mock or live draft into a learning artifact.

Deliverables:

- position inventory and deterministic starter coverage;
- optional year-one production, dynasty-market, and age-risk context when
  approved evidence supports it;
- visible unavailable states for long-term value, liquidity, and player
  fragility where V1 has no approved evidence;
- descriptive roster concentration observations without a quality verdict;
- strategy adherence and pivots;
- important passed-player and trade-up moments; and
- report export.

Exit criteria:

- every section includes a plain-language explanation and evidence limits;
- the report preserves observation without inventing a recommendation or grade;
- the user can compare two to four compatible saved outcomes; and
- report generation, read, comparison, and standalone export work fully
  offline from saved draft data.

### Phase 7 — Draft-Night Hardening

**Goal:** Stabilize rather than expand.

**Frozen V1 contract:**
[Phase 7 V1 Draft-Night Hardening Specification](docs/specs/phase-7-v1-hardening.md)

Checklist:

- [x] freeze non-critical features;
- [x] test with the actual league settings and pick order;
- [x] rehearse a full-speed mock;
- [x] verify autosave, recovery, undo, and export;
- [x] refresh and timestamp source data;
- [x] prepare a no-network fallback;
- [x] verify readable display at the intended screen size;
- [x] remove or hide unfinished controls; and
- [x] package simple launch and recovery instructions.

Release gate:

- [x] no known data-loss bug;
- [x] no blocker in the core pick workflow;
- [x] the app can complete a full mock without external services;
- [x] all critical controls are understandable without developer help; and
- [x] a backup board and draft-state export are available.

Completion evidence:
[Phase 7 V1 Release Audit](docs/audits/phase-7-v1-release-audit.md)

---

## Recommended Build Order

1. Player universe and ID normalization
2. Personal board and data import/export
3. Gut ELO
4. Draft state and blind board
5. Mock engine
6. Strategy guidance
7. Value and trade-up alerts
8. Post-draft report
9. Draft-night hardening

Each module should be handled as a short production cycle:

1. Write the module specification.
2. Define inputs, outputs, schema, edge cases, and acceptance tests.
3. Build only that module.
4. Audit the result against the specification.
5. Fix critical gaps.
6. Move to the next module.

## V1 Success Measures

V1 succeeds when a user can:

- create and export a personal board;
- express real preferences through Gut ELO without ranking an irrelevant player universe;
- complete and recover a mock draft;
- draft without visible ADP;
- understand every strategy or value alert;
- identify when a personally valued player is at risk;
- evaluate a pick-only move-up range;
- compare completed roster constructions; and
- use the app confidently on draft night.
