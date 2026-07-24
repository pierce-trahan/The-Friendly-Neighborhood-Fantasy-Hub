# Codex and Google AI Studio Collaboration Workflow

## Purpose

This workflow lets Pierce and Codex discuss product design, use Google AI Studio for rapid visual prototyping, and return reviewed work to GitHub without requiring Pierce to copy prompts, files, or responses between tools.

GitHub `main` remains the source of truth. Google AI Studio workspaces are treated as snapshots and prototype environments.

## Standard Loop

### 1. Discuss

Pierce and Codex define:

- the user problem;
- the desired interaction;
- relevant fantasy-football rules and assumptions;
- visual references;
- scope boundaries; and
- acceptance criteria.

No implementation begins until the task is narrow enough to review.

### 2. Prepare

Codex:

- checks the current GitHub state;
- identifies the files and interfaces that may change;
- prepares the AI Studio prompt and any supporting reference files;
- states what AI Studio must not change; and
- establishes the expected handoff format.

### 3. Prototype in AI Studio

Codex operates the authorized AI Studio workspace to:

- provide the scoped prompt;
- guide the visual and interaction work;
- inspect progress;
- prevent out-of-scope architecture or backend changes; and
- use the live preview to evaluate the experience with Pierce.

AI Studio must not push directly to `main`.

### 4. Audit

Before integration, Codex reviews:

- every created, modified, and deleted file;
- dependencies and licenses;
- secrets and personal data;
- accessibility and keyboard behavior;
- responsive behavior;
- error and loading states;
- compatibility with the accepted architecture;
- test impact; and
- whether the result actually satisfies the acceptance criteria.

Generated code is a candidate, not an approved result.

### 5. Integrate

Approved work is transferred through one of these reviewable paths:

- an `ai-studio/short-task-name` GitHub branch;
- an exported archive that Codex integrates on an `agent/short-task-name` branch; or
- a small manually reconstructed change when the generated output is not production-ready.

Codex then runs the relevant checks and opens a pull request. GitHub `main` changes only after review.

### 6. Verify

Pierce and Codex evaluate the completed behavior in the appropriate preview or local application. The handoff records:

- what changed;
- what was verified;
- what was intentionally deferred; and
- any remaining risks.

## Using NFL Draft Hub R&D

UI concepts developed for the NFL Draft Hub may be used as design research for this project. Reuse should focus on transferable interaction patterns such as:

- player tables and cards;
- draft clocks and pick navigation;
- team and position filters;
- board density and hierarchy;
- comparison views;
- alert presentation; and
- keyboard-friendly draft controls.

Concepts should be adapted to the fantasy product's goals rather than copied automatically. The Fantasy Hub keeps its own data model, terminology, product principles, and acceptance criteria.

## Stop Conditions

AI Studio work stops and returns to discussion when:

- a request would choose or change the architecture;
- the proposed change touches authoritative backend or database behavior;
- generated work expands beyond the defined task;
- a secret, private data, or paid external service would be introduced;
- GitHub contains newer work than the AI Studio snapshot; or
- the preview looks convincing but the underlying code cannot be audited safely.
