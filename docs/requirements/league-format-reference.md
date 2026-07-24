# League Format Reference

**Status:** Phase 0 requirements input

**Captured:** 2026-07-24

## Purpose

This document records the league shapes that the application must understand.
It intentionally excludes Sleeper league IDs, account IDs, member names,
rosters, transactions, and chat.

Entropy's 2026 configuration is the canonical V1 target. The comparison
profiles are compatibility references, not equal-priority launch targets.

## Canonical V1 Profile: Entropy 2026

### League

- NFL dynasty league
- 10 teams
- Head-to-head rather than best ball
- Four playoff teams beginning in Week 16
- Pick trading enabled
- Trade deadline in Week 12

### Active lineup

- 1 quarterback
- 2 running backs
- 2 wide receivers
- 1 tight end
- 3 flex positions
- 1 superflex position

### Roster management

- 10 bench positions
- 4 taxi positions
- Taxi eligibility lasts two years and allows veterans
- 3 injured-reserve positions
- $100 FAAB budget
- Two-day waivers clearing Wednesday

### Scoring rules that affect decisions

- Full PPR
- Four points per passing touchdown
- One point per 25 passing yards
- One point per 10 rushing or receiving yards
- Tight ends receive an additional 0.5 points for each receiving first down
- Field goals score 0.1 points per yard
- Standard turnover and team-defense scoring otherwise applies

The tight-end first-down bonus must be modeled as a distinct scoring rule. It
must not be mislabeled or calculated as ordinary tight-end premium PPR.

### Draft behavior

- The 2026 startup is a 10-team, 24-round snake draft
- Pick timer is 120 seconds
- Third-round reversal is enabled
- The long-term league configuration also supports three-round rookie drafts

The application must therefore support more than one draft attached to a
league and must distinguish startup, rookie, and other supplemental drafts.

## Comparison Profiles

The owner's recent Sleeper history provides several useful format variants:

| Profile | Teams | League type | Notable lineup or management differences |
|---|---:|---|---|
| Compact dynasty | 8 | Dynasty superflex | Two starting tight ends, kicker, defense, 10 bench, 4 taxi, 2 IR, six playoff teams |
| Standard redraft | 10 | Redraft | One quarterback, two flex, kicker, defense, 6 bench, 1 IR |
| Large redraft | 12 | Redraft | One quarterback, two flex, kicker, defense, 5 bench, no taxi |
| Shallow dynasty | 10 | Dynasty | One quarterback, two flex, kicker, defense, 5 bench, no taxi or IR |

These variants show that the schema cannot assume:

- a fixed team count;
- superflex is always present;
- kicker and defense are always absent;
- a single tight-end position;
- dynasty always implies taxi positions;
- a fixed bench, IR, playoff, or rookie-draft size; or
- a single draft per league-season.

## Product Requirements Derived From These Profiles

1. Store roster positions as an ordered, repeatable list rather than one
   boolean per position.
2. Store scoring rules as imported key/value rules plus normalized meanings
   used by the recommendation engines.
3. Preserve the original Sleeper rule value so an import can be audited.
4. Give every recommendation a league-profile reference and configuration
   version so changed rules do not silently rewrite old analysis.
5. Support multiple league profiles in storage while allowing one clearly
   selected active league in V1.
6. Treat league, season, and draft as separate records.
7. Allow multiple drafts per league-season with their own team count, rounds,
   timer, order style, and player pool.
8. Make unsupported or unknown Sleeper settings visible instead of dropping
   them.
9. Keep imported account and league identifiers in local application data,
   never in repository fixtures or logs intended for sharing.
10. Build sanitized test fixtures from these shapes before connecting real
    account data to the application.

## Initial Import Boundary

The first Sleeper integration should import only the information needed for
Draft Lab:

- user-selected leagues;
- league and season identity;
- roster construction;
- scoring settings;
- draft configuration and draft order;
- managers and roster ownership when required to render a draft board; and
- picks and current rosters when required for live state.

League chat is not part of the product and must not be imported. Raw personal
identifiers should remain local and should be excluded from normal diagnostic
logs, exported examples, and public bug reports.
