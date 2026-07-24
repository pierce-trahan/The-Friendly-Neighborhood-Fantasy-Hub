# AI Collaboration Guide

These instructions apply to every AI assistant and coding environment working in this repository.

## Start Here

- Read `README.md`, `PROJECT_ROADMAP.md`, `CONTRIBUTING.md`, `docs/adr/0001-local-browser-application-architecture.md`, and any environment-specific bootstrap instructions before making changes.
- Treat the GitHub `main` branch as the shared source of truth.
- The project is currently in Phase 0: Foundation and Decisions.
- Do not silently choose an application framework, database, or deployment model. Record and approve the architecture decision before generating the application skeleton.

## Working Rules

- Use one task branch per piece of work.
- Keep each change limited to the agreed task.
- Do not overwrite changes that another person or AI environment may own.
- Prefer small, clearly named commits that can be reviewed or reversed.
- Verify work against the roadmap's acceptance criteria before calling it complete.
- Explain important decisions, tradeoffs, and uncertainties in plain language.

## Product Guardrails

- Personal rankings and manual overrides remain authoritative.
- Recommendations must be explainable and must distinguish personal conviction from market evidence.
- Do not introduce automated drafting, required cloud infrastructure, or other out-of-scope features without an explicit roadmap decision.
- Treat stale, missing, or ambiguous data as a visible confidence problem rather than silently guessing.

## Security and Privacy

- This is a public repository. Treat every committed file as publicly visible.
- Never commit API keys, access tokens, passwords, private league data, or personal information.
- Keep local secrets in ignored environment files such as `.env`, or in the secret manager provided by the active development environment.
- Use fake or deliberately sanitized data for examples and tests until a privacy and storage decision is documented.
