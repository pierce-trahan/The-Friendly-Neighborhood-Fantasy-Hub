# Google AI Studio Bootstrap Instructions

## Purpose of the First AI Studio Session

The first session is for repository import and orientation only. It is not authorization to build, convert, scaffold, deploy, or otherwise modify the project.

The Friendly Neighborhood Fantasy Hub is intentionally documentation-only and is currently in Phase 0: Foundation and Decisions. The application architecture has not been selected.

## Required Reading

Before responding or proposing work, read:

1. `README.md`
2. `PROJECT_ROADMAP.md`
3. `AGENTS.md`
4. `CONTRIBUTING.md`
5. this file

## First-Session Restrictions

During the import-and-orientation session:

- Do not create, edit, delete, rename, move, or convert any repository file.
- Do not generate React, Node.js, Android, Python, database, or deployment scaffolding.
- Do not create `package.json`, install dependencies, configure Cloud Run, connect a database, or add authentication.
- Do not choose an interface framework, database, or deployment model.
- Do not treat the phrase "Draft Lab" or the detailed roadmap as authorization to implement features.
- Do not request, expose, store, or commit API keys, tokens, private league data, or personal information.
- Do not push, export, or sync changes to GitHub.

If AI Studio must create internal workspace metadata to complete the import, keep that metadata inside AI Studio and do not represent it as an approved project change.

## Required First Response

Return only:

1. a concise explanation of the product's purpose;
2. the repository's current implementation status;
3. the V1 scope boundary;
4. the unresolved Phase 0 architecture decisions;
5. any conflicts between AI Studio's preferred web stack and the roadmap's planned technical direction;
6. confirmation that no repository files were changed; and
7. a short list of questions to discuss before implementation.

Then stop and wait for explicit approval.

## Source-of-Truth Rule

GitHub `main` is the source of truth. An AI Studio import is a workspace snapshot, not continuous synchronization.

Future AI Studio changes must use an `ai-studio/short-task-name` branch or an exported handoff that can be reviewed before it reaches `main`. Never overwrite newer GitHub work with an older AI Studio snapshot.

## Exact First Prompt

Copy the following text into the AI Studio Build prompt when importing this repository:

> IMPORT AND ORIENT ONLY. DO NOT BUILD OR MODIFY THE PROJECT.
>
> Use the imported GitHub repository as context. Read `README.md`, `PROJECT_ROADMAP.md`, `AGENTS.md`, `CONTRIBUTING.md`, and `AI_STUDIO_BOOTSTRAP.md` completely before responding.
>
> This repository is intentionally documentation-only and is currently in Phase 0. For this first turn, do not create, edit, delete, rename, move, or convert files. Do not generate application scaffolding, install packages, connect services, deploy, or choose the architecture.
>
> Return only the seven items required by `AI_STUDIO_BOOTSTRAP.md`, confirm that no repository files changed, and then stop for explicit approval.
