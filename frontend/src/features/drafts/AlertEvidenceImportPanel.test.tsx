import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DraftSession } from "../../api/client";
import { AlertEvidenceImportPanel } from "./AlertEvidenceImportPanel";

function response(payload: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  };
}

const draft = {
  id: "draft-1",
  name: "Entropy Draft",
  board_id: "board-1",
  board_name: "Board",
  mode: "live",
  draft_format: "snake",
  third_round_reversal: true,
  team_count: 10,
  round_count: 24,
  user_slot: 2,
  status: "active",
  revision: 7,
  active_pick_count: 0,
  total_picks: 240,
  created_at: "2026-07-29T10:00:00Z",
  updated_at: "2026-07-29T10:00:00Z",
  league_profile_id: null,
  pick_timer_seconds: 120,
  reset_from_session_id: null,
  teams: [],
  current_pick: null,
  user_on_the_clock: false,
  picks_until_user: 1,
  picks: [],
  candidate_total: 0,
  available_count: 0,
  blind_data_hidden: true,
  recommendation_state_present: false,
  completed_at: null,
  reset_at: null,
  recovery_guidance: null,
} satisfies DraftSession;

function preview(permissionConfirmed: boolean) {
  return {
    id: permissionConfirmed ? "preview-confirmed" : "preview-unconfirmed",
    status: "preview",
    content_hash: permissionConfirmed ? "hash-confirmed" : "hash-unconfirmed",
    committed_snapshot_id: null,
    schema_version: 1,
    source: {
      label: "Local market snapshot",
      kind: "user_entered",
      namespace: "local_user",
      permitted_use_confirmed: permissionConfirmed,
      as_of: "2026-07-29T10:00:00Z",
    },
    format: {
      league_type: "dynasty",
      draft_purpose: "startup",
      team_count: 10,
      draft_format: "snake",
      third_round_reversal: true,
      rounds: 24,
      qb_mode: "superflex",
      reception_scoring: "ppr",
      te_premium: true,
    },
    supported_draft_depth: 240,
    total_player_count: 1,
    valid_player_count: 1,
    matched_player_count: 1,
    review_required_player_count: 0,
    unmatched_player_count: 0,
    ignored_player_count: 0,
    invalid_player_count: 0,
    total_pick_value_count: 0,
    valid_pick_value_count: 0,
    expected_selection_available: true,
    pick_curve_available: false,
    freshness_states: { market: "fresh" },
    limitation_codes: permissionConfirmed
      ? ["PICK_CURVE_UNAVAILABLE"]
      : ["PERMISSION_UNCONFIRMED", "PICK_CURVE_UNAVAILABLE"],
    warnings: permissionConfirmed
      ? ["Pick-value evidence was not supplied; costs will be unavailable."]
      : ["Permitted-use confirmation is required before commit."],
    rows: [],
  };
}

const committedSnapshot = {
  id: "snapshot-1",
  content_hash: "hash-confirmed",
  source_label: "Local market snapshot",
  source_kind: "user_entered",
  source_namespace: "local_user",
  source_as_of: "2026-07-29T10:00:00Z",
  imported_at: "2026-07-29T10:02:00Z",
  status: "active",
  schema_version: 1,
  compatibility_state: "not_evaluated",
  freshness_states: { market: "fresh" },
  format: preview(true).format,
  supported_draft_depth: 240,
  mapped_player_count: 1,
  expected_selection_count: 1,
  pick_value_count: 0,
  expected_selection_available: true,
  pick_curve_available: false,
  limitation_codes: ["PICK_CURVE_UNAVAILABLE"],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AlertEvidenceImportPanel", () => {
  it("keeps preview non-mutating and requires a permission-confirmed preview plus explicit commit", async () => {
    const onCommitted = vi.fn();
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/alert-evidence-imports/preview")) {
          const payload = JSON.parse(String(init?.body));
          return response(
            preview(Boolean(payload.metadata.permitted_use_confirmed)),
          );
        }
        if (url.endsWith("/preview-confirmed/commit")) {
          return response(
            { snapshot: committedSnapshot, idempotent: false },
            201,
          );
        }
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <AlertEvidenceImportPanel
        draft={draft}
        onCommitted={onCommitted}
      />,
    );

    fireEvent.click(screen.getByText("Preview / import evidence"));
    const playerFile = new File(
      [
        "source_player_key,display_name,position,expected_pick_low,expected_pick_high\nsafe-1,Marcus Hale,QB,4,8",
      ],
      "players.csv",
      { type: "text/csv" },
    );
    fireEvent.change(screen.getByLabelText("Player-signal CSV"), {
      target: { files: [playerFile] },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Preview evidence" }).closest("form")!,
    );

    expect(
      await screen.findByText(
        "Permitted-use confirmation is required before commit.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Commit evidence" }),
    ).toBeDisabled();
    expect(onCommitted).not.toHaveBeenCalled();
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/commit")),
    ).toBe(false);

    fireEvent.click(
      screen.getByLabelText(
        "I confirm I am permitted to use these files locally for this draft.",
      ),
    );
    expect(
      screen.queryByText(
        "Permitted-use confirmation is required before commit.",
      ),
    ).not.toBeInTheDocument();
    fireEvent.submit(
      screen.getByRole("button", { name: "Preview evidence" }).closest("form")!,
    );

    expect(
      await screen.findByText(
        "Pick-value evidence was not supplied; costs will be unavailable.",
      ),
    ).toBeInTheDocument();
    const commitConfirmation = screen.getByLabelText(
      "Commit this exact preview as an immutable local snapshot.",
    );
    expect(commitConfirmation).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Commit evidence" }),
    ).toBeDisabled();

    fireEvent.click(commitConfirmation);
    fireEvent.click(screen.getByRole("button", { name: "Commit evidence" }));

    await waitFor(() =>
      expect(onCommitted).toHaveBeenCalledWith(committedSnapshot),
    );
    const commitCall = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/preview-confirmed/commit"),
    );
    expect(JSON.parse(String(commitCall?.[1]?.body))).toEqual({
      content_hash: "hash-confirmed",
      permitted_use_confirmed: true,
    });
  });
});
