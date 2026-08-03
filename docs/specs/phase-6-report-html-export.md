# Phase 6 Standalone Safe HTML Report Export

**Status:** Bounded implementation contract

**Date:** 2026-08-03

**Parent specification:** [Phase 6 Post-Draft Report](phase-6-post-draft-report.md)

**Predecessor:** [Phase 6 Compatible Report Comparison Preview](phase-6-report-comparison.md)

## Outcome

This contract implements Phase 6 step 9. One immutable saved report may be
downloaded as a standalone, print-friendly UTF-8 HTML document that works
without a network connection.

The export is the digital equivalent of a self-contained scouting binder: all
approved text and styling travel inside one file. It contains no JavaScript,
remote request, external asset, tracking, upload, share workflow, PDF renderer,
or database mutation.

## API Contract

`GET /api/v1/post-draft-reports/{report_id}/export.html`

Success returns:

- status `200`;
- media type `text/html; charset=utf-8`;
- `Content-Disposition: attachment`;
- a filename derived from a bounded sanitized draft-name slug and completion
  date; and
- no persisted export record.

Missing reports retain `REPORT_NOT_FOUND`. A rendering or size failure returns
`REPORT_EXPORT_FAILED` and leaves the saved report intact.

## Document Contract

The document uses semantic `header`, `main`, `section`, heading, table, list,
and footer elements. It includes:

1. frozen report identity, mode, completion time, and version limits;
2. roster inventory and starter assignments;
3. every registered section in registry order with availability, confidence,
   explanation, safe metrics, limitations, and safe provenance;
4. bounded saved decision moments; and
5. the evidence-limits section.

Inline print CSS preserves readable source order. A restrictive inline content
security policy prohibits network content, scripts, frames, forms, and images.

## Escaping and Privacy

Every user-controlled or saved display string is HTML-escaped, including draft,
player, position, slot, source-label, explanation, limitation, metric-key, and
moment text. Generated filenames contain lowercase ASCII letters, digits, and
single hyphens only.

The renderer consumes only `PostDraftReportRead`; it never rereads draft,
board, mock, alert, or evidence source tables. Therefore the export cannot add:

- Personal Board or strategy notes;
- provider or source player ids;
- private evidence references or raw rows;
- CPU seed, alternatives, or random audit;
- manager internal references;
- comparison data, grades, projections, or recommendations; or
- claims that an alert caused a pick or a trade occurred.

## Limits and Failure Rules

- encoded output is below `2 MiB`;
- normal export target is below `1 second`;
- no network operation is permitted;
- no report or source row is created, updated, or deleted;
- an invalid nested safe value fails closed rather than using object repr; and
- export logging records ids, byte count, and duration, never names or roster
  contents.

## Verification Strategy

Unit coverage proves recursive escaping, deterministic filename generation,
semantic structure, print CSS, content-security policy, safe nested metrics,
and rejection of unsupported values.

API coverage proves headers, complete section order, roster and moment output,
missing-report behavior, no scripts/remote references, privacy exclusions,
sub-second rendering, size cap, and identical database counts before and after
export. Existing draft CSV tests remain unchanged and Phase 6-free.

The full repository verifier remains the publication gate.

## Acceptance Criteria

1. A saved report exports as one standalone UTF-8 HTML attachment.
2. The filename is bounded, deterministic, and safe for local filesystems.
3. Every registered report section appears in order.
4. Roster rows and bounded saved moments are represented semantically.
5. All display text is escaped exactly once.
6. The document contains no script, external asset, form, frame, remote URL, or
   tracking mechanism.
7. The evidence-limits section and all unavailable explanations remain visible.
8. Private, raw, provider, random, manager, predictive, grading, winner, and
   hindsight content is absent.
9. Export performs no database mutation and creates no persisted export row.
10. Output remains below `2 MiB` and normal rendering below `1 second`.
11. The regular draft CSV remains Phase 6-free.
12. The full repository verification gate passes.

## Next Implementation Boundary

Phase 6 step 10 implements this boundary in the
[desktop Reports workspace contract](phase-6-desktop-reports-workspace.md).
The remaining boundary is the final specification and offline workflow audit,
without new report calculations, persistence, grading, projections, or cloud
behavior.
