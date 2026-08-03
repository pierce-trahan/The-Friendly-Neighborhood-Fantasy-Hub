import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReportWorkspace } from "./ReportWorkspace";

function response(payload: unknown, ok = true) {
  return { ok, json: async () => payload };
}

const board = {
  id: "board-1",
  name: "Neighborhood Board",
  description: null,
  league_profile_id: "league-1",
  scope: "overall",
  archived: false,
  entry_count: 12,
  created_at: "2026-08-03T10:00:00Z",
  updated_at: "2026-08-03T10:00:00Z",
};

const draftSummary = {
  id: "draft-1",
  name: "Entropy Finale",
  board_id: board.id,
  board_name: board.name,
  mode: "live",
  draft_format: "snake",
  third_round_reversal: true,
  team_count: 3,
  round_count: 2,
  user_slot: 1,
  status: "completed",
  revision: 6,
  active_pick_count: 6,
  total_picks: 6,
  created_at: "2026-08-03T10:00:00Z",
  updated_at: "2026-08-03T10:30:00Z",
};

const draftDetail = {
  ...draftSummary,
  league_profile_id: "league-1",
  pick_timer_seconds: null,
  reset_from_session_id: null,
  teams: [],
  current_pick: null,
  user_on_the_clock: false,
  picks_until_user: null,
  picks: [],
  candidate_total: 20,
  available_count: 14,
  blind_data_hidden: true,
  recommendation_state_present: false,
  completed_at: "2026-08-03T10:30:00Z",
  reset_at: null,
  recovery_guidance: null,
};

const report = {
  id: "report-1",
  draft_session_id: draftSummary.id,
  draft_name: draftSummary.name,
  draft_mode: "live",
  draft_revision: 6,
  completed_at: "2026-08-03T10:30:00Z",
  generated_at: "2026-08-03T10:31:00Z",
  report_engine_version: "report-engine-v1",
  report_rules_version: "report-rules-v1",
  explanation_template_version: "report-explanations-v1",
  league_shape_fingerprint: "a".repeat(64),
  summary: { total_user_picks: 2 },
  section_summary: { long_term_value: "unavailable" },
  sections: [
    {
      section_key: "starter_coverage",
      title: "Starter coverage",
      availability: "supported",
      confidence: "high",
      metrics: { filled_starters: 2, unfilled_starters: 1 },
      reason_codes: ["FROZEN_ROSTER"],
      limitation_codes: [],
      explanation_template_key: "starter.coverage",
      explanation: "Saved eligibility fills two configured starter slots.",
      safe_provenance: {},
    },
    {
      section_key: "long_term_value",
      title: "Long-term value",
      availability: "unavailable",
      confidence: "unavailable",
      metrics: {},
      reason_codes: [],
      limitation_codes: ["APPROVED_EVIDENCE_UNAVAILABLE"],
      explanation_template_key: "unsupported.long_term",
      explanation: "Approved long-term evidence is unavailable.",
      safe_provenance: {},
    },
  ],
  roster: [
    {
      player_id: "player-1",
      display_name: "Marcus Hale",
      overall_pick: 1,
      round_number: 1,
      primary_position: "QB",
      fantasy_positions: ["QB"],
      starter_assignment: "QB",
      saved_personal_rank: 1,
      saved_tier_order: 1,
      saved_favorite: true,
    },
  ],
  moments: [],
  limitations: ["APPROVED_EVIDENCE_UNAVAILABLE"],
  comparison_eligible: true,
  export_available: true,
  available_actions: ["compare", "export_html"],
};

const reportSummary = {
  id: report.id,
  draft_session_id: report.draft_session_id,
  draft_name: report.draft_name,
  draft_mode: report.draft_mode,
  draft_revision: report.draft_revision,
  completed_at: report.completed_at,
  generated_at: report.generated_at,
  report_engine_version: report.report_engine_version,
  report_rules_version: report.report_rules_version,
  explanation_template_version: report.explanation_template_version,
  league_shape_fingerprint: report.league_shape_fingerprint,
  draft_format: "snake",
  team_count: 3,
  round_count: 2,
  initial_strategy: null,
  final_strategy: null,
  strategy_definition_version: null,
  section_summary: report.section_summary,
  limitations: report.limitations,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReportWorkspace", () => {
  it("requires confirmation, generates explicitly, and exposes safe detail export", async () => {
    let generated = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url === "/api/v1/boards?include_archived=false") {
        return response({ items: [board] });
      }
      if (url === "/api/v1/boards/board-1/draft-sessions") {
        return response({ items: [draftSummary] });
      }
      if (url.startsWith("/api/v1/boards/board-1/post-draft-reports?")) {
        return response({
          items: generated ? [reportSummary] : [],
          total: generated ? 1 : 0,
          limit: 100,
          offset: 0,
        });
      }
      if (url === "/api/v1/draft-sessions/draft-1" && method === "GET") {
        return response(draftDetail);
      }
      if (
        url === "/api/v1/draft-sessions/draft-1/post-draft-reports" &&
        method === "POST"
      ) {
        generated = true;
        return response({ idempotent: false, report });
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<ReportWorkspace />);

    expect(await screen.findByText("Entropy Finale")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([, init]) => init?.method === "POST"),
    ).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Prepare report" }));
    expect(
      await screen.findByRole("heading", {
        name: "Generate report for Entropy Finale?",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/completed revision/)).toHaveTextContent("6");

    fireEvent.click(screen.getByRole("button", { name: "Generate saved report" }));
    expect(
      await screen.findByRole("heading", { name: "Entropy Finale", level: 2 }),
    ).toBeInTheDocument();
    expect(screen.getByText("Availability: Supported")).toBeInTheDocument();
    expect(screen.getByText("Availability: Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Approved long-term evidence is unavailable.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Export HTML" })).toHaveAttribute(
      "href",
      "/api/v1/post-draft-reports/report-1/export.html",
    );
    expect(screen.queryByText(/overall score/i)).not.toBeInTheDocument();
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(post?.[1]?.body).toBe(
        JSON.stringify({
          draft_revision: 6,
          expected_completed_at: "2026-08-03T10:30:00Z",
        }),
      );
    });
  });
});
