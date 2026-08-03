import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type {
  PostDraftReportComparison as Comparison,
  PostDraftReportSummary,
} from "../../api/client";
import { ReportComparison } from "./ReportComparison";

function summary(
  id: string,
  name: string,
  fingerprint = "a".repeat(64),
): PostDraftReportSummary {
  return {
    id,
    draft_session_id: `draft-${id}`,
    draft_name: name,
    draft_mode: id === "report-2" ? "mock" : "live",
    draft_revision: 24,
    completed_at: "2026-08-03T10:30:00Z",
    generated_at: "2026-08-03T10:31:00Z",
    report_engine_version: "report-engine-v1",
    report_rules_version: "report-rules-v1",
    explanation_template_version: "report-explanations-v1",
    league_shape_fingerprint: fingerprint,
    draft_format: "snake",
    team_count: 12,
    round_count: 24,
    initial_strategy: id === "report-2" ? "balanced" : null,
    final_strategy: id === "report-2" ? "hero_rb" : null,
    strategy_definition_version: id === "report-2" ? "strategy-v1" : null,
    section_summary: { starter_coverage: "supported" },
    limitations: [],
  };
}

const result: Comparison = {
  report_count: 2,
  baseline_report_id: "report-1",
  league_shape_fingerprint: "a".repeat(64),
  report_rules_version: "report-rules-v1",
  reports: [
    {
      report_id: "report-1",
      draft_session_id: "draft-report-1",
      draft_name: "Live Finale",
      draft_mode: "live",
      completed_at: "2026-08-03T10:30:00Z",
      draft_format: "snake",
      team_count: 12,
      round_count: 24,
      initial_strategy: null,
      final_strategy: null,
      strategy_definition_version: null,
      report_engine_version: "report-engine-v1",
      report_rules_version: "report-rules-v1",
      explanation_template_version: "report-explanations-v1",
      league_shape_fingerprint: "a".repeat(64),
    },
    {
      report_id: "report-2",
      draft_session_id: "draft-report-2",
      draft_name: "Mock Rehearsal",
      draft_mode: "mock",
      completed_at: "2026-08-03T10:30:00Z",
      draft_format: "snake",
      team_count: 12,
      round_count: 24,
      initial_strategy: "balanced",
      final_strategy: "hero_rb",
      strategy_definition_version: "strategy-v1",
      report_engine_version: "report-engine-v1",
      report_rules_version: "report-rules-v1",
      explanation_template_version: "report-explanations-v1",
      league_shape_fingerprint: "a".repeat(64),
    },
  ],
  sections: [
    {
      section_key: "strategy_story",
      title: "Strategy story",
      comparison_state: "not_comparable",
      values: [
        {
          report_id: "report-1",
          availability: "not_applicable",
          confidence: "unavailable",
          metrics: {},
          delta_from_first: {},
        },
        {
          report_id: "report-2",
          availability: "supported",
          confidence: "high",
          metrics: { pivot_count: 1 },
          delta_from_first: {},
        },
      ],
      reason_codes: ["MIXED_DRAFT_MODES"],
      limitation_codes: ["SECTION_SUPPORT_MISMATCH"],
      explanation_template_key: "comparison.not_comparable",
      explanation: "Mixed live and mock strategy stories are not comparable.",
    },
  ],
  limitations: ["SECTION_SUPPORT_MISMATCH"],
  explanation_template_key: "comparison.compatible",
  explanation: "Compatible report shapes are aligned section by section.",
};

describe("ReportComparison", () => {
  it("filters incompatible choices and renders explicit not-comparable sections", () => {
    const onToggle = vi.fn();
    const onPreview = vi.fn();
    const reports = [
      summary("report-1", "Live Finale"),
      summary("report-2", "Mock Rehearsal"),
      summary("report-3", "Different League", "b".repeat(64)),
    ];
    const { rerender } = render(
      <ReportComparison
        reports={reports}
        selectedIds={["report-1"]}
        result={null}
        busy={false}
        onToggle={onToggle}
        onPreview={onPreview}
      />,
    );

    expect(screen.getByLabelText(/Different League/)).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/Mock Rehearsal/));
    expect(onToggle).toHaveBeenCalledWith("report-2");

    rerender(
      <ReportComparison
        reports={reports}
        selectedIds={["report-1", "report-2"]}
        result={result}
        busy={false}
        onToggle={onToggle}
        onPreview={onPreview}
      />,
    );
    expect(screen.getByText("Not Comparable")).toBeInTheDocument();
    expect(
      screen.getByText("Mixed live and mock strategy stories are not comparable."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/overall score/i)).not.toBeInTheDocument();
  });
});
