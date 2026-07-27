# Desktop UI Direction: Editorial Draft Workstation

**Status:** Approved design reference

**Date:** 2026-07-26

## Outcome

The Friendly Neighborhood Fantasy Hub should look and behave like a specialized
football operations instrument. It should not resemble a generic subscription
dashboard assembled from interchangeable cards.

This direction is based on the user-supplied UI research notes and NFL Draft Hub
visual reference board. The reference board is a visual-language source, not a
feature commitment.

The working phrase is:

> An editorial draft workstation with terminal-like density, fast direct
> manipulation, and visible state confidence.

## Current Product Scope

The visual system applies to the local desktop browser application and its
currently supported surfaces:

- overview and local-system status;
- Player Universe and import review;
- Personal Boards;
- Gut ELO comparisons and results; and
- future draft-room, mock, strategy, alert, and reporting modules as they are
  approved.

Desktop is the current product target. Phone-specific composition is deferred.
The app should remain structurally usable at narrower widths, but mobile polish
is not an acceptance gate.

## Reference Ideas We Are Adopting

### Editorial hierarchy

- Typography and rules organize the page before containers do.
- Headings feel like section plates in a scouting publication.
- Utility labels are compact, uppercase, and mechanical.
- Explanatory copy is present but does not dominate the data surface.

### Professional workstation density

- The interface favors persistent context over a sequence of oversized cards.
- Tables and ordered rows are first-class operating surfaces.
- Navigation, filters, controls, and state are visible without decorative
  whitespace.
- Keyboard shortcuts are displayed next to the actions they control.

### Restrained brutalism

- Geometry is square or nearly square.
- Borders and dividers are explicit.
- Controls feel mechanical and dependable.
- One accent color carries active state and emphasis.
- The app avoids glossy gradients, floating glass cards, and soft pill-heavy
  framing.

### Mode-specific composition

Different jobs may use different layouts:

- Player Universe: dense table and import-review queue.
- Personal Board: ordered board-builder surface.
- Gut ELO: focused comparison canvas plus result table.
- Draft Room: board, pick state, and persistent draft context.

The shared shell and visual grammar remain consistent without forcing every
module into the same dashboard grid.

## Supported Visual Rules

1. Default radius is `0-4px`.
2. The primary accent is restrained equipment orange.
3. Near-black, charcoal, warm paper, and muted metal tones form the base.
4. Display headings use a condensed editorial face available from system
   fonts; utility labels and data use a monospace stack.
5. Body copy uses a compact, highly readable sans-serif stack.
6. Tables use tight rows, strong column labels, and visible separators.
7. Buttons express hierarchy through fill, border, and label rather than size.
8. Status is written plainly and reinforced with a small color signal.
9. Data and state should appear before decorative explanation.
10. The application shell remains usable offline without loading web fonts,
    icon packs, or remote assets.

## Patterns to Remove

- 20-28px default corner radii;
- a card around every subsection;
- large decorative gradients;
- giant landing-page typography inside workspaces;
- excessive pill controls;
- glassmorphism and blur as the primary surface treatment;
- sparse marketing-page spacing;
- decorative metrics that do not support a decision; and
- multiple competing accent colors.

## Information Hierarchy

### Global shell

The top of the app provides:

- product identity;
- current phase or operating context;
- local database state; and
- compact primary navigation.

It should resemble the title strip and command rail of a desktop tool, not a
marketing hero.

### Workspace header

Each module begins with:

- an indexed phase or mode label;
- the workspace name;
- one short operating description; and
- a plain local/privacy/state indicator where relevant.

### Operating surface

The primary job fills the majority of the canvas. Sidebars hold selection and
context, not unrelated summary cards.

### Feedback

Notices appear as narrow status strips with a strong left rule. Errors explain
what remained unchanged and how to recover.

## Data Presentation

- Personal rank remains visually distinct from calculated or contextual
  signals.
- Gut ELO results continue to state that the Personal Board is unchanged.
- Missing, stale, or ambiguous data remains visible.
- ADP, market rank, projections, and provider identifiers do not appear unless
  a later approved module explicitly introduces them.
- Notes and private league data do not enter public fixtures, normal errors, or
  public repository assets.

## Interaction Rules

- Primary actions must be reachable without opening a decorative menu.
- Destructive or high-consequence actions retain explicit confirmation.
- Fast-entry workflows expose keyboard controls.
- Selection state uses the single accent plus a border or rule, not color
  alone.
- Hover treatments may sharpen contrast but must not shift layout.
- Saved state is acknowledged without obscuring the operating surface.

## Explicitly Unsupported Reference Elements

The following imagery on the reference board is not part of this UI pass:

- prospect headshots;
- college scouting grades or percentile metrics;
- film playback, clips, snaps, timecodes, or route diagrams;
- scouting-source provenance inspectors;
- injury, testing, production, or combine databases;
- analytical charts, maps, clusters, or player-comparison metrics;
- college or NFL logos and licensed imagery;
- cloud data sources;
- collaboration, sharing, or multi-user ownership;
- reports for modules that have not been specified; and
- a user-configurable widget canvas.

Those patterns may be reconsidered only when the corresponding product and data
contracts are approved.

## Acceptance Criteria

1. The existing Phase 1 and Phase 2 workflows remain functionally unchanged.
2. The desktop application no longer reads as a soft, card-based SaaS landing
   page.
3. Global navigation and local database status are immediately visible.
4. Workspaces use explicit rules, compact typography, and low-radius geometry.
5. Tables and ordered lists become denser without losing accessible labels or
   keyboard focus.
6. Gut ELO retains a focused comparison canvas and clearly separate result
   table.
7. The interface loads without remote fonts, icons, or images.
8. Existing automated tests, type checks, production build, and dependency
   audit pass.
9. A live desktop visual review shows no clipping, accidental overflow, or
   unreadable contrast.

## Deferred

- a packaged desktop window;
- mobile-specific redesign;
- resizable or user-saved pane layouts;
- a persistent player inspector;
- a command palette;
- global shortcut customization;
- light/paper theme switching; and
- a signature visualization such as a board-history graph or scouting atlas.
