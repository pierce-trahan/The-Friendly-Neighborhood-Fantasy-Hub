# The Friendly Neighborhood Fantasy Hub

> A local-first fantasy football intelligence platform that helps serious dynasty and redraft players make better decisions—not by replacing judgment, but by teaching better processes.

## Vision

Fantasy football tools often present average draft position, consensus rankings, or a single trade value as if each were an answer. The Friendly Neighborhood Fantasy Hub treats them as signals.

The Hub is a private, local-first decision-support application built to help players:

- develop and trust their own evaluations;
- understand value, uncertainty, and strategic tradeoffs;
- practice different roster-building philosophies;
- recognize where personal, league, and market opinions diverge; and
- improve through deliberate mock drafts and transparent feedback.

The product's defining question is:

> **How should I think about this decision?**

It will not draft for the user. It will make the user's reasoning more visible, structured, and informed.

## Product Principles

1. **User judgment wins.** Manual rankings, tiers, and overrides remain authoritative.
2. **Personal rankings come first.** The user's board—not consensus ADP—is the center of the experience.
3. **Value replaces anchoring.** ADP may inform private calculations but should not dominate the interface.
4. **Context beats absolutes.** Advice changes with league format, scoring, roster construction, strategy, and draft state.
5. **Every recommendation is explainable.** Alerts show their inputs, assumptions, confidence, and downside.
6. **Drafting is learning.** Every mock should teach the user something about players, strategy, or risk.
7. **Local-first and dependable.** Draft-night workflows must remain fast and useful without cloud infrastructure.

## Initial Product Scope

The first release is the **Draft Lab**, focused on:

- a relevant, normalized player universe;
- personal boards, tiers, notes, and manual overrides;
- a pairwise-comparison **Gut ELO** ranking tool;
- blind and alphabetical draft-board views;
- mock and live draft-state controls;
- strategy guidance that nudges without forcing;
- transparent value and “your guy may not return” alerts;
- pick-only trade-up guidance; and
- post-draft roster reports.

Waiver recommendations, full player-and-pick trade calculators, projections, and season management are intentionally deferred.

## Roadmap

See [PROJECT_ROADMAP.md](PROJECT_ROADMAP.md) for the complete product roadmap and the detailed V1 delivery plan.

## Project Status

This repository begins with product direction and scope. Implementation will proceed module by module, with each module specified, built, tested against acceptance criteria, and audited before the next begins.

## Planned Technical Direction

- Python application
- Local database such as SQLite or DuckDB
- Sleeper and public-data imports with a dedicated player-ID normalization layer
- Deterministic, inspectable scoring engines
- A simple local interface optimized for draft-night speed

Specific framework choices remain subject to a short architecture decision before implementation.

## License

This project is licensed under the [MIT License](LICENSE).

