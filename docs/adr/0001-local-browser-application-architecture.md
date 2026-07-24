# ADR-001: Local-Browser Application Architecture

**Status:** Accepted

**Date:** 2026-07-24

**Deciders:** Pierce Trahan and Codex

## Context

The Friendly Neighborhood Fantasy Hub must be dependable during live fantasy drafts, useful without an internet connection after data has been refreshed, and understandable to a non-technical user. It must preserve manual control, autosave important state, recover cleanly after interruption, and explain its recommendations.

The product also needs a polished, keyboard-friendly interface. Google AI Studio is available as a rapid React design and prototyping environment, but its preferred hosted React/Node.js workflow does not by itself satisfy the Hub's local-first storage and draft-night reliability requirements.

The V1 goal is a realistic local application. A packaged desktop version is desirable only if it does not delay the Draft Lab.

## Decision

V1 will use a local-browser architecture:

- **Frontend:** React with TypeScript, built as static browser assets.
- **Frontend build tooling:** Vite unless the application skeleton reveals a concrete reason to choose another tool.
- **Backend:** Python with FastAPI.
- **Primary database:** SQLite.
- **Production shape:** One local application process serves both the API and the built frontend.
- **Launch experience:** A simple launcher starts the local service and opens the Hub in the user's normal browser.
- **Network posture:** Core draft preparation, board management, mock drafting, live draft state, recovery, and reporting work offline after source data has been refreshed.
- **Packaging:** A traditional desktop package may be evaluated during Phase 7 hardening, but it is not a V1 prerequisite.

SQLite is the operational source of truth for player identity mappings, settings, personal boards, draft state, comparisons, mock history, and reports. DuckDB is deferred as a possible later analytical companion; it will not replace SQLite for application state.

The production application will not require Gemini or another generative-AI service to make fantasy decisions. Deterministic and inspectable engines remain the default.

## Development Boundaries

### Google AI Studio

Google AI Studio is the visual prototyping and frontend exploration environment. It may:

- explore page layouts and interaction patterns;
- prototype React components;
- help evaluate responsive behavior and accessibility;
- produce reviewable candidate frontend changes; and
- provide a live preview for design conversations.

It does not own:

- the production architecture;
- the SQLite schema;
- authoritative Python business logic;
- deployment decisions;
- GitHub `main`; or
- an automatically synchronized copy of the repository.

### Codex and the Local Repository

Codex is responsible for:

- turning product discussions into scoped specifications and acceptance criteria;
- preparing prompts and context for AI Studio;
- auditing generated code, dependencies, security, and repository impact;
- integrating approved frontend work with the Python backend;
- implementing and testing deterministic business logic;
- maintaining migrations, backups, recovery, and packaging; and
- publishing reviewable GitHub branches and pull requests.

### Product Owner

Pierce remains the final authority for product direction, user experience, fantasy-football assumptions, and whether a reviewed change matches the intended experience. Routine tool handoffs between Codex and AI Studio should not require Pierce to copy information manually.

## Options Considered

| Option | Complexity | Local reliability | UI flexibility | AI Studio fit | Assessment |
|---|---:|---:|---:|---:|---|
| React + FastAPI + SQLite | Medium | High | High | High for frontend | Accepted |
| React + Electron + SQLite | Medium-high | High | High | Medium-high | Reconsider only if desktop packaging becomes essential |
| Python + Streamlit + SQLite | Low | High | Medium-low | Low | Fast prototype, but weak fit for the intended draft room |
| React + browser-only storage | Low-medium | Medium | High | High | Storage and recovery are not dependable enough for the authoritative V1 state |
| AI Studio React/Node hosted app | Low initially | Low for offline use | High | Native | Conflicts with the local-first release requirement |

## Trade-off Analysis

The accepted design uses two languages, which adds a frontend/backend boundary. That cost is justified because it gives AI Studio a natural React surface while keeping data normalization, simulations, scoring engines, imports, and local persistence in Python.

Electron would provide a traditional desktop window and a single TypeScript-oriented stack, but it adds packaging, application-process, and security complexity before those costs are necessary. Streamlit would be faster to scaffold, but its interaction model would constrain the polished, fast-entry draft room described in the roadmap.

## Consequences

### What becomes easier

- Building a polished and responsive draft-room interface.
- Keeping the authoritative database on the user's computer.
- Developing deterministic fantasy-football engines in Python.
- Reviewing AI Studio output as a bounded frontend contribution.
- Serving the finished frontend and API from one local process.
- Deferring packaging without blocking a usable V1.

### What becomes harder

- Coordinating TypeScript and Python development environments.
- Defining and testing the API contract between the frontend and backend.
- Converting AI Studio prototypes into production-ready repository changes.
- Creating a one-click launcher that hides local server details from the user.

### What must be revisited

- Whether Phase 7 should package the Hub as a traditional desktop application.
- Whether later market-history analysis justifies adding DuckDB.
- Whether multi-device or hosted access becomes a real requirement after V1.

## Action Items

1. [x] Record the application architecture and tool boundaries.
2. [x] Specify the initial repository and module structure.
3. [x] Define the league settings and application configuration schemas.
4. [x] Define SQLite ownership, migration, backup, and recovery conventions.
5. [x] Define logging and user-facing error conventions.
6. [x] Create a small sanitized offline test dataset.
7. [x] Build a minimal launch/configuration persistence proof before analytical features.
