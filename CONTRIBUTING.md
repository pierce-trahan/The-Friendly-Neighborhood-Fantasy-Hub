# Contributing and AI Workspace Workflow

This project may be edited from several environments, including Codex and Google AI Studio. GitHub is the shared source of truth.

The detailed handoff loop is documented in [docs/workflows/ai-studio-collaboration.md](docs/workflows/ai-studio-collaboration.md).

## Architecture Gate

The repository currently contains product direction, not an implemented application. The accepted application direction is recorded in [ADR-001](docs/adr/0001-local-browser-application-architecture.md). Before either environment generates application code, the remaining Phase 0 work must specify:

- the application and data-directory structure;
- configuration and backup formats; and
- logging and user-facing error conventions.

This prevents two environments from building incompatible versions of the same product.

## One-Task, One-Branch Workflow

1. Start from the latest `main`.
2. Create a branch for one clearly defined task.
3. Let only one environment actively own that branch at a time.
4. Make small, scoped changes and verify them locally.
5. Push the branch and open a draft pull request.
6. Review the changes and acceptance criteria before merging into `main`.

Suggested branch names:

- Codex: `agent/short-task-name`
- Google AI Studio: `ai-studio/short-task-name`
- Manual work: `work/short-task-name`

Avoid having Codex and Google AI Studio edit the same files simultaneously. That is the software equivalent of two editors cutting different versions of the same scene.

## Handoff Format

Every handoff should state:

- **Branch:** the branch containing the work
- **Changed:** what was added, removed, or altered
- **Verified:** the checks that were run
- **Open questions:** decisions or risks that remain

## Secrets and Private Data

- Never commit secrets, tokens, passwords, `.env` files, or real private league data.
- Use `.env` locally when the chosen application stack needs environment variables.
- Use Google AI Studio's Secrets panel for credentials used inside that environment.
- Before committing, inspect the staged changes and confirm that no secret or personal data is included.
- If a secret is committed, rotate it immediately. Removing it in a later commit does not remove it from Git history.

The existing `.gitignore` excludes common local secret, database, cache, backup, and log files.
