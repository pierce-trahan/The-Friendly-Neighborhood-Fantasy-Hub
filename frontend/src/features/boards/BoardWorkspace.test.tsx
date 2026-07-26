import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  Board,
  BoardListResponse,
  Player,
  PlayerListResponse,
} from "../../api/client";
import { BoardWorkspace } from "./BoardWorkspace";

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
  primary_position: "QB",
  fantasy_positions: ["QB"],
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
  primary_position: "RB",
  fantasy_positions: ["RB"],
};

function makeBoard(entries: Board["entries"] = []): Board {
  return {
    id: "20000000-0000-0000-0000-000000000001",
    name: "Dynasty Startup Board",
    description: "My authoritative player order for this draft room.",
    scope: "overall",
    league_profile_id: null,
    archived: false,
    entry_count: entries.length,
    entries,
    tiers: [],
    created_at: "2026-07-26T12:00:00Z",
    updated_at: "2026-07-26T12:00:00Z",
  };
}

function boardSummary(board: Board): BoardListResponse {
  const { entries: _entries, tiers: _tiers, ...summary } = board;
  return { items: [summary] };
}

function entry(
  player: Player,
  rank: number,
): Board["entries"][number] {
  return {
    id: `30000000-0000-0000-0000-00000000000${rank}`,
    player,
    rank,
    tier_id: null,
    note: null,
    favorite: false,
    updated_at: "2026-07-26T12:00:00Z",
  };
}

describe("BoardWorkspace", () => {
  beforeEach(() => {
    HTMLDialogElement.prototype.showModal = function showModal() {
      this.setAttribute("open", "");
    };
    HTMLDialogElement.prototype.close = function close() {
      this.removeAttribute("open");
    };
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("creates the first independent personal board", async () => {
    let currentBoard: Board | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/v1/boards?include_archived=false") {
        return response(currentBoard ? boardSummary(currentBoard) : { items: [] });
      }
      if (url === "/api/v1/boards" && init?.method === "POST") {
        currentBoard = makeBoard();
        return response(currentBoard);
      }
      if (url === `/api/v1/boards/${makeBoard().id}`) {
        return response(currentBoard);
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<BoardWorkspace />);

    expect(
      await screen.findByRole("heading", {
        name: "Create your first personal board.",
      }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getAllByRole("button", { name: "Create personal board" }).at(-1)!,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Create board" }),
    );

    expect(
      await screen.findByRole("heading", { name: "Dynasty Startup Board" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Personal board created locally.")).toBeInTheDocument();
    const createCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === "/api/v1/boards" && (init as RequestInit | undefined)?.method === "POST",
    );
    expect(JSON.parse((createCall?.[1] as RequestInit).body as string)).toEqual({
      name: "Dynasty Startup Board",
      description: "My authoritative player order for this draft room.",
      scope: "overall",
      league_profile_id: null,
    });
  });

  it("adds a canonical player to the end of the selected board", async () => {
    let currentBoard = makeBoard();
    const players: PlayerListResponse = {
      items: [firstPlayer],
      total: 1,
      limit: 100,
      offset: 0,
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/v1/boards?include_archived=false") {
        return response(boardSummary(currentBoard));
      }
      if (url === `/api/v1/boards/${currentBoard.id}`) {
        return response(currentBoard);
      }
      if (url.startsWith("/api/v1/players?")) return response(players);
      if (
        url === `/api/v1/boards/${currentBoard.id}/entries` &&
        init?.method === "POST"
      ) {
        currentBoard = makeBoard([entry(firstPlayer, 1)]);
        return response(currentBoard);
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<BoardWorkspace />);
    await screen.findByRole("heading", { name: "Dynasty Startup Board" });
    fireEvent.click(screen.getByRole("button", { name: "Add first player" }));
    const pickerPlayer = (await screen.findAllByText("Marcus Hale")).find(
      (element) => element.tagName === "STRONG",
    )!;
    fireEvent.click(pickerPlayer.closest("article")!.querySelector("button")!);

    expect(
      await screen.findByText("Player added to the end of your board."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Manual player order" }),
    ).toHaveTextContent("Marcus Hale");
    const addCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === `/api/v1/boards/${currentBoard.id}/entries` &&
        (init as RequestInit | undefined)?.method === "POST",
    );
    expect(JSON.parse((addCall?.[1] as RequestInit).body as string)).toEqual({
      player_id: firstPlayer.id,
    });
  });

  it("sends the complete manual order when a player moves", async () => {
    let currentBoard = makeBoard([
      entry(firstPlayer, 1),
      entry(secondPlayer, 2),
    ]);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/v1/boards?include_archived=false") {
        return response(boardSummary(currentBoard));
      }
      if (url === `/api/v1/boards/${currentBoard.id}`) {
        return response(currentBoard);
      }
      if (
        url === `/api/v1/boards/${currentBoard.id}/order` &&
        init?.method === "PUT"
      ) {
        currentBoard = makeBoard([
          entry(secondPlayer, 1),
          entry(firstPlayer, 2),
        ]);
        return response(currentBoard);
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<BoardWorkspace />);
    await screen.findByRole("button", { name: "Move Marcus Hale down" });
    fireEvent.click(
      screen.getByRole("button", { name: "Move Marcus Hale down" }),
    );

    expect(await screen.findByText("Manual board order saved.")).toBeInTheDocument();
    const orderCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        url === `/api/v1/boards/${currentBoard.id}/order` &&
        (init as RequestInit | undefined)?.method === "PUT",
    );
    expect(JSON.parse((orderCall?.[1] as RequestInit).body as string)).toEqual({
      player_ids: [secondPlayer.id, firstPlayer.id],
    });
    await waitFor(() =>
      expect(
        screen.getAllByRole("listitem")[0],
      ).toHaveTextContent("Devin Brooks"),
    );
  });
});
