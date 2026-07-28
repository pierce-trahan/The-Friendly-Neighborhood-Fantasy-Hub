# Phase 4 Specification: Mock Draft Engine and Strategy Lab

**Status:** Draft for product approval

**Date:** 2026-07-28

## How to Use This Document

- The product owner approves the four product-gate decisions and initial
  checkpoint definitions.
- The implementation engineer follows the persistence, API, deterministic
  engine, and recommended-build-order contracts.
- The auditor uses the privacy rules, test strategy, acceptance tests, and exit
  criteria before Phase 4 is called complete.

Related documents:

- [V1 roadmap](../../PROJECT_ROADMAP.md);
- [Phase 3 draft-room contract](phase-3-draft-room.md);
- [league-format reference](../requirements/league-format-reference.md);
- [local-browser architecture](../adr/0001-local-browser-application-architecture.md);
- [local data model](../adr/0002-local-data-and-configuration-model.md);
- [module boundaries](../adr/0003-repository-and-module-structure.md); and
- [errors and logging standard](../standards/errors-and-logging.md).

## Outcome

Phase 4 turns the recoverable Phase 3 draft room into a deterministic practice
environment.

The user still makes every selection for their own team. CPU-controlled slots
may advance one saved pick at a time, while a selected strategy guide explains
roster-construction checkpoints and viable pivots. Identical snapshots,
settings, engine version, and random seed reproduce the same CPU decisions.

The module teaches draft process. It does not predict a real market, claim that
a player will be available, or turn a strategy into an autopilot.

## Product Approval Gate

Implementation must not begin until the following recommended decisions are
approved:

1. **Practice-board baseline:** CPU player valuation uses the mock's snapshotted
   Personal Board order because V1 does not yet have an approved market-value
   source. The interface labels results `Practice simulation`, never `Market
   projection`.
2. **Timeline-strategy limit:** `win_now` and `productive_struggle` may give
   roster-level construction guidance, but they may not classify individual
   veterans as win-now assets or prospects as long-term assets. The current
   Player Universe has rookie status but no dependable age, production,
   contract, or market-liquidity signal.
3. **History ingestion boundary:** Phase 4 may consume normalized manager draft
   history when it exists, but it does not add direct Sleeper synchronization
   or scrape provider history. Insufficient history always falls back to a
   clearly labeled CPU archetype.
4. **Learning consent:** completed mocks are excluded from learned local signals
   by default. The user must opt in per mock, and may reverse that choice.

These limits preserve the roadmap without inventing evidence the application
does not possess.

## Design Trade-offs

| Decision | Benefit | Cost accepted for V1 | Revisit trigger |
|---|---|---|---|
| Use the snapshotted Personal Board as the CPU baseline | Keeps the simulation local, inspectable, and usable with ADP hidden | CPU choices reflect the user's practice board, not an independent market forecast | Phase 5 approves a provenance-tracked market source |
| Persist one CPU pick per request | Each confirmed pick is recoverable, auditable, and safe to retry | `Run to my pick` makes more local requests than a bulk simulation | Measured local latency makes sequential advancement disruptive |
| Key seeded draws to a content fingerprint | Equivalent frozen inputs replay across different database session IDs | Every decision-affecting input must be versioned and fingerprinted correctly | A new engine input requires a fingerprint-schema revision |
| Bound strategy advice to available roster evidence | The app stays honest about what it knows | `win_now` and `productive_struggle` are less player-specific in V1 | Approved age, production, contract, or liquidity data becomes available |
| Snapshot CPU profiles at mock creation | Past mocks remain reproducible after profile rules or history change | A running mock does not automatically adopt later profile improvements | The user explicitly starts a replacement mock |

These are deliberate constraints, not hidden implementation shortcuts.

## Existing Inputs and Known Gaps

### Available now

- frozen Phase 3 draft order, teams, mode, and current revision;
- frozen candidate identity, position, rookie status, and Personal Board
  context;
- league-profile roster positions and normalized scoring configuration when a
  profile is attached;
- completed picks, corrections, undo history, pause, reset, and recovery;
- local SQLite persistence; and
- deterministic, inspectable Python services.

### Not available as approved Phase 4 evidence

- ADP or consensus rank;
- dynasty market value;
- age or date of birth;
- NFL experience and contract horizon;
- production projections;
- historical outcomes;
- normalized manager draft history;
- provider live-draft synchronization; and
- reliable player-level win-now or long-term timeline scores.

Missing evidence lowers or disables guidance. It never causes the engine to
silently guess.

## Scope

### Included

- creation of mock-only configuration attached to a Phase 3 `mock` session;
- explicit integer random seed and versioned deterministic draw algorithm;
- adjustable randomness from `0` through `100`;
- one saved CPU pick per server mutation;
- a frontend `Run to my pick` loop that confirms each saved CPU pick before
  requesting the next;
- fallback CPU archetypes based on position, roster shape, Personal Board
  order, and bounded seeded variation;
- a selectable strategy for each mock, chosen by the user, with append-only
  strategy-pivot history;
- balanced, win-now, productive-struggle, hero-RB, robust-RB, WR-heavy, and
  early-quarterback guides;
- contextual nudges rather than locked selections, expressed as
  roster-construction checkpoints and off-plan-but-viable explanations;
- visible strategy confidence and missing-input limitations;
- fallback-versus-history profile provenance and confidence;
- reversible per-mock inclusion in learned local signals;
- mock history summaries;
- recoverable mock reset with copied mock settings;
- deterministic decision audit rows; and
- keyboard-friendly desktop controls consistent with the editorial
  workstation.

### Excluded

- automatic selection for the user's slot;
- automated live-draft picks;
- claims about real-world player availability;
- ADP, consensus, projections, market values, or Phase 5 value alerts;
- player-specific win-now or long-term classifications without approved data;
- direct provider draft-history import or live synchronization;
- trade simulation;
- auction drafts;
- keeper assignment;
- traded-pick ownership;
- multi-user or cloud simulation;
- generative-AI picks or strategy advice;
- reinforcement learning;
- background draft timers or notifications; and
- post-draft grading, which remains Phase 6.

## Roadmap Traceability

| Phase 4 roadmap promise | Contract coverage |
|---|---|
| selectable strategy for each mock | Strategy configuration, revision, pivot, and desktop contracts |
| simple CPU manager archetypes as fallback | Seven fallback archetypes with visible provenance |
| league-manager profiles only when sufficient draft history exists | Minimum-history threshold, confidence, and fallback rules |
| contextual nudges rather than locked selections | Non-blocking guidance events and the no-autopilot rule |
| roster-construction checkpoints | Versioned early, middle, and late checkpoint definitions |
| off-plan-but-viable explanations | Four-state guidance contract with evidence and limitations |
| adjustable randomness | Integer `0` through `100` with a deterministic score formula |
| mock history that only affects learned local signals when the user opts in | Default-off, reversible per-mock learning consent |
| identical settings and random seed reproduce a mock | Versioned engine, frozen snapshots, content fingerprint, and seeded draws |
| no strategy forces a player selection | User-slot and guidance mutation boundaries |
| the user can pivot strategies mid-draft | Append-only strategy revisions that affect later guidance only |
| manager-history confidence is visible | Profile provenance, sample size, confidence, and limitation codes |
| mocks can be excluded from learned tendencies | Reversible consent endpoint and default exclusion |

## Product Rules

1. The user slot is never CPU-controlled.
2. A strategy guide never submits, blocks, or replaces a user pick.
3. A CPU mutation records exactly one pick and commits the draft pick and its
   decision audit together.
4. `Run to my pick` is a client loop over confirmed one-pick mutations. Closing
   the browser loses no confirmed CPU pick.
5. CPU decisions use only the frozen mock snapshot and versioned mock settings.
6. Personal Board order is a practice baseline, not market evidence.
7. Randomness changes variation, not reproducibility. The same inputs and seed
   return the same decision.
8. Ties use stable canonical-player-ID ordering after seeded scoring.
9. Corrections and undo remain authoritative Phase 3 controls.
10. Strategy pivots affect later guidance only. They never rewrite earlier
    picks or explanations.
11. Missing league or timeline evidence is visible in confidence and
    limitation codes.
12. Learned manager profiles are unavailable below the documented evidence
    threshold.
13. A fallback CPU archetype is never presented as a real manager model.
14. Mock-history learning is opt-in and reversible.
15. Normal responses, exports, errors, and logs exclude provider IDs, Personal
    Board notes, and private manager identifiers.

## Terminology

- **Mock configuration:** versioned simulation settings attached one-to-one to a
  Phase 3 mock session.
- **Practice-board baseline:** the snapshotted Personal Board order used as the
  CPU's starting player order.
- **CPU slot:** a non-user draft slot controlled by the mock engine.
- **Fallback archetype:** a transparent synthetic roster-building preference,
  not a learned real-manager profile.
- **Manager profile:** a bounded tendency snapshot produced only from
  sufficient normalized history.
- **Randomness:** the maximum seeded score variation allowed around the
  deterministic baseline.
- **Strategy guide:** user-facing roster-construction checkpoints and pivot
  explanations.
- **Strategy pivot:** a saved change in the user's active strategy guide.
- **Guidance event:** a saved, dismissible checkpoint explanation that does not
  select a player.
- **Decision audit:** the saved components that explain a CPU pick.
- **Draft revision:** the existing Phase 3 revision guarding picks.
- **Mock revision:** a separate monotonic revision guarding strategy, history,
  and guidance mutations.

## High-Level Flow

```text
Frozen Phase 3 snapshot
        |
        +--> CPU profile + practice-board rank + roster state
        |                         |
        |                  deterministic scorer
        |                         |
        |                  one transactional pick
        |                         |
        +-----------------> saved decision audit
        |
        +--> user roster + league shape + selected strategy
                                  |
                           checkpoint evaluator
                                  |
                    nudge / viable pivot / limitation
```

The mock engine may write through a shared internal Phase 3 pick primitive, but
the public Phase 3 live-draft contract remains unchanged.

## Mock Creation

`POST /api/v1/boards/{board_id}/mock-sessions` creates:

1. a Phase 3 draft session with `mode = mock`;
2. a frozen candidate and Personal Board snapshot;
3. one mock configuration;
4. one profile snapshot for every non-user slot;
5. the initial user-strategy revision; and
6. the first applicable checkpoint state.

Creation is one transaction. A partial mock session is never visible.

### Required request fields

- Phase 3 session name, format, reversal flag, teams, rounds, user slot, team
  names, and optional league-profile reference;
- `seed`: unsigned 64-bit integer represented as a decimal string;
- `randomness`: integer from `0` through `100`;
- `strategy_key`;
- optional explicit fallback archetype per non-user slot; and
- `include_in_learning`, default `false`.

If fallback archetypes are omitted, assignment is deterministic from seed,
draft slot, and the supported-archetype list.

Example:

```json
{
  "name": "Entropy strategy rehearsal",
  "draft_format": "snake",
  "third_round_reversal": true,
  "team_count": 10,
  "round_count": 24,
  "user_slot": 4,
  "league_profile_id": "local-profile-id",
  "seed": "2026072801",
  "randomness": 35,
  "strategy_key": "hero_rb",
  "include_in_learning": false
}
```

### Creation rejection

- the selected board is archived;
- Phase 3 configuration is invalid;
- fewer than two candidates exist;
- the candidate cap is exceeded;
- the requested strategy is unknown;
- a strategy is incompatible with the league shape and has no safe reduced
  behavior;
- an archetype key is unknown; or
- the seed is outside the unsigned 64-bit range.

## Deterministic Draw Algorithm

V1 uses a counter-based SHA-256 draw rather than Python's process-global random
state.

Each draw hashes a canonical UTF-8 string containing:

- engine version;
- seed;
- content fingerprint for the frozen candidate, order, profile, and league-shape
  snapshots;
- overall pick;
- selecting slot;
- draw purpose;
- draw index; and
- stable candidate or archetype key when applicable.

The first unsigned 64 bits of the digest become a value in `[0, 1)`.

Properties:

- no process-global random state;
- no result dependence on database row order;
- no result dependence on browser timing;
- stable replay across restart;
- stable tie-breaking; and
- an explicit `rng_version` stored with the mock.

Changing the algorithm requires a new version. Historical mocks always retain
their original version.

The content fingerprint, rather than the database session ID, allows a
separately created replay to reproduce the same decisions when its frozen
inputs are identical. A reset whose fresh candidate or league snapshot changes
receives a different fingerprint and is explicitly labeled non-identical.

## CPU Selection Engine

### Candidate eligibility

A CPU pick considers:

- available candidates in the frozen mock snapshot;
- canonical position;
- snapshotted Personal Board rank;
- rookie flag;
- the CPU slot's current roster;
- attached league roster positions when available; and
- the CPU profile snapshot.

It does not consider board notes, Gut ELO, ADP, market value, projections, or
provider identifiers.

Unranked candidates remain eligible after ranked candidates and receive a
stable alphabetical/canonical fallback order.

### Score components

Every eligible candidate receives inspectable integer components:

- `board_order`: practice-board baseline;
- `starter_need`: league-shape coverage nudge;
- `depth_need`: soft roster-balance nudge;
- `archetype_fit`: profile-specific position or rookie preference;
- `duplication_penalty`: soft penalty for extreme positional concentration;
- `random_variation`: bounded seeded variation; and
- `stable_tiebreak`: canonical ID, used only after numeric scores tie.

No component is called player quality, market value, or projection.

Randomness `0` makes `random_variation = 0`. Randomness `100` uses the maximum
documented variation band. The band may reorder nearby practice-board players;
it must not make an unranked player leap the entire ranked pool without another
visible roster or archetype reason.

### V1 scoring bounds

The first engine version uses integer components with these hard bounds:

| Component | Minimum | Maximum |
|---|---:|---:|
| `board_order` | `0` | candidate count multiplied by `100` |
| `starter_need` | `-200` | `300` |
| `depth_need` | `-100` | `150` |
| `archetype_fit` | `-150` | `200` |
| `duplication_penalty` | `-300` | `0` |
| `random_variation` | `-200` | `200` |

For `N` ordered candidates and zero-based practice index `i`,
`board_order = (N - i) * 100`. Ranked candidates come first; unranked
candidates follow in stable alphabetical/canonical order.

For a deterministic draw `d` in `[0, 1)`,
`random_variation = round((2 * d - 1) * 2 * randomness)`.

To prevent implausible full-pool jumps, CPU scoring considers:

1. the top `1 + floor(randomness / 5)` available practice-board candidates,
   capped at `21`;
2. the top three available candidates at each position with an unfilled
   normalized starter requirement; and
3. the top three available candidates at the archetype's emphasized position.

The union is deduplicated before scoring. At randomness `0`, roster and
archetype needs may still justify a lower-ranked candidate, but random variation
cannot.

Exact component tables live in one versioned engine-definition file and are
covered by fixtures. Changing a bound or table requires a new CPU engine
version.

### Supported fallback archetypes

- `balanced`: moderate starter coverage and concentration penalties;
- `qb_priority`: stronger quarterback and superflex coverage;
- `rb_heavy`: stronger early running-back depth;
- `wr_heavy`: stronger early wide-receiver depth;
- `te_aware`: stronger tight-end coverage when the league starts or rewards
  tight ends;
- `rookie_lean`: bounded rookie preference with low-confidence labeling; and
- `chaotic`: wider seeded variation with ordinary roster-safety penalties.

Archetypes use soft score changes. They do not impose hard position locks.

### Selection

The highest total score is selected. Numeric ties resolve by canonical player
ID.

The decision audit stores:

- chosen player ID;
- overall pick and selecting slot;
- engine and RNG versions;
- seed;
- total score;
- component scores;
- random draw inputs and output;
- up to five scored alternatives;
- profile source and confidence; and
- reason and limitation codes.

Normal logs contain IDs and codes only, not player display names or manager
identities.

## CPU Advancement

`POST /api/v1/mock-sessions/{session_id}/cpu-pick` contains:

- exact draft revision;
- exact mock revision;
- expected overall pick; and
- expected selecting slot.

The server validates that:

- the session is a mock;
- the session is active;
- the current slot is not the user slot;
- both revisions match;
- expected pick and slot match;
- the engine and RNG versions are supported; and
- at least one candidate is available.

One transaction:

1. calculates the deterministic decision;
2. records the Phase 3 pick;
3. appends the Phase 3 pick revision;
4. appends the CPU decision audit; and
5. commits both revisions once.

There is no server endpoint that fills an arbitrary number of picks in one
transaction.

### `Run to my pick`

The desktop client:

1. requests one CPU pick;
2. renders the committed response;
3. stops if the user is on the clock, the session pauses/completes, or an error
   occurs;
4. otherwise requests the next CPU pick; and
5. exposes `Stop after current pick`.

The loop is limited to `31` consecutive CPU picks, the maximum possible before
one user's turn in a 32-team draft. Continuing beyond that requires another
explicit user action.

## Strategy Guide

### Strategy keys

- `balanced`;
- `win_now`;
- `productive_struggle`;
- `hero_rb`;
- `robust_rb`;
- `wr_heavy`; and
- `early_qb_superflex`.

Strategy definitions are versioned data, not scattered UI conditionals.

Each definition contains:

- compatible league-shape conditions;
- checkpoint pick or round windows;
- roster-count targets or ranges;
- reason codes;
- viable-pivot rules;
- required evidence;
- missing-evidence limitations; and
- plain-language explanation templates.

### V1 evidence boundary

`balanced`, `hero_rb`, `robust_rb`, `wr_heavy`, and
`early_qb_superflex` may use position, pick window, and league roster shape.

`win_now` and `productive_struggle` may use:

- starter coverage;
- positional investment timing;
- rookie count only as a low-confidence context signal; and
- visible missing-evidence limitations.

They may not:

- call a non-rookie productive;
- call a rookie a long-term hit;
- infer age from name, team, status, or notes;
- use board rank as a timeline signal; or
- produce player-specific timeline recommendations.

### Recommended initial checkpoints

Checkpoint windows are expressed as a fraction of configured rounds so the
guides work for both 24-round startups and shorter drafts. `early` ends after
the first `25%` of rounds, `middle` ends after `60%`, and `late` is the
remainder. Fractional boundaries round up.

- `balanced`
  - by the middle boundary, fill at least `75%` of normalized starter slots;
  - no single non-quarterback position exceeds `40%` of user picks before the
    middle boundary.
- `win_now`
  - by the middle boundary, fill every distinct normalized starter position;
  - rookie count is context only and never a negative player judgment;
  - missing production and age evidence keeps confidence `low`.
- `productive_struggle`
  - no more than one running back in the early window;
  - prioritize quarterback, wide receiver, and tight-end roster optionality at
    the position-count level;
  - missing age, liquidity, and market evidence keeps confidence `low`.
- `hero_rb`
  - exactly one running back target in the early window;
  - no more than two running backs before the middle boundary;
  - moving above two becomes `off_plan_viable`, not a blocked action.
- `robust_rb`
  - at least two running backs by the early boundary;
  - target three by the middle boundary when roster length permits;
  - quarterback and tight-end starter coverage can produce a viable pivot.
- `wr_heavy`
  - at least three wide receivers by the middle boundary when the draft has at
    least six rounds;
  - wide receiver represents at least `35%` of user picks through the middle
    window.
- `early_qb_superflex`
  - compatible only when normalized league shape includes superflex or at least
    two quarterback-eligible starter slots;
  - target one quarterback in the first `10%` of rounds and two by the early
    boundary.

These are guide defaults, not claims that one construction is objectively
correct. Approval of this specification approves them as the first versioned
checkpoint set.

### Checkpoint states

- `on_plan`: current roster is inside the strategy's target range;
- `watch`: the next window may create a strategy tension;
- `off_plan_viable`: the user departed from the guide but retains a coherent
  roster path;
- `risk_checkpoint`: an important roster-coverage or concentration issue is
  approaching; and
- `insufficient_evidence`: the guide cannot support a stronger conclusion.

No state disables the Draft button.

### Guidance shape

A guidance event includes:

- strategy and definition version;
- effective overall pick;
- state;
- affected roster positions;
- observed counts;
- target range;
- reason codes;
- confidence: `high`, `medium`, `low`, or `unavailable`;
- missing-input codes;
- one plain-language explanation;
- one optional viable-pivot explanation; and
- dismissal state.

Guidance never contains a selected player ID.

## Strategy Pivots

The user may pivot while an active or paused mock is incomplete.

`PATCH /api/v1/mock-sessions/{session_id}/strategy` contains:

- exact mock revision;
- expected current overall pick;
- new strategy key; and
- optional private user note.

The server appends a strategy revision with:

- previous and next strategy;
- effective overall pick;
- current user-roster counts;
- reason `user_pivot`; and
- timestamp.

Earlier picks and guidance remain attached to their original strategy revision.
The new guide evaluates only the current state and later decisions.

The optional note is local-only, excluded from normal logs and public exports,
and never parsed as machine instruction.

## Manager Profiles and Confidence

### Fallback profile

Always available.

Response fields:

- `source = fallback`;
- archetype key;
- `confidence = not_applicable`;
- `draft_count = 0`;
- `pick_count = 0`; and
- explanation that the profile is synthetic.

### History-derived profile

May be created only when normalized, permitted history contains at least:

- `3` completed real drafts for that manager and league shape;
- `20` total selections;
- `8` observations for any tendency shown; and
- source and refresh timestamps.

Below either threshold, the engine uses a fallback profile and returns
`MANAGER_HISTORY_INSUFFICIENT`.

Even above the threshold:

- confidence is based on sample size and recency;
- a tendency is a range, not a certainty;
- manager identity remains an internal local reference;
- normal responses use slot display name only; and
- mock-generated picks are excluded unless their mock explicitly opted in.

Phase 4 defines this consumer contract. Provider history ingestion remains a
separate permission- and privacy-reviewed task.

## Learning Consent and Mock History

`include_in_learning` defaults to `false`.

The user may toggle it for a completed or incomplete mock with the exact mock
revision. The change:

- is reversible;
- does not alter the mock result;
- records the consent timestamp;
- records withdrawal timestamp when disabled; and
- takes effect in the next profile rebuild only.

Mock history summaries show:

- mock name and completion state;
- seed and randomness;
- selected strategy and pivot count;
- format, teams, rounds, and user slot;
- created, updated, and completed timestamps;
- inclusion-in-learning state; and
- engine versions.

No automatic deletion or cloud upload is introduced.

## Persistence Model

### `mock_configuration`

- `id`;
- unique `draft_session_id`;
- `seed` as decimal text;
- `rng_version`;
- `cpu_engine_version`;
- `strategy_definition_version`;
- frozen normalized league-shape JSON;
- nullable league-shape source timestamp;
- candidate/order/profile/league content fingerprint;
- `randomness`;
- `current_strategy_key`;
- `revision`;
- `include_in_learning`;
- nullable `learning_opted_in_at`;
- nullable `learning_withdrawn_at`;
- `created_at`; and
- `updated_at`.

### `mock_strategy_revision`

- `id`;
- `mock_configuration_id`;
- `sequence_number`;
- nullable previous strategy;
- next strategy;
- effective overall pick;
- user-roster counts JSON;
- nullable private user note;
- `created_at`; and
- unique `(mock_configuration_id, sequence_number)`.

### `mock_cpu_profile`

- `id`;
- `mock_configuration_id`;
- `draft_slot`;
- source: `fallback` or `history`;
- archetype key;
- confidence;
- draft sample count;
- pick sample count;
- bounded tendency snapshot JSON;
- nullable internal manager reference;
- source timestamp;
- `created_at`; and
- unique `(mock_configuration_id, draft_slot)`.

### `mock_pick_decision`

- `id`;
- `mock_configuration_id`;
- `draft_pick_revision_id`;
- overall pick;
- selecting slot;
- chosen player ID;
- profile source and archetype;
- engine and RNG versions;
- total score;
- component scores JSON;
- random audit JSON;
- alternatives JSON, maximum five;
- reason codes JSON;
- limitation codes JSON;
- `created_at`; and
- unique `draft_pick_revision_id`.

### `mock_guidance_event`

- `id`;
- `mock_configuration_id`;
- strategy-revision ID;
- deterministic event key;
- effective overall pick;
- state;
- confidence;
- observed counts JSON;
- target ranges JSON;
- reason codes JSON;
- limitation codes JSON;
- explanation template key;
- nullable pivot template key;
- status: `open`, `acknowledged`, or `dismissed`;
- `created_at`; and
- nullable `resolved_at`.

Unique `(mock_configuration_id, deterministic_event_key)` prevents duplicate
events after refresh or restart.

## API Contract

Every state-changing endpoint uses the existing local write guard. There is no
remote authentication layer because the application binds to the trusted local
service boundary.

### Sessions

- `GET /api/v1/boards/{board_id}/mock-sessions`
  - newest-first mock summaries.
- `POST /api/v1/boards/{board_id}/mock-sessions`
  - atomically creates Phase 3 and Phase 4 snapshots.
- `GET /api/v1/mock-sessions/{session_id}`
  - full Phase 3 state plus mock settings, CPU profiles, current strategy,
    roster checkpoint, guidance, and both revisions.
- `POST /api/v1/mock-sessions/{session_id}/reset`
  - recoverably resets Phase 3 state and copies mock settings and profiles;
  - same seed by default;
  - new seed only when explicitly supplied.

### CPU

- `POST /api/v1/mock-sessions/{session_id}/cpu-pick`
  - records exactly one deterministic CPU pick.
- `GET /api/v1/mock-sessions/{session_id}/decisions/{overall_pick}`
  - returns the active or historical CPU decision audit without Personal Board
    notes or provider data.

Example CPU request:

```json
{
  "draft_revision": 17,
  "mock_revision": 2,
  "expected_overall_pick": 18,
  "expected_selecting_slot": 8
}
```

### Strategy

- `PATCH /api/v1/mock-sessions/{session_id}/strategy`
  - saves a user pivot with exact mock revision.
- `GET /api/v1/mock-sessions/{session_id}/guidance`
  - returns bounded current and recent guidance;
  - default page size `20`, maximum `100`, stable newest-first pagination.
- `PATCH /api/v1/mock-sessions/{session_id}/guidance/{event_id}`
  - acknowledges, dismisses, or reopens one event.

### History consent

- `PATCH /api/v1/mock-sessions/{session_id}/learning`
  - toggles reversible local-learning inclusion with exact mock revision.

Candidate browsing, user pick entry, correction, undo, pause/resume, and CSV
draft-state export continue to use the Phase 3 contract.

## Full Mock Response

The full response includes:

- Phase 3 session state;
- draft revision;
- mock revision;
- seed and engine versions;
- randomness;
- current strategy and revision;
- strategy compatibility and limitations;
- user roster counts;
- current checkpoint;
- current and recent guidance;
- CPU profile summaries with source and confidence;
- nullable last CPU decision summary;
- run-to-user eligibility;
- learning-consent state; and
- recovery guidance.

It does not include:

- Personal Board notes in blind contexts;
- provider IDs;
- raw manager identity;
- private source payloads;
- ADP or market value; or
- hidden player recommendations.

## Desktop Interaction Contract

### Persistent mock strip

- `Practice simulation` label;
- seed and randomness;
- current strategy;
- draft and mock revisions;
- current selecting team;
- `Run to my pick`;
- `Advance one CPU pick`;
- `Stop after current pick`;
- pause/resume; and
- local-saved state.

### User turn

- the ordinary Phase 3 candidate table remains authoritative;
- strategy checkpoint appears beside the table;
- no candidate is preselected;
- `Draft` remains explicit and manually confirmed;
- a pivot control explains that it changes guidance, not earlier picks; and
- limitations remain visible.

### CPU turn

- current CPU profile source and archetype;
- one-pick progress;
- expandable saved decision explanation;
- no fake countdown; and
- a stopped loop leaves the draft at the latest committed pick.

### History and consent

- completed and incomplete mocks;
- replay settings;
- learning opt-in toggle, off by default; and
- plain-language explanation of what opt-in changes.

### Keyboard

- existing Phase 3 shortcuts remain;
- `R` starts `Run to my pick` only on a CPU turn;
- `S` stops after the current request returns;
- shortcuts do not fire inside form fields; and
- CPU advancement never starts from an unlabeled row action.

## Correction, Undo, Pause, and Reset

### Correction

A manual correction remains authoritative. The original CPU decision audit
remains historical and the response labels the active pick `manually
corrected`.

### Undo

Undo uses Phase 3 and clears the latest active pick. If that pick was CPU-made,
its decision audit remains historical. Re-advancing from the identical state
and settings reproduces the same CPU choice.

A paused mock remains paused after undo.

### Pause

Pause stops frontend auto-advance after any in-flight one-pick request returns.
No new CPU request begins while paused.

### Reset

Mock reset:

- preserves the old draft and mock audit;
- creates linked replacement Phase 3 and Phase 4 rows;
- copies strategy, profile snapshots, and randomness;
- keeps the seed unless a new seed is explicitly requested;
- sets learning consent to `false` for the replacement mock;
- uses the fresh Phase 3 candidate snapshot required by reset; and
- reports when changed candidates mean the new run is not an exact replay.

## Error and Recovery Rules

- missing board, mock, decision, guidance, or strategy: safe `404`;
- non-mock session passed to mock API: `409`;
- stale draft or mock revision: `409`;
- expected pick or slot changed: `409`;
- CPU request on the user slot: `409`;
- CPU request while paused, completed, or reset: `409`;
- unsupported engine or RNG version: `409` with upgrade guidance;
- no available candidate: `409`;
- incompatible strategy: `422`;
- invalid seed, randomness, or archetype: `422`;
- insufficient manager history: fallback result, not request failure;
- strategy missing evidence: visible limitation, not fabricated guidance;
- repeated guidance mutation with stale revision: `409`;
- database failure: rollback the pick and decision audit together; and
- frontend loop failure: stop, refresh authoritative state, and preserve every
  already confirmed pick.

## Privacy and Logging

- Mock state remains local.
- Mock fixtures use fictional players and sanitized profiles.
- Personal Board notes are never scoring inputs.
- Internal manager references never appear in normal responses or CSV.
- Provider IDs and source payloads never enter mock decision rows.
- Private pivot notes are excluded from logs and public exports.
- Logs use session ID, slot, overall pick, engine version, reason codes, and
  correlation ID.
- Learning consent is local, explicit, reversible, and never implies cloud
  sharing.

## Limits and Performance

- Phase 3 limits remain authoritative;
- one CPU request records one pick;
- maximum consecutive frontend loop: `31` picks;
- maximum saved alternatives per CPU decision: `5`;
- maximum recent guidance in full response: `20`;
- decision JSON fields use bounded schemas and size limits;
- CPU scoring is bounded by the `2,000`-candidate snapshot;
- no per-candidate database query;
- profile history aggregation is not performed in the live pick request; and
- one CPU pick should complete within an interactive local request.

## Test Strategy

### Coverage gates

- every deterministic draw, score component, tie-break, and archetype branch
  has a fixed unit fixture;
- every strategy checkpoint state and limitation code has at least one positive
  and one boundary fixture;
- every state-changing API has happy-path, stale-revision, invalid-state,
  restart, and rollback coverage;
- every privacy boundary asserts forbidden keys, not only expected values;
- the frontend one-pick loop covers every stop condition; and
- the Entropy-shaped offline workflow is a required release-gate audit.

Line coverage is secondary to these behavioral gates. Framework serialization,
trivial model accessors, and generated contract files do not need artificial
unit tests.

### Unit tests

- SHA-256 draw fixtures are stable across repeated runs;
- seed boundaries and canonical serialization;
- randomness zero removes variation;
- same inputs produce the same score order;
- different seeds can vary nearby candidates without violating hard
  eligibility;
- stable canonical tie-breaking;
- each fallback archetype changes only documented components;
- roster counts derive correctly from Phase 3 picks;
- every strategy checkpoint and viable-pivot rule;
- incompatible and insufficient-evidence states;
- manager-history threshold and confidence bands; and
- guidance event keys are deterministic.

### Integration tests

- atomic mock and Phase 3 session creation;
- one CPU pick persists with one decision audit;
- simulated database failure rolls back both;
- stale draft and mock revisions change no state;
- user slot cannot receive a CPU pick;
- paused, completed, live, and reset sessions reject CPU advancement;
- restart restores seed, profiles, strategy history, decisions, and guidance;
- correction preserves decision history and labels manual override;
- undo followed by re-advance reproduces the decision;
- paused undo remains paused;
- reset preserves old history and creates linked replacement mock state;
- learning consent defaults off and is reversible;
- insufficient history uses a fallback profile;
- normal responses and exports exclude private fields; and
- bounded queries avoid N+1 candidate or profile reads.

### Frontend tests

- `Run to my pick` requests exactly one CPU mutation at a time;
- the loop stops on the user turn, pause, completion, stop request, or error;
- server rejection refreshes authoritative state;
- user pick controls are never automated;
- strategy pivot changes guidance but not completed picks;
- missing-evidence limitations render visibly;
- fallback profiles are not labeled as learned managers;
- learning toggle is off by default and reversible;
- keyboard shortcuts ignore form fields; and
- live sessions never render mock automation controls.

### Live workflow audit

- complete a seeded 10-team, 24-round third-round-reversal mock;
- interrupt and restart between CPU picks;
- reproduce a run from the same seed and unchanged snapshots;
- verify a changed seed produces a different but valid nearby sequence;
- pivot strategies mid-draft;
- correct and undo CPU and user picks;
- verify Blind view remains context-free; and
- export draft state without mock-private data.

### Known coverage gaps at specification time

- no normalized real-manager history fixture exists yet;
- no approved player age, production, contract, or liquidity fields exist;
- no visual-regression harness is configured; and
- no GitHub Actions workflow currently runs repository checks.

History-derived profiles cannot be marked complete until a sanitized,
rights-permitted normalized fixture and its provenance are approved. The
fallback-profile path remains fully testable without it.

## Acceptance Tests

1. Identical snapshots, settings, versions, and seed reproduce every CPU pick.
2. Randomness `0` produces no random score component.
3. A different seed may vary eligible nearby choices while remaining
   deterministic.
4. CPU advancement rejects the user slot.
5. One CPU request commits one Phase 3 pick and one decision audit atomically.
6. Restart resumes from the latest committed pick with the same deterministic
   next decision.
7. `Run to my pick` stops after each confirmed response and never skips the user
   turn.
8. Closing the client during a run loses no confirmed CPU pick.
9. Every decision exposes bounded score components, alternatives, reasons, and
   limitations.
10. CPU output is labeled practice simulation and never market projection.
11. Each fallback archetype produces documented, testable behavior.
12. Insufficient manager history uses a labeled fallback without inventing
    confidence.
13. A learned manager tendency appears only above all evidence thresholds.
14. All seven strategies are selectable when their safe league behavior is
    defined.
15. Strategy guidance never contains a selected player or submits a pick.
16. The user may make an off-plan pick without override or warning blockade.
17. Off-plan-but-viable and insufficient-evidence explanations are distinct.
18. A strategy pivot is append-only and affects only later guidance.
19. Win-now and productive-struggle guidance does not invent player timeline
    evidence.
20. Correction keeps the original CPU audit while making the manual pick
    authoritative.
21. Undo and identical re-advance reproduce the CPU decision.
22. Paused undo leaves the mock paused.
23. Reset preserves the old mock and creates a linked replacement with copied
    mock settings.
24. Learning inclusion defaults off, is reversible, and changes no saved picks.
25. Live draft sessions expose no CPU automation controls.
26. Blind responses remain structurally free of Personal Board and mock-private
    fields.
27. Errors and logs exclude names, notes, provider IDs, and manager identity.
28. A full Entropy-shaped mock works offline and remains responsive.

## Exit Criteria

Phase 4 is complete when:

- a user can create and recover a seeded mock;
- CPU slots advance deterministically one saved pick at a time;
- the user slot is never automated;
- all seven strategy guides have approved, evidence-bounded behavior;
- the user can pivot without rewriting history;
- fallback and learned profiles are visibly distinct;
- mock-learning consent is off by default and reversible;
- every CPU decision and strategy nudge is inspectable;
- no result is presented as ADP, market prediction, or objective player value;
- the full Entropy-shaped workflow passes offline live audit; and
- full backend, frontend, migration, contract, privacy, and dependency checks
  pass.

## Recommended Implementation Order

1. Approve the four product-gate decisions.
2. Add deterministic draw and CPU score unit fixtures.
3. Add mock configuration, strategy revision, CPU profile, decision, and
   guidance persistence.
4. Refactor a shared transaction-safe Phase 3 pick primitive.
5. Add atomic mock creation and one-CPU-pick APIs.
6. Add fallback profiles and deterministic selection.
7. Add strategy definitions, checkpoints, pivots, and limitations.
8. Add correction, undo, pause, and reset integration.
9. Add history consent and summary APIs.
10. Add the desktop Mock/Strategy surface and one-pick client loop.
11. Run specification audit, fix critical gaps, and complete the live workflow
    audit.

## Deferred Revisit

- approved market baselines after Phase 5 source decisions;
- player age, experience, production, and timeline models;
- direct provider draft-history import;
- richer learned manager profiles;
- cross-league simulation;
- auction and keeper mocks;
- trade behavior;
- post-draft grading; and
- packaged desktop performance tuning during Phase 7.
