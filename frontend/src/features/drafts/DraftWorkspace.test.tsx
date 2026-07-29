import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DraftSession } from "../../api/client";
import { DraftWorkspace } from "./DraftWorkspace";

function response(payload: unknown, ok = true) {
  return {
    ok,
    status: ok ? 200 : 400,
    json: async () => payload,
  };
}

const board = {
  id: "board-1",
  name: "Draft Board",
  description: null,
  league_profile_id: null,
  scope: "overall" as const,
  archived: false,
  entry_count: 3,
  created_at: "2026-07-26T10:00:00Z",
  updated_at: "2026-07-26T10:00:00Z",
};

const draft: DraftSession = {
  id: "draft-1",
  name: "Entropy Draft",
  board_id: board.id,
  board_name: board.name,
  mode: "live",
  draft_format: "snake",
  third_round_reversal: true,
  team_count: 2,
  round_count: 2,
  user_slot: 2,
  status: "active",
  revision: 7,
  active_pick_count: 0,
  total_picks: 4,
  created_at: "2026-07-26T10:00:00Z",
  updated_at: "2026-07-26T10:00:00Z",
  league_profile_id: null,
  pick_timer_seconds: 120,
  reset_from_session_id: null,
  teams: [
    { draft_slot: 1, display_name: "Alpha", is_user: false },
    { draft_slot: 2, display_name: "Your Team", is_user: true },
  ],
  current_pick: {
    overall_pick: 1,
    round_number: 1,
    pick_in_round: 1,
    selecting_slot: 1,
    selecting_team: "Alpha",
  },
  user_on_the_clock: false,
  picks_until_user: 1,
  picks: [],
  candidate_total: 2,
  available_count: 2,
  blind_data_hidden: true,
  recommendation_state_present: false,
  completed_at: null,
  reset_at: null,
  recovery_guidance: null,
};

const candidates = {
  view: "blind" as const,
  total: 2,
  limit: 200,
  offset: 0,
  items: [
    {
      player_id: "player-1",
      display_name: "Marcus Hale",
      primary_position: "QB",
      fantasy_positions: ["QB"],
      team: "CHI",
      player_status: "active",
      is_rookie: false,
      rookie_class: 2022,
      drafted_overall_pick: null,
    },
    {
      player_id: "player-2",
      display_name: "Devin Cross Jr.",
      primary_position: "RB",
      fantasy_positions: ["RB"],
      team: "ATL",
      player_status: "active",
      is_rookie: false,
      rookie_class: 2024,
      drafted_overall_pick: null,
    },
  ],
};

function summary(session: DraftSession) {
  return {
    id: session.id,
    name: session.name,
    board_id: session.board_id,
    board_name: session.board_name,
    mode: session.mode,
    draft_format: session.draft_format,
    third_round_reversal: session.third_round_reversal,
    team_count: session.team_count,
    round_count: session.round_count,
    user_slot: session.user_slot,
    status: session.status,
    revision: session.revision,
    active_pick_count: session.active_pick_count,
    total_picks: session.total_picks,
    created_at: session.created_at,
    updated_at: session.updated_at,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DraftWorkspace", () => {
  it("guides the user to create a Personal Board when none exists", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(response({ items: [] })),
    );

    render(<DraftWorkspace />);

    expect(
      await screen.findByText("A Personal Board is the call sheet for this room."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Run to my pick" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Advance one CPU pick" }),
    ).not.toBeInTheDocument();
  });

  it("keeps practice sessions in the dedicated Mock Lab", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/v1/boards?include_archived=false") {
          return response({ items: [board] });
        }
        if (url.endsWith("/boards/board-1/draft-sessions")) {
          return response({
            items: [{ ...summary(draft), mode: "mock" as const }],
          });
        }
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftWorkspace />);

    expect(
      await screen.findByRole("button", { name: "Create draft room" }),
    ).toBeEnabled();
    expect(screen.queryByText("Entropy Draft")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Mode")).not.toBeInTheDocument();
  });

  it("submits one editable team name per configured draft slot", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/v1/boards?include_archived=false") {
          return response({ items: [board] });
        }
        if (
          url.endsWith("/boards/board-1/draft-sessions") &&
          init?.method === "POST"
        ) {
          return response(draft);
        }
        if (url.endsWith("/boards/board-1/draft-sessions")) {
          return response({ items: [] });
        }
        if (url.includes("/draft-sessions/draft-1/candidates?")) {
          return response(candidates);
        }
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftWorkspace />);
    fireEvent.change(await screen.findByLabelText("Teams"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByText("Customize team names"));
    fireEvent.change(screen.getByLabelText(/^Team 1 name/), {
      target: { value: "Alpha" },
    });
    fireEvent.change(screen.getByLabelText(/^Team 2 name/), {
      target: { value: "Beta" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create draft room" }));

    await waitFor(() => {
      const createCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).endsWith("/boards/board-1/draft-sessions") &&
          init?.method === "POST",
      );
      expect(createCall).toBeDefined();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        mode: "live",
        team_count: 2,
        team_names: ["Alpha", "Beta"],
      });
    });
  });

  it("optionally attaches a selected evidence snapshot after creating the room", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/v1/boards?include_archived=false") {
          return response({ items: [board] });
        }
        if (
          url.endsWith("/boards/board-1/draft-sessions") &&
          init?.method === "POST"
        ) {
          return response(draft);
        }
        if (url.endsWith("/boards/board-1/draft-sessions")) {
          return response({ items: [] });
        }
        if (url.includes("/alert-evidence-snapshots?")) {
          return response({
            items: [
              {
                id: "snapshot-1",
                source_label: "Neighborhood Synthetic Market",
                source_as_of: "2026-07-28T00:00:00Z",
                freshness_states: { market: "fresh" },
                compatibility_state: "not_evaluated",
              },
            ],
            total: 1,
            limit: 100,
            offset: 0,
          });
        }
        if (
          url.endsWith("/draft-sessions/draft-1/alert-configuration") &&
          init?.method === "POST"
        ) {
          return response({}, true);
        }
        if (url.includes("/draft-sessions/draft-1/candidates?")) {
          return response(candidates);
        }
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftWorkspace />);
    expect(
      await screen.findByRole("button", { name: "Create draft room" }),
    ).toBeEnabled();
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).includes("/alert-evidence-snapshots"),
      ),
    ).toBe(false);

    fireEvent.click(screen.getByText("Decision support (optional)"));
    fireEvent.click(
      await screen.findByLabelText(
        "Attach decision support when this room opens",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "Create draft room" }));

    await waitFor(() => {
      const attachCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).endsWith(
            "/draft-sessions/draft-1/alert-configuration",
          ) && init?.method === "POST",
      );
      expect(JSON.parse(String(attachCall?.[1]?.body))).toEqual({
        draft_revision: 7,
        evidence_snapshot_id: "snapshot-1",
        enabled: true,
        personal_qualifier_mode: "tier_or_favorite",
        eligible_tier_count: 2,
        minimum_conservative_gap: 6,
        snooze_pick_count: 5,
      });
    });
    expect(
      await screen.findByText(
        "Draft room created. Decision support is attached outside Blind view.",
      ),
    ).toBeInTheDocument();
  });

  it("submits exact revision and current-pick guards", async () => {
    const updated: DraftSession = {
      ...draft,
      revision: 8,
      active_pick_count: 1,
      available_count: 1,
      current_pick: {
        overall_pick: 2,
        round_number: 1,
        pick_in_round: 2,
        selecting_slot: 2,
        selecting_team: "Your Team",
      },
      user_on_the_clock: true,
      picks_until_user: 0,
      picks: [
        {
          overall_pick: 1,
          round_number: 1,
          pick_in_round: 1,
          selecting_slot: 1,
          selecting_team: "Alpha",
          player_id: "player-1",
          player_display_name: "Marcus Hale",
          player_position: "QB",
          player_team: "CHI",
          recorded_at: "2026-07-26T10:01:00Z",
          correction_count: 0,
        },
      ],
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/v1/boards?include_archived=false") {
        return response({ items: [board] });
      }
      if (url.endsWith("/boards/board-1/draft-sessions")) {
        return response({ items: [summary(draft)] });
      }
      if (url.endsWith("/draft-sessions/draft-1/candidates?view=blind&include_drafted=false&limit=200&offset=0")) {
        return response(candidates);
      }
      if (url.endsWith("/draft-sessions/draft-1/picks") && init?.method === "POST") {
        return response(updated);
      }
      if (url.endsWith("/draft-sessions/draft-1")) return response(draft);
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftWorkspace />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Draft" }))[0]);
    expect(screen.getByRole("button", { name: "Confirm pick" })).toBeEnabled();
    expect(
      fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).endsWith("/draft-sessions/draft-1/picks") &&
          init?.method === "POST",
      ),
    ).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: "Confirm pick" }));

    await screen.findByText("You are on the clock");
    const pickCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).endsWith("/draft-sessions/draft-1/picks") &&
        init?.method === "POST",
    );
    expect(pickCall).toBeDefined();
    expect(JSON.parse(String(pickCall?.[1]?.body))).toMatchObject({
      revision: 7,
      expected_overall_pick: 1,
      player_id: "player-1",
    });
  });

  it("refreshes server state after a stale rejection without optimistic loss", async () => {
    const serverAdvanced: DraftSession = {
      ...draft,
      revision: 8,
      current_pick: {
        overall_pick: 2,
        round_number: 1,
        pick_in_round: 2,
        selecting_slot: 2,
        selecting_team: "Your Team",
      },
      active_pick_count: 1,
      available_count: 1,
      user_on_the_clock: true,
      picks_until_user: 0,
    };
    let sessionReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/v1/boards?include_archived=false") {
        return response({ items: [board] });
      }
      if (url.endsWith("/boards/board-1/draft-sessions")) {
        return response({ items: [summary(draft)] });
      }
      if (url.includes("/candidates?")) return response(candidates);
      if (url.endsWith("/draft-sessions/draft-1/picks") && init?.method === "POST") {
        return response(
          {
            error: {
              message: "The draft changed before that action could be saved.",
              action: "Refresh the draft room and retry from the current pick.",
            },
          },
          false,
        );
      }
      if (url.endsWith("/draft-sessions/draft-1")) {
        sessionReads += 1;
        return response(sessionReads === 1 ? draft : serverAdvanced);
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftWorkspace />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Draft" }))[0]);
    fireEvent.click(screen.getByRole("button", { name: "Confirm pick" }));

    expect(
      await screen.findByText(
        "The draft changed before that action could be saved.",
      ),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("You are on the clock")).toBeInTheDocument(),
    );
    expect(screen.getAllByText("Marcus Hale").length).toBeGreaterThan(0);
  });

  it("keeps Blind view context-free and exposes the keyboard workflow", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/v1/boards?include_archived=false") {
        return response({ items: [board] });
      }
      if (url.endsWith("/boards/board-1/draft-sessions")) {
        return response({ items: [summary(draft)] });
      }
      if (url.includes("/draft-sessions/draft-1/candidates?")) {
        return response(candidates);
      }
      if (url.endsWith("/draft-sessions/draft-1")) return response(draft);
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftWorkspace />);
    const playerRow = await screen.findByRole("row", { name: /Marcus Hale/ });

    expect(
      screen.queryByRole("columnheader", { name: "Personal" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: "Tier" }),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/alert")),
    ).toBe(false);

    fireEvent.keyDown(window, { key: "/" });
    expect(screen.getByPlaceholderText("Search candidates")).toHaveFocus();

    playerRow.focus();
    fireEvent.keyDown(playerRow, { key: "Enter" });
    expect(screen.getByRole("button", { name: "Confirm pick" })).toBeEnabled();
    fireEvent.keyDown(playerRow, { key: "Escape" });
    expect(
      screen.queryByRole("button", { name: "Confirm pick" }),
    ).not.toBeInTheDocument();
  });

  it("mounts decision support only after leaving Blind view", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === "/api/v1/boards?include_archived=false") {
        return response({ items: [board] });
      }
      if (url.endsWith("/boards/board-1/draft-sessions")) {
        return response({ items: [summary(draft)] });
      }
      if (url.includes("/draft-sessions/draft-1/candidates?")) {
        return response({
          ...candidates,
          view: url.includes("view=personal") ? "personal" : "blind",
          items: url.includes("view=personal")
            ? candidates.items.map((candidate, index) => ({
                ...candidate,
                personal_rank: index + 1,
                tier_order: 1,
                favorite: index === 0,
              }))
            : candidates.items,
        });
      }
      if (url.endsWith("/draft-sessions/draft-1")) return response(draft);
      if (url.endsWith("/alert-configuration")) {
        return {
          ...response(
            {
              error: { message: "No decision-support evidence is attached." },
            },
            false,
          ),
          status: 404,
        };
      }
      if (url.includes("/alert-evidence-snapshots?")) {
        return response({ items: [], total: 0, limit: 100, offset: 0 });
      }
      throw new Error(`Unhandled request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftWorkspace />);
    await screen.findByRole("row", { name: /Marcus Hale/ });
    expect(
      screen.queryByRole("complementary", { name: "Decision support" }),
    ).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes("/alert")),
    ).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "personal" }));
    expect(
      await screen.findByRole("complementary", { name: "Decision support" }),
    ).toBeInTheDocument();
    expect(await screen.findByText("No evidence attached")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith("/alert-configuration"),
      ),
    ).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "blind" }));
    expect(
      screen.queryByRole("complementary", { name: "Decision support" }),
    ).not.toBeInTheDocument();
  });

  it("marks the preserved room reset when opening its replacement", async () => {
    const replacement: DraftSession = {
      ...draft,
      id: "draft-2",
      revision: 0,
      reset_from_session_id: draft.id,
    };
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/v1/boards?include_archived=false") {
          return response({ items: [board] });
        }
        if (url.endsWith("/boards/board-1/draft-sessions")) {
          return response({ items: [summary(draft)] });
        }
        if (
          url.endsWith("/draft-sessions/draft-1/reset") &&
          init?.method === "POST"
        ) {
          return response(replacement);
        }
        if (url.includes("/candidates?")) return response(candidates);
        if (url.endsWith("/draft-sessions/draft-1")) return response(draft);
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftWorkspace />);
    fireEvent.click(await screen.findByRole("button", { name: "Reset room" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm reset" }));

    expect(
      await screen.findByText(
        "Clean replacement room created; old session preserved.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Saved draft sessions"),
    ).toHaveTextContent("Reset");
  });
});
