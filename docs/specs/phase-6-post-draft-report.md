# Phase 6 Post-Draft Report Specification

**Status:** Approved for bounded implementation

**Phase:** 6

**Specification date:** 2026-07-29

**Product-gate approval date:** 2026-07-29

**Engineering authorization:** Proceed one bounded implementation step at a
time, beginning with the approved report definitions and expected-fixture
contract

## Purpose

Phase 6 turns a completed mock or live draft into a durable learning artifact.
The report explains what the saved roster contains, how it relates to the
configured league and practice strategy, which important decision moments were
recorded, and where the available evidence cannot support a stronger claim.

The report is not a draft grade, a projection, or a declaration that one roster
is objectively better than another. It is closer to a postgame film review:
the sequence is preserved, the important decisions are easy to revisit, and
the evidence is separated from the coach's future judgment.

## Product-Gate Decisions

Engineering begins only after all four decisions are approved.

### Decision 1: Evidence ledger, not report card

**Approved decision:** Approved on 2026-07-29.

V1 has no overall grade, championship probability, roster-value total, or
single composite score. Each section reports:

- `supported`, `limited`, `unavailable`, or `not_applicable`;
- `high`, `medium`, `low`, or `unavailable` evidence confidence;
- exact observed counts or ranges when supported;
- reason and limitation codes; and
- a plain-language explanation.

Why:

- a single grade would collapse personal conviction, roster construction,
  strategy, and optional market evidence into a false objective answer;
- the current player universe does not contain approved projections, contracts,
  injuries, or outcome models; and
- the product should teach the user's process rather than imitate a television
  draft-grade segment.

Trade-off:

- the report is less instantly shareable as a letter grade;
- the user receives a more honest and inspectable learning artifact.

Rejected alternatives:

- an overall `A–F` grade;
- a `0–100` roster score;
- a hidden weighted composite rendered only as a label; and
- an AI-written verdict.

### Decision 2: Completed-only, immutable snapshots

**Approved decision:** Approved on 2026-07-29.

A report may be generated only from a completed live or mock draft. It is an
immutable snapshot tied to:

- the completed draft revision;
- the frozen draft candidate and pick history;
- the frozen league-shape input;
- the applicable Phase 4 mock history, when present;
- the applicable Phase 5 configuration, evidence, and event history, when
  present; and
- versioned report rules.

Identical inputs produce the same report. Repeated generation returns the same
saved report idempotently. A reset or replay is a different draft and therefore
receives a different report.

Why:

- incomplete report cards would compete with the live draft room;
- immutability preserves what the user actually reviewed;
- the report can be opened after restart without recalculating against changed
  board or source data; and
- saved comparisons remain reproducible.

Trade-off:

- the user cannot preview a speculative final roster;
- Phase 4 and Phase 5 already provide in-draft decision support.

Rejected alternatives:

- continuously changing report previews during a draft;
- rewriting an old report after a reset;
- using the user's current Personal Board instead of the draft snapshot; and
- recalculating evidence freshness every time an old report is opened.

### Decision 3: Core report plus optional evidence enrichment

**Approved decision:** Approved on 2026-07-29.

Every completed draft can produce a useful core report from local saved state.
Optional Phase 5 evidence enriches only the sections its frozen fields support.

Core supported observations:

- draft and roster summary;
- position counts;
- deterministic starter-slot coverage;
- bench/depth counts after starter assignment;
- positional concentration and investment timing;
- Personal Board decision moments;
- mock strategy revisions and saved guidance, for mocks; and
- recorded alert moments, when alerts were configured.

Optional Phase 5 enrichment:

- categorical win-now production profile;
- categorical age-risk profile;
- saved dynasty-market context;
- recorded value, return-risk, and trade-up moments; and
- source label, compatibility, freshness-at-completion, and limitations.

Explicitly unavailable without a separately approved source:

- projected points or wins;
- average player age;
- career longevity;
- long-term dynasty outcome value;
- trade liquidity;
- injury or contract fragility;
- championship probability;
- exact resale value; and
- future availability probability.

Why:

- the report remains useful fully offline with only core draft data;
- optional local evidence may add context without becoming mandatory;
- missing data becomes visible rather than silently guessed; and
- a market band is not relabeled as liquidity or long-term outcome value.

Trade-off:

- several roadmap sections may visibly say `unavailable` in the initial V1
  report;
- those honest placeholders define the exact evidence needed for later
  enrichment.

Rejected alternatives:

- inferring age from rookie status, name, team, or notes;
- treating Personal Board rank as production or market value;
- treating a market band as liquidity;
- treating rookie count as long-term success; and
- hiding unsupported sections entirely.

### Decision 4: Safe decision moments, compatible comparisons, HTML export

**Approved decision:** Approved on 2026-07-29.

V1 reports:

- bounded Personal Board choice moments;
- recorded Phase 4 pivots and guidance;
- recorded Phase 5 alert and trade-up moments;
- comparisons of two to four compatible saved reports; and
- a standalone, print-friendly HTML export.

Moment language remains observational:

> At pick 7, you selected Player A while Player B was five places higher on
> your saved Personal Board.

It never says:

> You made the wrong pick.

Comparisons show section deltas without declaring a winner. HTML export contains
no external scripts, fonts, images, or network calls. PDF generation, social
sharing, and private reflection notes are deferred.

Why:

- the report should help the user revisit actual decisions;
- recorded events are safer than reconstructed hindsight narratives;
- compatible side-by-side reports satisfy the roadmap comparison outcome; and
- standalone HTML is readable, printable, portable, and fully offline.

Trade-off:

- the first export is not a one-click PDF;
- HTML avoids adding a rendering dependency before Phase 7 packaging.

Rejected alternatives:

- an automatically ranked leaderboard of drafts;
- retrospective alerts that did not exist during the draft;
- including raw Personal Board notes or private source references;
- a cloud-hosted share link; and
- PDF as the first report format.

## Goals

Phase 6 must:

1. create a durable learning artifact from a completed live or mock draft;
2. explain every displayed metric and qualitative band;
3. distinguish direct observation, optional evidence context, and
   recommendation;
4. preserve missing and limited evidence states;
5. support compatible comparison of saved reports;
6. export a safe standalone report;
7. remain deterministic, recoverable, private, and fully offline; and
8. change no draft, pick, mock, alert, board, or source record.

## Non-Goals

Phase 6 does not add:

- overall roster grades;
- projections, simulations, or championship odds;
- lineup optimization;
- weekly or in-season advice;
- waiver recommendations;
- player-plus-pick trade calculation;
- trade-partner targeting;
- direct provider refresh;
- new market, age, injury, contract, or liquidity providers;
- retrospective alerts invented after the draft;
- generative-AI analysis;
- cloud storage or share links;
- PDF generation;
- editable report notes;
- report-driven learning or ranking changes; or
- automatic picks, trades, or roster moves.

## Roadmap Traceability

| Phase 6 roadmap promise | V1 contract |
| --- | --- |
| position and starter coverage | Deterministic roster counts and maximum starter-slot assignment |
| year-one strength | Optional categorical production profile; unavailable without adequate approved coverage |
| long-term dynasty value | Explicitly unavailable until an approved long-term evidence field exists |
| age profile | Optional categorical age-risk distribution; never fabricated average age |
| liquidity | Explicitly unavailable until dedicated liquidity evidence exists |
| fragility and concentration risk | Supported roster-construction concentration; injury/contract fragility unavailable |
| strategy adherence and pivots | Saved Phase 4 revisions and guidance-event summary for mocks |
| passed-player moments | Bounded reconstruction from the frozen Personal Board and pick sequence |
| trade-up moments | Only saved Phase 5 trade-up events and pick-only references |
| report export | Standalone offline HTML |
| compare mock outcomes | Two-to-four report comparison under compatibility rules |

## Terminology

- **Report:** An immutable saved artifact derived from one completed draft.
- **Core observation:** A result derived only from authoritative saved draft,
  league, board-snapshot, mock, or alert state.
- **Evidence enrichment:** Optional source-backed categorical context frozen
  with the draft's Phase 5 configuration.
- **Section availability:** `supported`, `limited`, `unavailable`, or
  `not_applicable`. The last state means the section does not apply to this
  draft mode, not that evidence was lost.
- **Evidence confidence:** `high`, `medium`, `low`, or `unavailable`; this
  describes input completeness, not predictive accuracy.
- **Starter assignment:** A deterministic maximum assignment of drafted
  players to configured starter slots.
- **Depth count:** Drafted players left at a position after starter assignment.
- **Concentration:** The share or timing of roster investment in one position.
- **Player fragility:** Injury, contract, or role risk; unsupported in V1.
- **Decision moment:** A bounded saved or reconstructable event at a user
  decision point.
- **Compatible reports:** Reports with the same report rule version and
  equivalent normalized league shape.
- **Safe summary:** A response or export that excludes raw uploads, provider
  identifiers, private notes, and internal references.

## Authoritative Inputs

### Required

- one completed `draft_session`;
- all active completed `draft_pick` rows;
- the session's frozen `draft_candidate` snapshot;
- draft teams, user slot, format, rounds, and third-round-reversal setting;
- the saved league profile and its normalized league-shape fingerprint; and
- the report engine and explanation-template versions.

### Mock-only

- `mock_configuration`;
- `mock_strategy_revision`;
- saved `mock_guidance_event` rows; and
- the active/historical status needed to distinguish corrected CPU decisions.

CPU random audit, seed, manager internal references, and private pivot notes are
not report inputs.

### Alert-enriched

- `draft_alert_configuration` revision frozen at completion;
- attached evidence snapshot id and safe metadata;
- saved alert evaluations and event history through the completed revision;
- safe trade-up reference fields; and
- evidence freshness evaluated at `draft.completed_at`.

Raw upload text, provider row keys, private source references, Personal Board
notes, and dismissed-event private context are not report inputs.

### Explicitly prohibited inputs

- current Personal Board order after the draft;
- current source snapshots not attached to the draft;
- player names as a proxy for talent, age, role, or production;
- private notes;
- CPU randomness as a roster-quality signal;
- mock learning-consent state as a report score;
- internet data fetched at generation time; and
- generative model output.

## Input Freeze and Fingerprinting

Report generation constructs a canonical input document containing:

- draft id and completed revision;
- ordered active picks;
- frozen candidate fields used by the report;
- normalized league shape;
- safe mock strategy/guidance inputs;
- safe alert event/evidence inputs;
- draft completion timestamp;
- report engine version;
- report rules version; and
- explanation-template version.

The canonical document:

- sorts map keys lexicographically;
- sorts picks by overall pick;
- sorts strategy revisions and events by their saved sequence;
- uses explicit `null` for missing optional fields;
- normalizes timestamps to UTC;
- excludes generated report id and generation time; and
- hashes as SHA-256 UTF-8 canonical JSON.

`input_fingerprint` is SQLite-internal. Repeated generation with the same
fingerprint returns the existing report. Freshness is evaluated relative to the
saved draft completion time so opening the same report later cannot change it.

## Report Availability

### Eligible

- completed live draft;
- completed mock draft;
- exact active pick count equals `team_count * round_count`;
- every active pick has one canonical player;
- league shape can be normalized; and
- the supported report engine version is available.

### Ineligible

- active or paused draft;
- reset source whose status is not completed;
- draft with a missing active pick;
- draft with duplicate active player assignments;
- missing or invalid league profile;
- unsupported report version; or
- corrupted revision history.

An ineligible request fails without changing any source state.

## Report Sections

Every section has:

- stable `section_key`;
- display title;
- availability;
- confidence;
- structured metrics;
- reason codes;
- limitation codes;
- explanation-template key;
- rendered plain-language explanation; and
- safe provenance summary when external evidence contributed.

### 1. Draft summary

Always includes:

- draft name and mode;
- completed time;
- team count and rounds;
- draft format and third-round reversal;
- user slot;
- total user picks;
- configured starter and bench shape;
- report versions; and
- whether mock, alert, and evidence context were available.

It excludes seed, randomness, private notes, provider identifiers, and internal
manager references.

### 2. Position inventory

For the user's completed roster:

- count by canonical fantasy position;
- list of players with selected overall pick and position;
- first and last investment pick by position;
- early, middle, and late pick counts using the Phase 4 window boundaries; and
- rookie count as identity context only.

Rookie count never becomes a dynasty-value or timeline score.

### 3. Starter coverage

Starter coverage uses the frozen eligible fantasy positions and normalized
league starter slots.

Algorithm:

1. expand each configured starter slot into one assignment target;
2. build candidate-to-slot edges from frozen fantasy-position eligibility;
3. find the maximum number of filled starter slots;
4. among maximum assignments, prefer the lexicographically smallest tuple of
   `(slot_order, overall_pick, canonical_player_id)`;
5. calculate filled, unfilled, and ambiguous-flex counts; and
6. leave unmatched drafted players in depth inventory.

Outputs:

- `starter_slots_total`;
- `starter_slots_filled`;
- `starter_coverage_ratio`;
- filled slot labels;
- unfilled slot labels;
- flex assignments;
- depth counts by position; and
- limitations for unknown or unsupported position eligibility.

This is roster coverage, not a starting-lineup recommendation.

### 4. Roster-construction concentration

Supported observations:

- share of user picks by position;
- share before the middle-window boundary;
- maximum single-position share;
- starter-position gaps;
- surplus after starter assignment;
- early-round concentration; and
- position groups with zero depth after starter assignment.

Versioned V1 context bands:

- `balanced_distribution`: no position exceeds `40%` of user picks and every
  distinct starter position is covered;
- `concentrated`: one position exceeds `40%` but not `55%`;
- `highly_concentrated`: one position exceeds `55%`;
- `coverage_gap`: at least one configured distinct starter position is
  unfilled; and
- `unavailable`: league starter shape cannot be normalized.

Multiple bands may coexist. They describe construction only and never say the
roster is good or bad.

Player fragility remains a separate `unavailable` sub-section with
`PLAYER_FRAGILITY_EVIDENCE_UNAVAILABLE`.

### 5. Year-one production profile

Available only from attached compatible Phase 5 `win_now_production_band`
evidence.

Coverage:

- `supported`: at least `80%` of user roster players have a usable band;
- `limited`: at least `50%` and below `80%`;
- `unavailable`: below `50%`, incompatible, invalid, or expired at completion.

Outputs:

- covered and uncovered player counts;
- distribution of source-defined bands;
- source label and as-of timestamp;
- freshness at completion;
- compatibility; and
- limitations.

Confidence is capped at `medium` because the V1 field is a categorical
single-source input and not a projection.

The section is called `Year-one production context`, not `Projected strength`.

### 6. Dynasty market context

Available only from attached compatible Phase 5 market bands.

Coverage thresholds match the production section: below `50%` is unavailable,
at least `50%` and below `80%` is limited, and at least `80%` is supported.
Confidence is capped at `medium` because this is categorical single-source
context rather than a roster-value model.

Outputs:

- covered and uncovered player counts;
- source-defined band distribution;
- expected-selection context compared with actual selected pick, where both
  existed at draft time;
- source freshness and compatibility; and
- limitations.

It does not:

- sum bands into a roster value;
- call a player liquid;
- predict appreciation;
- claim long-term outcome quality; or
- compare against unattached current market data.

The roadmap's `long-term dynasty value` remains visibly unavailable with
`LONG_TERM_VALUE_EVIDENCE_UNAVAILABLE`.

### 7. Age-risk profile

Available only from attached compatible Phase 5 `age_risk_band` evidence.

Coverage thresholds match the production section. Outputs are band
distributions and missing-player counts.

It does not calculate:

- average age;
- age by position;
- career horizon;
- contract runway; or
- decline probability.

If no adequate evidence exists, the section renders:

> Age profile unavailable. The saved draft does not contain approved age
> evidence, so the Hub will not infer age from rookie status, name, or team.

### 8. Liquidity

V1 always reports `unavailable` with:

- `LIQUIDITY_EVIDENCE_UNAVAILABLE`; and
- a plain-language description of the dedicated market-depth or transaction
  evidence required.

A Phase 5 market band is not liquidity evidence.

### 9. Strategy story

Mock only.

Uses saved Phase 4 strategy revisions and guidance events. Outputs:

- initial strategy;
- ordered pivots and their effective picks;
- count of `on_plan`, `watch`, `off_plan_viable`, `risk_checkpoint`, and
  `insufficient_evidence` events;
- final position counts;
- saved target ranges and observed counts;
- acknowledged or dismissed status as interaction history; and
- limitations inherited from each event.

No percentage adherence score is created. A pivot is not treated as failure.
Only events actually saved during the mock appear.

Live drafts render `not_applicable`, not `unavailable`.

### 10. Personal Board choice moments

The engine reconstructs candidate availability before each user pick from the
frozen candidate snapshot and ordered active picks.

A candidate moment is created when the selected player was below the
highest-ranked available player on the frozen Personal Board and at least one
of these is true:

- the rank delta is `5` or more;
- the passed player was a saved favorite; or
- the passed player was in a better saved tier.

The report keeps at most `10` moments, sorted by:

1. favorite passed;
2. tier difference descending;
3. rank delta descending; and
4. user pick ascending.

Repeated passing on the same player is collapsed to the earliest qualifying
moment, with the last pick at which the player remained available recorded
separately.

Moment output includes:

- user overall pick;
- selected player display name, position, and saved Personal Board rank;
- passed player display name, position, rank, tier, and favorite flag;
- rank delta;
- whether and when the passed player was later drafted; and
- `PERSONAL_BOARD_OBSERVATION_ONLY`.

It excludes Personal Board notes and does not call the choice a mistake.

### 11. Recorded alert moments

Availability states:

- `not_configured`;
- `disabled_at_completion`;
- `configured_no_events`;
- `available`; or
- `unavailable_due_to_corruption`.

Only saved Phase 5 events appear. The report may include:

- value-watch event;
- return-risk event;
- trade-up-window event;
- event status history;
- event draft revision;
- safe evidence summary;
- target pick window;
- ranged pick-only references;
- whether the player was later drafted by the user, another slot, or not
  drafted; and
- limitations.

The report must not:

- create a new alert retrospectively;
- claim an event caused a pick;
- claim the user executed a trade;
- expose ownership not saved by the draft;
- include player-plus-pick packages;
- expose private source references or raw rows; or
- label a passed player an objective steal or mistake.

At most `20` alert events appear in the exported report. Ordering is by saved
event revision, event kind, and canonical event id. The UI may page the full
safe history.

### 12. Evidence limits

Every report ends with a limits section that:

- lists unavailable and limited sections;
- identifies missing evidence categories;
- distinguishes source freshness from predictive confidence;
- states that the report does not project outcomes;
- states that user judgment remains authoritative; and
- names the frozen report versions.

## Recommendation Boundary

Phase 6 may recommend a learning action, not a player or transaction.

Allowed:

- review an unfilled starter slot;
- compare two roster constructions;
- revisit a saved decision moment;
- inspect why a section is limited; and
- run another mock with a different strategy.

Prohibited:

- draft, drop, trade, start, or acquire a named player;
- declare a winning draft;
- say a roster will contend or rebuild successfully;
- claim a choice was correct or incorrect;
- prescribe a player-plus-pick offer; and
- turn a report observation into automated action.

## Persistence Model

### `post_draft_report`

- `id`
- `draft_session_id`
- `draft_revision`
- `input_fingerprint`
- `league_shape_fingerprint`
- `report_engine_version`
- `report_rules_version`
- `explanation_template_version`
- `draft_mode`
- `generated_at`
- `completed_at`
- `section_summary_json`
- `limitation_codes_json`

Constraints:

- one report per `(draft_session_id, input_fingerprint)`;
- fingerprints are 64-character lowercase SHA-256;
- source draft must be completed;
- revisions are non-negative;
- modes are `live` or `mock`; and
- version fields are non-empty.

### `post_draft_report_player`

- `id`
- `report_id`
- `player_id`
- `overall_pick`
- `round_number`
- `primary_position`
- `fantasy_positions_json`
- `starter_assignment`
- `saved_personal_rank`
- `saved_tier_order`
- `saved_favorite`
- `safe_evidence_json`

Constraints:

- one row per report and player;
- one row per report and overall pick;
- safe evidence contains normalized report fields only; and
- Personal Board notes and source record keys are prohibited.

### `post_draft_report_section`

- `id`
- `report_id`
- `section_key`
- `availability`
- `confidence`
- `metrics_json`
- `reason_codes_json`
- `limitation_codes_json`
- `explanation_template_key`
- `explanation`
- `safe_provenance_json`

Constraints:

- one row per report and section key;
- availability and confidence use approved enums;
- metrics are schema-validated before persistence; and
- explanation is generated from a versioned template, not free-form AI.

### `post_draft_report_moment`

- `id`
- `report_id`
- `moment_key`
- `moment_kind`
- `overall_pick`
- `primary_player_id`
- `secondary_player_id`
- `safe_summary_json`
- `reason_codes_json`
- `limitation_codes_json`

Constraints:

- `moment_key` is deterministic and unique per report;
- moment kind is `personal_board_choice`, `strategy_pivot`,
  `strategy_guidance`, or `alert_event`;
- player ids are optional where the saved event has no player; and
- safe summary excludes all private fields.

Reports are draft-owned and cascade only if the draft is deliberately deleted.
A reset preserves the source draft, so its report remains available.

## Service Boundaries

New backend domain:

```text
backend/src/friendly_hub/domains/reports/
|-- definitions.py
|-- engine.py
|-- models.py
|-- schemas.py
|-- service.py
|-- export.py
`-- router.py
```

Responsibilities:

- `definitions.py`: versions, section registry, reason codes, thresholds, and
  explanation templates;
- `engine.py`: pure deterministic report calculations and fingerprinting;
- `models.py`: SQLAlchemy rows;
- `schemas.py`: API request/response models;
- `service.py`: eligibility, snapshot loading, transaction, idempotency,
  comparison, and privacy projection;
- `export.py`: standalone escaped HTML generation; and
- `router.py`: thin HTTP transport.

The reports domain reads public service boundaries from drafts, mocks, alerts,
boards, and leagues. It does not write those domains.

## API Contract

### Generate

`POST /api/v1/draft-sessions/{session_id}/post-draft-reports`

Request:

```json
{
  "draft_revision": 240,
  "expected_completed_at": "2026-07-29T19:00:00Z"
}
```

Behavior:

- requires the local mutation guard;
- validates completed state and exact revision;
- loads all inputs in one consistent transaction;
- computes the fingerprint and report;
- saves all report rows atomically;
- returns `201` for a new report; and
- returns `200` with `idempotent: true` for identical input.

It changes no source record.

### Read one

`GET /api/v1/post-draft-reports/{report_id}`

Returns:

- report summary;
- all section summaries;
- roster player rows;
- bounded decision moments;
- compatibility fingerprints;
- limitations; and
- available actions.

### List for a draft

`GET /api/v1/draft-sessions/{session_id}/post-draft-reports`

Bounded pagination, newest first.

### List for a board

`GET /api/v1/boards/{board_id}/post-draft-reports`

Filters:

- mode;
- completion date;
- strategy key for mocks;
- report version; and
- league-shape fingerprint.

No player-name or private-note search is required in V1.

### Compare

`POST /api/v1/post-draft-report-comparisons/preview`

Request:

```json
{
  "report_ids": [
    "report-a",
    "report-b"
  ]
}
```

Rules:

- two to four unique reports;
- equivalent league-shape fingerprint;
- same report rules version;
- no persistence;
- no winner, ranking, or composite delta;
- section-by-section counts and availability;
- `not_comparable` for a section unsupported by one or more reports; and
- mock-only strategy comparison appears only when every selected report is a
  mock with compatible strategy-definition versions.

### Export

`GET /api/v1/post-draft-reports/{report_id}/export.html`

Returns a standalone UTF-8 HTML document with:

- semantic headings, tables, lists, and print CSS;
- escaped user-controlled display text;
- no JavaScript;
- no external assets;
- no remote URLs or tracking;
- safe provenance labels only;
- the evidence limits section; and
- a filename based on sanitized draft name and completion date.

The regular draft CSV remains unchanged and Phase 6-free.

## Response Shape

Top-level report:

- id;
- draft id;
- draft name;
- mode;
- completion and generation timestamps;
- versions;
- league-shape fingerprint;
- summary;
- sections;
- roster;
- moments;
- limitations;
- comparison eligibility; and
- export availability.

Normal responses exclude:

- input fingerprint;
- raw evidence;
- source player keys;
- provider IDs;
- private source references;
- Personal Board notes;
- private strategy notes;
- CPU seed and random audit;
- manager internal references; and
- raw serialized database JSON.

## Comparison Semantics

Comparison is descriptive.

Allowed deltas:

- position counts;
- starter slots filled;
- unfilled starter labels;
- depth counts;
- concentration bands;
- categorical evidence distributions;
- strategy event-state counts;
- pivot count;
- Personal Board moment count; and
- recorded alert-moment count.

Prohibited deltas:

- overall quality;
- projected wins;
- expected points;
- dynasty portfolio value;
- liquidity;
- championship odds;
- hindsight correctness;
- CPU strength; and
- a ranked winner.

Mode is always shown. A live and mock report may be compared when league shape
and rule versions match, but mock-only sections render `not_comparable`.

## Desktop Contract

New frontend feature:

```text
frontend/src/features/reports/
|-- ReportWorkspace.tsx
|-- ReportDetail.tsx
|-- ReportComparison.tsx
|-- ReportSection.tsx
|-- ReportMoments.tsx
`-- *.test.tsx
```

### Navigation

- add `Reports` to primary navigation;
- show completed drafts eligible for report generation;
- show saved report history;
- preserve Draft Room and Mock Lab navigation state; and
- never generate a report merely by opening the screen.

### Report generation

- explicit `Generate report` action;
- confirmation identifies the completed draft and frozen revision;
- progress state does not imply background cloud work;
- stale revision refreshes authoritative state;
- idempotent result opens the existing report; and
- failure leaves every source record unchanged.

### Report detail

Order:

1. report identity and limits;
2. roster inventory;
3. starter coverage;
4. construction concentration;
5. optional evidence profiles;
6. strategy story;
7. decision moments; and
8. evidence limits.

No overall score receives hero placement because no overall score exists.

Each section:

- labels availability and confidence in text;
- explains its calculation;
- shows limitations beside the result;
- identifies source label/as-of only when applicable;
- provides an accessible details control; and
- never uses color as the only status signal.

### Comparison

- choose two to four reports;
- filter eligible choices by league compatibility;
- show mode, strategy, date, and format before comparison;
- align the same sections in columns or stacked groups;
- show exact deltas only for comparable counts;
- explain `not_comparable`; and
- provide no winner banner.

### Export

- one `Export HTML` control;
- downloaded file is described as a local standalone report;
- no upload or share language; and
- export failure leaves the saved report intact.

### Accessibility and keyboard

- semantic heading hierarchy;
- tables include captions and scoped headers;
- details dialogs restore focus;
- status changes use polite announcements;
- all actions are keyboard reachable;
- shortcuts do not fire in form fields;
- print layout preserves readable order; and
- reduced-motion preferences are respected.

## Explanation Templates

All prose that characterizes a result uses versioned templates.

Required template families:

- starter coverage complete/partial/unavailable;
- concentration bands;
- production supported/limited/unavailable;
- age-risk supported/limited/unavailable;
- long-term value unavailable;
- liquidity unavailable;
- player fragility unavailable;
- strategy event summary/not-applicable/limited;
- Personal Board moment;
- alert moment;
- comparison compatible/not-comparable; and
- report limitations.

Forbidden objective or predictive phrases include:

- `draft grade`;
- `A+ draft`;
- `best roster`;
- `worst roster`;
- `winner`;
- `championship team`;
- `contender` as a conclusion;
- `guaranteed`;
- `elite` unless it is an exact source-provided band shown as provenance;
- `mistake`;
- `bad pick`;
- `steal`;
- `bust`;
- `must trade`; and
- `should have drafted`.

## Privacy and Logging

- reports remain local in SQLite;
- fixtures use fictional players and sanitized league profiles;
- report exports may include player display names because they are the user's
  requested roster artifact;
- exports exclude Personal Board notes and private strategy notes;
- exports exclude source player keys, provider IDs, private source references,
  raw evidence rows, and internal manager references;
- normal logs exclude player names and roster contents;
- logs use report id, draft id, versions, section availability counts,
  correlation id, and duration;
- comparison logs record report count and compatibility result, not report
  contents;
- HTML escapes all user-controlled names and labels;
- HTML contains no remote requests; and
- normal responses expose safe source label/as-of metadata only.

## Error and Recovery Rules

Required codes:

- `REPORT_DRAFT_NOT_COMPLETE`;
- `REPORT_DRAFT_STALE_REVISION`;
- `REPORT_DRAFT_INCOMPLETE`;
- `REPORT_LEAGUE_SHAPE_UNAVAILABLE`;
- `REPORT_VERSION_UNSUPPORTED`;
- `REPORT_NOT_FOUND`;
- `REPORT_COMPARISON_INVALID`;
- `REPORT_COMPARISON_INCOMPATIBLE`;
- `REPORT_GENERATION_FAILED`; and
- `REPORT_EXPORT_FAILED`.

Errors state:

- what remained unchanged;
- which draft revision or input failed;
- whether an existing report is still safe to open; and
- the next recovery action.

Transaction rules:

- report header, players, sections, and moments commit atomically;
- late failure rolls back only new report rows;
- source draft, picks, mock, alerts, board, and evidence remain unchanged;
- repeated generation after a rollback is safe;
- restart may return an already committed report by fingerprint; and
- export performs no database mutation.

## Performance and Limits

- maximum `500` draft candidates;
- maximum `60` user roster picks;
- maximum `100` saved sections and sub-sections;
- maximum `10` Personal Board moments in detail/export;
- maximum `20` alert moments in export;
- full safe alert history is paginated;
- two to four reports per comparison;
- generation target under `1 second` for a 500-candidate completed draft;
- cached report-read target under `100 milliseconds`;
- comparison target under `500 milliseconds`;
- HTML export target under `1 second`;
- export target under `2 MB`; and
- no network request in generation, read, comparison, or export.

## Test Strategy

### Unit tests

- canonical input serialization and fingerprinting;
- completed-draft eligibility;
- deterministic maximum starter assignment;
- flex-slot tie-breaking;
- depth inventory;
- early/middle/late windows;
- concentration bands and exact boundaries;
- evidence coverage thresholds at `49%`, `50%`, `79%`, and `80%`;
- confidence caps;
- freshness at completion rather than read time;
- Personal Board moment eligibility and deduplication;
- alert-moment safe projection;
- section availability;
- comparison compatibility;
- forbidden-language scan;
- HTML escaping; and
- HTML contains no script, remote URL, or external asset.

### Persistence tests

- migration upgrade and downgrade round trip;
- report fingerprint uniqueness;
- one player per report and pick;
- one section key per report;
- deterministic moment-key uniqueness;
- enum and range constraints;
- draft-owned cascade;
- reset source preservation;
- immutable report rows;
- idempotent generation; and
- transaction rollback on late failure.

### Integration tests

- completed live report generation;
- completed mock report generation;
- active and paused rejection;
- exact draft revision guard;
- full roster and starter coverage;
- optional evidence supported/limited/unavailable paths;
- incompatible and expired evidence;
- mock strategy revisions and guidance;
- live strategy not-applicable;
- Personal Board moments from frozen snapshot;
- safe alert and trade-up moments;
- alert not-configured and disabled distinctions;
- repeated generation idempotency;
- restart recovery;
- reset draft receives a separate report;
- source rows unchanged after generation;
- two-to-four compatible comparison;
- incompatible comparison rejection;
- safe standalone HTML export;
- normal response privacy scan;
- export privacy scan; and
- existing draft CSV remains Phase 6-free.

### Frontend tests

- Reports navigation and eligible completed-draft list;
- explicit generation confirmation;
- no generation on mount;
- stale revision refresh;
- report section availability and confidence labels;
- no overall score or winner;
- starter coverage and concentration explanations;
- unsupported long-term, liquidity, and fragility sections remain visible;
- optional production and age-risk evidence;
- mock strategy story and live not-applicable state;
- Personal Board and alert moments;
- compatible comparison and not-comparable state;
- export action;
- error recovery;
- keyboard behavior;
- focus restoration;
- accessible tables, headings, and announcements; and
- no cloud/share wording.

### Live workflow audit

- create two same-shape 10-team, 24-round third-round-reversal mocks;
- complete both fully offline with different strategies;
- attach synthetic compatible alert evidence to one mock;
- exercise strategy pivots and recorded alerts;
- generate both reports;
- restart and read identical saved reports;
- verify identical generation returns idempotently;
- inspect starter assignment and all section states;
- verify unsupported evidence remains unavailable;
- compare the two compatible reports without a winner;
- generate a completed live-draft report;
- verify live strategy state is not applicable;
- export standalone HTML;
- scan response, logs, and HTML for private fields and remote URLs;
- verify source draft, picks, mock, alerts, and board are unchanged; and
- complete full repository verification.

### Known coverage gaps at specification time

- no approved real production, age, contract, injury, or liquidity dataset;
- no calibrated outcome or roster-strength model;
- no visual-regression harness;
- no dedicated HTML-to-PDF packaging path; and
- no GitHub Actions workflow.

Synthetic fixtures can prove deterministic calculations, privacy boundaries,
and offline behavior. They cannot prove real-world predictive accuracy.

## Acceptance Tests

1. Active and paused drafts cannot generate a report.
2. A completed live draft can generate one report offline.
3. A completed mock can generate one report offline.
4. A stale draft revision is rejected without source mutation.
5. Identical inputs return the same report idempotently.
6. A reset or different draft produces a distinct report.
7. Report generation changes no draft, pick, mock, alert, board, or evidence
   row.
8. A late persistence failure leaves no partial report.
9. Restart restores the identical saved report.
10. Report input uses the frozen draft candidate snapshot, not the current
    Personal Board.
11. Position inventory matches the user's active completed picks.
12. Starter assignment fills the maximum number of eligible slots.
13. Starter-assignment ties use the documented stable order.
14. Depth counts exclude assigned starters.
15. Concentration boundary calculations match the versioned rules.
16. Concentration language never becomes a quality verdict.
17. Missing league shape makes starter coverage unavailable rather than
    guessed.
18. Production coverage below `50%` is unavailable.
19. Production coverage from `50%` through `79%` is limited.
20. Production coverage at or above `80%` is supported and confidence remains
    capped at medium.
21. Age-risk coverage follows the same thresholds.
22. Freshness is evaluated at draft completion and does not change on later
    reads.
23. Incompatible or expired evidence cannot produce a supported enriched
    section.
24. Missing long-term evidence remains visibly unavailable.
25. Missing liquidity evidence remains visibly unavailable.
26. Market bands are never relabeled liquidity.
27. Missing injury or contract evidence keeps player fragility unavailable.
28. Rookie count never becomes a long-term value score.
29. Mock strategy history contains only saved revisions and guidance events.
30. A pivot is not counted as failure.
31. Live reports label strategy not applicable.
32. Personal Board moments match reconstructed availability and thresholds.
33. Repeated passing on one player collapses to one bounded moment.
34. Personal Board notes never appear in a moment.
35. Only saved Phase 5 events appear as alert moments.
36. A report never invents a retrospective alert.
37. Trade-up moments contain only ranged pick references and no ownership
    claim.
38. Alert moments do not claim that a trade occurred.
39. Reports with equivalent league shape and versions can be compared.
40. Two to four reports are accepted; duplicates or larger sets are rejected.
41. Incompatible reports cannot produce section deltas.
42. Comparison contains no winner, ranking, or composite score.
43. HTML export is standalone and contains no script or remote request.
44. HTML escapes draft, team, player, and source display text.
45. Normal responses and exports exclude provider IDs, private source
    references, raw rows, Personal Board notes, private strategy notes, seed,
    randomness, and manager internal references.
46. Draft CSV export remains Phase 6-free.
47. Every supported or limited section includes a plain-language explanation.
48. Every unavailable section explains which evidence is missing.
49. No report contains forbidden objective, predictive, or hindsight language.
50. The full Entropy-shaped report and comparison workflow completes offline
    within performance limits.

## Exit Criteria

Phase 6 is complete when:

- all four product-gate decisions are approved;
- completed live and mock drafts generate immutable reports;
- identical generation is idempotent;
- position inventory and starter coverage are deterministic;
- core construction observations work without Phase 5 evidence;
- optional evidence enriches only supported sections;
- missing long-term, liquidity, and player-fragility evidence stays visible;
- mock strategy and recorded decision moments are inspectable;
- two to four compatible reports can be compared without a winner;
- standalone safe HTML export works offline;
- source draft domains remain unchanged and recoverable;
- the full offline live workflow audit passes; and
- backend, frontend, migration, contract, privacy, build, and dependency checks
  pass.

## Recommended Implementation Order

Each step receives a bounded contract, tests, audit, and reviewable commit
before the next step begins.

1. Approve the four product-gate decisions.
2. Approve report section definitions, availability thresholds, starter
   assignment, explanation templates, and synthetic expected fixtures.
3. Add pure deterministic report-engine fixtures.
4. Add report, player, section, and moment persistence.
5. Add completed-draft eligibility and idempotent generation API.
6. Add optional Phase 5 evidence enrichment.
7. Add mock strategy story and Personal Board/alert moments.
8. Add compatible comparison preview.
9. Add standalone safe HTML export.
10. Add the desktop Reports workspace.
11. Run specification audit, fix critical gaps, and complete the offline live
    workflow audit.

The bounded contract for implementation step 2 is recorded in
[Phase 6 Report Definitions and Expected-Fixture Contract](phase-6-report-contract.md).

The bounded contract for implementation step 3 is recorded in
[Phase 6 Deterministic Report Engine Fixtures](phase-6-report-engine-fixtures.md).

The bounded contract for implementation step 4 is recorded in
[Phase 6 Post-Draft Report Persistence](phase-6-report-persistence.md).

The bounded contract for implementation step 5 is recorded in
[Phase 6 Completed-Draft Report Generation API](phase-6-report-generation-api.md).

The bounded contract for implementation step 6 is recorded in
[Phase 6 Attached-Evidence Report Enrichment](phase-6-evidence-enrichment.md).

The bounded contract for implementation step 7 is recorded in
[Phase 6 Saved Strategy and Decision Moments](phase-6-strategy-decision-moments.md).

The bounded contract for implementation step 8 is recorded in
[Phase 6 Compatible Report Comparison Preview](phase-6-report-comparison.md).

The bounded contract for implementation step 9 is recorded in
[Phase 6 Standalone Safe HTML Report Export](phase-6-report-html-export.md).

The bounded contract for implementation step 10 is recorded in
[Phase 6 Desktop Reports Workspace](phase-6-desktop-reports-workspace.md).

## Deferred Revisit

- overall or letter grades;
- projections and championship probability;
- approved age and experience model;
- long-term dynasty outcome model;
- dedicated liquidity and market-depth evidence;
- injury, contract, and role-fragility evidence;
- multi-source consensus;
- hindsight outcome backtesting;
- editable private report reflections;
- PDF generation;
- cloud sharing;
- report-driven learned tendencies;
- mobile report layout beyond responsive desktop support;
- Phase 7 packaging and print hardening; and
- V2 season-companion roster evaluation.
