# Phase 5 Evidence Import and Freshness Contract

**Status:** Bounded implementation contract

**Date:** 2026-07-28

**Parent specification:** [Phase 5 Value and Trade-Up Alerts](phase-5-value-trade-up-alerts.md)

## Outcome

This contract implements Phase 5 step 2: approve the evidence schema,
synthetic fixture, player-mapping rules, and freshness policy before database
or alert-engine code begins.

The import surface accepts two flat CSV files plus metadata entered during
preview. The backend normalizes those inputs into one strict JSON snapshot.
The JSON snapshot is the stable boundary used by later persistence and alert
modules.

This is like separating a reporter's raw notes from the verified fact sheet
used on air: the CSVs are easy to prepare, while the normalized snapshot is
the checked, versioned record every downstream claim must cite.

## Approved Decisions Applied

1. Evidence enters through local, provider-neutral files. This contract adds no
   provider synchronization or scraping.
2. Market evidence remains independent from Personal Board conviction. This
   schema contains no Personal Board rank, tier, favorite, or note.
3. Pick-value inputs contain picks only. No player asset can appear in the
   curve.
4. Provider record references are import-only mapping inputs. Normal alert
   responses and Blind view never expose them.

## Artifacts

- [normalized evidence JSON Schema](../schemas/alert-evidence-snapshot.schema.json);
- [freshness-policy JSON Schema](../schemas/alert-freshness-policy.schema.json);
- [V1 freshness policy](../requirements/alert-freshness-policy.v1.json);
- `tests/fixtures/alert_evidence/player-signals.synthetic.csv`;
- `tests/fixtures/alert_evidence/pick-values.synthetic.csv`; and
- `tests/fixtures/alert_evidence/entropy-alert-evidence.synthetic.json`.

All fixture identities, sources, values, and dates are fictional.

## Import Package

### Files

One preview accepts:

- required `player-signals.csv`;
- optional `pick-values.csv`; and
- metadata entered in the local preview form.

The optional file may be omitted. Player value and return-risk alerts can
still work when the player file is sufficient, while trade-up cost reports
`Pick-only cost unavailable`.

V1 does not accept a ZIP, spreadsheet workbook, remote URL, or executable
formula.

Before parsing:

- the player file is limited to 2 MiB and 1,000 data rows;
- the pick file is limited to 1 MiB and 500 data rows;
- one decoded field is limited to 4 KiB;
- invalid UTF-8 and NUL bytes are rejected; and
- the preview is rejected before any database mutation when a bound is
  exceeded.

### Preview metadata

The user supplies:

- source label;
- source kind: `synthetic`, `user_entered`, `public`, or `licensed`;
- source namespace used for saved identity mappings;
- permitted-use confirmation;
- evidence `as_of` timestamp;
- league type;
- draft purpose;
- team count;
- draft format;
- third-round-reversal state;
- round count;
- quarterback mode;
- reception scoring shape;
- tight-end-premium state;
- optional private source reference; and
- supported draft depth.

The preview form explains that permitted-use confirmation records the user's
assertion; it does not change a source's terms or permit redistribution.

## Player Signals CSV

The exact V1 header is:

```text
source_player_key,display_name,position,team,expected_pick_low,expected_pick_high,market_band,win_now_production_band,age_risk_band,evidence_as_of,limitation_codes
```

Rules:

- UTF-8 with a header row;
- one row per source player key;
- `source_player_key`, `display_name`, and `position` are required;
- expected-pick endpoints are both present or both empty;
- low is no greater than high;
- endpoints are within the declared supported draft depth;
- optional categorical cells are empty when unavailable;
- limitation codes are pipe-separated, unique, uppercase codes;
- extra columns block preview;
- duplicate source keys block preview;
- spreadsheet formulas are treated as text and never executed; and
- leading `=`, `+`, `-`, or `@` in identity text triggers review.

Approved enums:

- position: `QB`, `RB`, `WR`, `TE`, `K`, `DEF`, `DL`, `LB`, or `DB`;
- market band: `premium`, `strong`, `standard`, `depth`, or `fringe`;
- production band: `high`, `medium`, or `low`;
- age-risk band: `lower`, `middle`, or `higher`.

These are source assertions, not Hub player grades. Empty optional bands
normalize to `null`, not `neutral`.

## Pick Values CSV

The exact V1 header is:

```text
asset_key,asset_type,overall_pick,season_offset,round,value_low,value_high,evidence_as_of,limitation_codes
```

Rules:

- `asset_type` is `current_draft_pick` or `future_round`;
- a current-draft row requires `overall_pick` and leaves `season_offset` and
  `round` empty;
- a future-round row requires positive `season_offset` and `round`, and leaves
  `overall_pick` empty;
- value endpoints are non-negative integers;
- low is no greater than high;
- asset keys are unique;
- current-draft value ranges cannot increase as overall pick increases;
- future-round value ranges cannot increase as round increases within one
  season offset;
- limitation codes follow the player-file rules; and
- no player name, player key, or player asset column exists.

The curve is contextual source evidence. Its units are private to the curve and
are never displayed as an objective universal value.

## Normalized Snapshot

The preview adapter combines both CSV files and metadata into the normalized
shape validated by `alert-evidence-snapshot.schema.json`.

Normalization:

- trims surrounding text whitespace;
- preserves source keys as opaque strings;
- converts empty optional cells to `null`;
- converts numeric cells to integers only after strict parsing;
- splits and sorts unique limitation codes;
- emits UTC RFC 3339 timestamps;
- sorts player signals by source player key;
- sorts current picks by overall pick;
- sorts future picks by season offset and round; and
- calculates a SHA-256 hash from canonical JSON with sorted object keys.

The content hash excludes:

- preview identifier;
- import time;
- local database identifiers;
- mapping suggestions;
- user-interface state; and
- private source reference.

Equivalent evidence therefore hashes identically even when previewed again.

## Player Mapping

### Mapping order

1. **Saved exact external mapping**
   - source namespace plus source player key matches one canonical player;
   - preview status is `matched`;
   - no confirmation is required.
2. **Unique identity suggestion**
   - normalized name, position, and compatible team identify one candidate;
   - preview status is `review_required`;
   - the user must explicitly confirm or reject it.
3. **Ambiguous suggestion**
   - more than one canonical candidate remains;
   - preview status is `review_required`;
   - no default candidate is selected.
4. **No candidate**
   - preview status is `unmatched`;
   - the row may be mapped manually or ignored.
5. **Invalid row**
   - schema or domain validation failed;
   - preview status is `invalid`;
   - it cannot be committed.

Name similarity never creates an automatic mapping. Team changes do not break a
saved exact external mapping. A manual mapping decision is local, auditable,
and reusable by later imports in the same namespace.

### Commit boundary

Only `matched` or explicitly confirmed `review_required` rows become committed
player signals.

Ignored, unmatched, ambiguous, rejected, and invalid rows:

- remain visible in the preview counts;
- are excluded from active evidence;
- cannot produce alerts; and
- do not block other valid rows unless every player row is excluded.

Commit requires:

- preview identifier;
- normalized content hash;
- permitted-use confirmation;
- zero invalid metadata or curve rows; and
- at least one committable player signal with an expected-pick window.

## Format Compatibility

The snapshot records the exact source format. A later configuration module
compares it with a draft's frozen league shape.

V1 compatibility states:

- `exact`: all declared shape fields match;
- `family`: league type, draft purpose, quarterback mode, and reception shape
  match, while team count or rounds differ safely;
- `partial`: one non-critical scoring modifier differs;
- `incompatible`: league type, draft purpose, quarterback mode, or draft
  format conflicts; and
- `unknown`: the source omitted a required comparison fact.

The import preview validates the format but does not decide compatibility with
a particular draft.

## V1 Freshness Policy

`alert-freshness-policy.v1.json` is the executable policy source for elapsed-day
evidence:

| Evidence | Fresh through | Aging through | Stale through | Then |
| --- | ---: | ---: | ---: | --- |
| expected selection | 7 days | 21 days | 45 days | expired |
| dynasty market | 7 days | 21 days | 45 days | expired |
| pick value | 30 days | 60 days | 90 days | expired |
| in-season production | 14 days | 30 days | 60 days | expired |

Boundary days are inclusive. Future timestamps are invalid rather than fresh.
Age is calculated using UTC calendar dates from the field timestamp or
snapshot `as_of`, never import time.

Season-labeled offseason production uses:

- current labeled season: `fresh`;
- one prior labeled season: `aging`;
- older labeled season: `stale`; and
- missing or unknown season: `expired`.

Birthdate-derived age risk uses:

- valid non-conflicting birthdate: `fresh`;
- conflicting sources: `stale`; and
- missing or invalid input: `expired`.

Freshness and confidence remain separate. The freshness policy only provides a
state and limitation code; the later engine applies the approved confidence
caps.

## Preview Result Contract

Preview returns:

- schema version;
- preview identifier;
- normalized content hash;
- source and format summaries;
- snapshot freshness states;
- total, valid, matched, review-required, unmatched, ignored, and invalid
  player counts;
- total and valid pick-value counts;
- expected-selection availability;
- pick-curve availability;
- warnings;
- limitation codes; and
- bounded mapping rows without private source payloads.

The response does not echo the entire uploaded files.

## Privacy and Safety

- Source player keys are mapping inputs and remain outside normal alert
  responses.
- Private source reference is stored only after commit and is excluded from the
  content hash, logs, normal responses, and exports.
- Public fixtures use namespace `sanitized_fixture` and fictional identities.
- Normal logs contain only preview identifier, content hash prefix, safe counts,
  duration, and stable error codes.
- CSV rows, player names, source keys, raw values, and filesystem paths are not
  logged.
- The importer does not evaluate formulas, macros, links, or remote content.
- Files are bounded before parsing.

## Error Codes

- `VALIDATION.ALERT_EVIDENCE.INVALID_METADATA`;
- `VALIDATION.ALERT_EVIDENCE.INVALID_HEADER`;
- `VALIDATION.ALERT_EVIDENCE.INVALID_ROW`;
- `VALIDATION.ALERT_EVIDENCE.DUPLICATE_PLAYER`;
- `VALIDATION.ALERT_EVIDENCE.INVALID_RANGE`;
- `VALIDATION.ALERT_EVIDENCE.INVALID_CURVE`;
- `VALIDATION.ALERT_EVIDENCE.FUTURE_TIMESTAMP`;
- `IMPORT.ALERT_EVIDENCE.MAPPING_REQUIRED`;
- `IMPORT.ALERT_EVIDENCE.NO_USABLE_PLAYERS`;
- `IMPORT.ALERT_EVIDENCE.PERMISSION_UNCONFIRMED`;
- `IMPORT.ALERT_EVIDENCE.PREVIEW_CHANGED`; and
- `IMPORT.ALERT_EVIDENCE.PREVIEW_NOT_FOUND`.

Each error says that active evidence and draft state remain unchanged.

## Contract Tests

The contract test must verify:

- both JSON Schemas are themselves valid Draft 2020-12 schemas;
- the normalized fixture validates;
- the freshness policy validates;
- CSV headers match exactly;
- the CSV rows normalize to the committed fixture facts;
- all fixture player keys exist in the sanitized Player Universe namespace;
- player keys and pick asset keys are unique;
- expected-pick and value endpoints are ordered;
- current-pick and future-round curves are monotonic;
- no future timestamps exist;
- missing optional bands remain null;
- all limitations use the approved code format;
- public fixture metadata is synthetic and permission-confirmed;
- no private source reference or real provider marker appears; and
- malformed copies fail representative schema or semantic checks.

Every documented rule branch receives a focused fixture when the importer is
implemented. A global line-coverage percentage does not replace these contract
and workflow gates.

## Acceptance Criteria

1. A nontechnical user can prepare the two documented flat CSV formats.
2. The normalized evidence format is strict, versioned, and provider-neutral.
3. The synthetic snapshot validates against the JSON Schema.
4. The freshness policy is versioned and mechanically validated.
5. Exact external identity is the only automatic player mapping.
6. Name-based matches require explicit review.
7. Ambiguous and unmatched rows cannot produce alerts.
8. Missing optional evidence remains null.
9. Range and curve inversions are rejected.
10. Pick values contain no player assets.
11. Equivalent normalized evidence has one stable content hash.
12. Public artifacts contain no real provider data or private identifiers.
13. All contract tests pass offline.

## Next Implementation Boundary

After this contract is reviewed, Phase 5 step 3 may add pure deterministic
engine fixtures for:

- market-gap ranges;
- return-risk bands;
- freshness lookup;
- confidence caps;
- target-pick windows; and
- pick-only cost-band matching.

No database migration, import endpoint, or desktop component is authorized by
this contract.
