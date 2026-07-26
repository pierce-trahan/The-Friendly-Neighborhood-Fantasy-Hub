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

Phase 0 is complete: the repository contains a production-shaped local launch
proof with configuration persistence, a sanitized offline Entropy profile, and
a React status screen.

Phase 1 is complete: the Hub now has a canonical player universe, conservative
identity matching, persisted import review, manual correction, and CSV
import/export.

Phase 2A is building the authoritative personal-board foundation for tiers,
notes, favorites, and manual order. See the
[personal board specification](docs/specs/phase-2-personal-board.md) for its
storage, API, reversibility, privacy, and acceptance rules.

## Local Setup

Requirements:

- Python 3.12 or newer
- Node.js 22 or newer

From PowerShell in the repository:

```powershell
.\scripts\bootstrap.ps1
.\scripts\run.ps1
```

After setup, `Launch Friendly Hub.cmd` provides the same local launch path by
double-click. The launcher starts the private local service and opens
`http://127.0.0.1:8765` in the normal browser.

Development and verification commands:

```powershell
.\scripts\dev.ps1
.\scripts\verify.ps1
```

Production data is stored outside the repository under
`%LOCALAPPDATA%\FriendlyNeighborhoodFantasyHub\`. Automated tests use temporary
directories and never touch that production location.

## Accepted Technical Direction

- Local-browser application with a React and TypeScript frontend
- Python and FastAPI backend
- SQLite as the authoritative local application database
- Sleeper and public-data imports with a dedicated player-ID normalization layer
- Deterministic, inspectable scoring engines
- One local launcher that serves the application and opens it in the user's browser
- No required cloud service for core draft-night workflows

See [ADR-001](docs/adr/0001-local-browser-application-architecture.md) for the decision and tradeoffs. Traditional desktop packaging may be reconsidered during draft-night hardening if time permits.

Entropy's sanitized 2026 settings are the canonical V1 league profile. See the
[league format reference](docs/requirements/league-format-reference.md) for
the target roster, scoring, draft behavior, comparison formats, and privacy
boundary. The versioned local storage and import model is recorded in
[ADR-002](docs/adr/0002-local-data-and-configuration-model.md). The modular
repository boundary is recorded in
[ADR-003](docs/adr/0003-repository-and-module-structure.md), with the
[errors and logging standard](docs/standards/errors-and-logging.md) defining
how failures protect saved work and communicate recovery steps.

## Development Workflow

GitHub is the shared source of truth for work performed locally, in Codex, or in Google AI Studio. See [CONTRIBUTING.md](CONTRIBUTING.md) for the one-task, one-branch workflow, [AGENTS.md](AGENTS.md) for shared AI guardrails, [AI_STUDIO_BOOTSTRAP.md](AI_STUDIO_BOOTSTRAP.md) for the safe first AI Studio import, and the [AI Studio collaboration workflow](docs/workflows/ai-studio-collaboration.md) for the ongoing design and audit loop.

## License

This project is licensed under the [MIT License](LICENSE).
