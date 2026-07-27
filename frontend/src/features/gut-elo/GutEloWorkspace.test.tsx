import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  Board,
  BoardListResponse,
  GutEloSession,
  Player,
} from "../../api/client";
import { GutEloWorkspace } from "./GutEloWorkspace";

function response(payload: unknown, ok = true): Response {
  return {
    ok,
    json: async () => payload,
  } as Response;
}

const firstPlayer: Player = {
  id: "10000000-0000-0000-0000-000000000001",
  display_name: "Marcus Hale",
  first_name: "Marcus",
  last_name: "Hale",
  suffix: null,
  team: "CHI",
  primary_position: "RB",
  fantasy_positions: ["RB"],
  status: "active",
  rookie_class: 2022,
  is_rookie: false,
  relevant: true,
  updated_at: "2026-07-26T12:00:00Z",
};

const secondPlayer: Player = {
  ...firstPlayer,
  id: "10000000-0000-0000-0000-000000000002",
  display_name: "Devin Brooks",
  first_name: "Devin",
  last_name: "Brooks",
  team: "ATL",
};

const thirdPlayer: Player = {
  ...firstPlayer,
  id: "10000000-0000-0000-0000-000000000003",
  display_name: "Theo Grant",
  first_name: "Theo",
  last_name: "Grant",
  team: "SEA",
  primary_position: "WR",
  fantasy_positions: ["WR"],
};

const board: Board = {
  id: "20000000-0000-0000-0000-000000000001",
  name: "Dynasty Startup Board",
  description: "My authoritative player order.",
  scope: "overall",
  league_profile_id: null,
  archived: false,
  entry_count: 3,
  entries: [firstPlayer, secondPlayer, thirdPlayer].map((player, index) => ({
    id: `30000000-0000-0000-0000-00000000000${index + 1}`,
    player,
    tier_id: null,
    rank: index + 1,
    note: null,
    favorite: false,
    updated_at: "2026-07-26T12:00:00Z",
  })),
  tiers: [
    {
      id: "40000000-0000-0000-0000-000000000001",
      name: "Cornerstones",
      color: "#A8FF60",
      tier_order: 1,
      created_at: "2026-07-26T12:00:00Z",
      updated_at: "2026-07-26T12:00:00Z",
    },
  ],
  created_at: "2026-07-26T12:00:00Z",
  updated_at: "2026-07-26T12:00:00Z",
};

function boardList(): BoardListResponse {
  const { entries: _entries, tiers: _tiers, ...summary } = board;
  return { items: [summary] };
}

function makeSession(
  overrides: Partial<GutEloSession> = {},
): GutEloSession {
  return {
    id: "50000000-0000-0000-0000-000000000001",
    board_id: board.id,
    board_name: board.name,
    board_scope: "overall",
    queue_mode: "board",
    position: null,
    tier_id: null,
    status: "active",
    participant_count: 3,
    resolved_count: 0,
    target_count: 2,
    created_at: "2026-07-26T12:00:00Z",
    updated_at: "2026-07-26T12:00:00Z",
    completed_at: null,
    revision: 0,
    participants: [firstPlayer, secondPlayer, thirdPlayer].map(
      (player, index) => ({
        player,
        starting_manual_rank: index + 1,
        starting_tier_name: null,
        gut_rank: index + 1,
        rating: 1000,
        decisive_count: 0,
      }),
    ),
    progress: {
      resolved_count: 0,
      decisive_count: 0,
      insufficient_count: 0,
      skip_count: 0,
      target_count: 2,
      progress_percent: 0,
      participants_with_decision: 0,
      participant_count: 3,
      coverage_percent: 0,
      stability_label: "starting",
      stability_explanation:
        "This is an early read; more resolved comparisons are needed.",
    },
    actions: [],
    next_pair: {
      revision: 0,
      player_a: firstPlayer,
      player_b: secondPlayer,
    },
    manual_board_unchanged: true,
    ...overrides,
  };
}

function sessionSummary(gutSession: GutEloSession) {
  const {
    actions: _actions,
    manual_board_unchanged: _manualBoardUnchanged,
    next_pair: _nextPair,
    participants: _participants,
    progress: _progress,
    revision: _revision,
    ...summary
  } = gutSession;
  return summary;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("GutEloWorkspace", () => {
  it("starts a bounded position session from the selected Personal Board", async () => {
    const created = makeSession({
      queue_mode: "position",
      position: "RB",
      participant_count: 2,
      target_count: 2,
    });
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/v1/boards?include_archived=false") {
          return response(boardList());
        }
        if (url === `/api/v1/boards/${board.id}`) return response(board);
        if (url === `/api/v1/boards/${board.id}/gut-elo-sessions`) {
          if (init?.method === "POST") return response(created);
          return response({ items: [] });
        }
        throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<GutEloWorkspace />);

    await screen.findByRole("heading", {
      name: "Set the question, then trust the first reaction.",
    });
    fireEvent.click(screen.getByRole("radio", { name: /One position/ }));
    fireEvent.change(screen.getByLabelText("Position"), {
      target: { value: "RB" },
    });
    fireEvent.change(
      screen.getByLabelText("Resolved comparison target"),
      { target: { value: "2" } },
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Start Gut ELO session" }),
    );

    expect(
      await screen.findByText(
        "Gut ELO session started. The Personal Board is unchanged.",
      ),
    ).toBeInTheDocument();
    const createCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === `/api/v1/boards/${board.id}/gut-elo-sessions` &&
        (init as RequestInit | undefined)?.method === "POST",
    );
    expect(JSON.parse((createCall?.[1] as RequestInit).body as string)).toEqual({
      queue_mode: "position",
      position: "RB",
      tier_id: null,
      target_count: 2,
    });
  });

  it("maps a visually swapped choice back to the canonical pair outcome", async () => {
    const initial = makeSession({
      revision: 1,
      actions: [
        {
          id: "60000000-0000-0000-0000-000000000001",
          sequence_number: 1,
          player_a_id: firstPlayer.id,
          player_b_id: thirdPlayer.id,
          outcome: "skip",
          created_at: "2026-07-26T12:01:00Z",
        },
      ],
      next_pair: {
        revision: 1,
        player_a: firstPlayer,
        player_b: secondPlayer,
      },
    });
    const updated = makeSession({
      revision: 2,
      resolved_count: 1,
      updated_at: "2026-07-26T12:02:00Z",
      actions: [
        {
          id: "60000000-0000-0000-0000-000000000002",
          sequence_number: 2,
          player_a_id: firstPlayer.id,
          player_b_id: secondPlayer.id,
          outcome: "b_win",
          created_at: "2026-07-26T12:02:00Z",
        },
        ...initial.actions,
      ],
      progress: {
        ...initial.progress,
        resolved_count: 1,
        decisive_count: 1,
        progress_percent: 50,
        participants_with_decision: 2,
        coverage_percent: 67,
        stability_label: "developing",
      },
      next_pair: {
        revision: 2,
        player_a: secondPlayer,
        player_b: thirdPlayer,
      },
    });
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/v1/boards?include_archived=false") {
          return response(boardList());
        }
        if (url === `/api/v1/boards/${board.id}`) return response(board);
        if (url === `/api/v1/boards/${board.id}/gut-elo-sessions`) {
          return response({ items: [sessionSummary(initial)] });
        }
        if (url === `/api/v1/gut-elo-sessions/${initial.id}`) {
          return response(initial);
        }
        if (
          url === `/api/v1/gut-elo-sessions/${initial.id}/actions` &&
          init?.method === "POST"
        ) {
          return response(updated);
        }
        throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<GutEloWorkspace />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Choose Devin Brooks" }),
    );
    await screen.findByText("Preference saved locally.");

    const actionCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === `/api/v1/gut-elo-sessions/${initial.id}/actions` &&
        (init as RequestInit | undefined)?.method === "POST",
    );
    expect(JSON.parse((actionCall?.[1] as RequestInit).body as string)).toEqual({
      revision: 1,
      player_a_id: firstPlayer.id,
      player_b_id: secondPlayer.id,
      outcome: "b_win",
    });
  });

  it("supports keyboard skip and reversible undo", async () => {
    const initial = makeSession();
    const skipped = makeSession({
      revision: 1,
      updated_at: "2026-07-26T12:01:00Z",
      actions: [
        {
          id: "60000000-0000-0000-0000-000000000001",
          sequence_number: 1,
          player_a_id: firstPlayer.id,
          player_b_id: secondPlayer.id,
          outcome: "skip",
          created_at: "2026-07-26T12:01:00Z",
        },
      ],
      progress: {
        ...initial.progress,
        skip_count: 1,
      },
      next_pair: {
        revision: 1,
        player_a: firstPlayer,
        player_b: thirdPlayer,
      },
    });
    let actionSaved = false;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/v1/boards?include_archived=false") {
          return response(boardList());
        }
        if (url === `/api/v1/boards/${board.id}`) return response(board);
        if (url === `/api/v1/boards/${board.id}/gut-elo-sessions`) {
          return response({ items: [sessionSummary(initial)] });
        }
        if (url === `/api/v1/gut-elo-sessions/${initial.id}`) {
          return response(initial);
        }
        if (
          url === `/api/v1/gut-elo-sessions/${initial.id}/actions` &&
          init?.method === "POST"
        ) {
          actionSaved = true;
          return response(skipped);
        }
        if (
          url === `/api/v1/gut-elo-sessions/${initial.id}/undo` &&
          init?.method === "POST"
        ) {
          return response(initial);
        }
        throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<GutEloWorkspace />);
    await screen.findByRole("button", { name: "Choose Marcus Hale" });

    fireEvent.keyDown(window, { key: "s" });
    await screen.findByText(
      "Pair postponed. It can return after other matchups.",
    );
    expect(actionSaved).toBe(true);

    fireEvent.keyDown(window, { key: "u" });
    await screen.findByText("Latest comparison undone and ratings replayed.");
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            url === `/api/v1/gut-elo-sessions/${initial.id}/undo` &&
            (init as RequestInit | undefined)?.method === "POST",
        ),
      ).toBe(true),
    );
  });
});
