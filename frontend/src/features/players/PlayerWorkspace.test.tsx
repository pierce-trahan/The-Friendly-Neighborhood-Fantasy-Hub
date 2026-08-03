import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  Player,
  PlayerImportSession,
  PlayerListResponse,
} from "../../api/client";
import { PlayerWorkspace } from "./PlayerWorkspace";

function response(payload: unknown, ok = true): Response {
  return {
    ok,
    json: async () => payload,
  } as Response;
}

const emptyPlayers: PlayerListResponse = {
  items: [],
  total: 0,
  limit: 25,
  offset: 0,
};

const canonicalPlayer: Player = {
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
  updated_at: "2026-07-24T12:00:00Z",
};

const ambiguousSession: PlayerImportSession = {
  id: "20000000-0000-0000-0000-000000000001",
  source: "sanitized_fixture",
  status: "preview",
  filename: "players.sanitized.json",
  new_count: 0,
  matched_count: 0,
  changed_count: 0,
  ambiguous_count: 1,
  invalid_count: 0,
  ignored_count: 0,
  created_at: "2026-07-24T12:00:00Z",
  committed_at: null,
  rows: [
    {
      id: "30000000-0000-0000-0000-000000000001",
      row_number: 1,
      source_name: "Marcus Hale",
      candidate: {
        display_name: "Marcus Hale",
        first_name: "Marcus",
        last_name: "Hale",
        suffix: null,
        search_name: "marcus hale",
        team: "CHI",
        primary_position: "QB",
        fantasy_positions: ["QB"],
        status: "active",
        rookie_class: 2022,
        is_rookie: false,
        provider: "sanitized_fixture",
        external_id: "fictional-001",
        include: true,
      },
      outcome: "ambiguous",
      proposed_player_id: canonicalPlayer.id,
      resolved_player_id: null,
      candidate_players: [canonicalPlayer],
      reason_code: "IMPORT.PLAYER.CONFIRM_NAME_MATCH",
      explanation: "The name and position suggest a match.",
    },
  ],
};

const newSession: PlayerImportSession = {
  ...ambiguousSession,
  id: "20000000-0000-0000-0000-000000000002",
  new_count: 1,
  ambiguous_count: 0,
  rows: [
    {
      ...ambiguousSession.rows[0],
      id: "30000000-0000-0000-0000-000000000002",
      outcome: "new",
      proposed_player_id: null,
      candidate_players: [],
      reason_code: "IMPORT.PLAYER.NEW",
      explanation: "No canonical player matches this valid source row.",
    },
  ],
};

describe("PlayerWorkspace", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function uploadCsv() {
    const input = screen.getByLabelText("Choose player CSV");
    Object.defineProperty(input, "files", {
      configurable: true,
      value: [
        {
          name: "players.csv",
          text: async () => "name,position,team,status\nMarcus Hale,QB,CHI,active\n",
        },
      ],
    });
    fireEvent.change(input);
  }

  it("keeps optional CSV import available without asking for sample data", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(emptyPlayers))
      .mockResolvedValueOnce(response(newSession));
    vi.stubGlobal("fetch", fetchMock);

    render(<PlayerWorkspace />);

    expect(
      await screen.findByRole("heading", { name: "No players match this view." }),
    ).toBeInTheDocument();
    await uploadCsv();

    expect(
      await screen.findByRole("heading", {
        name: "Nothing has changed in your player universe yet.",
      }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/v1/player-imports/csv/preview",
      expect.objectContaining({ method: "POST" }),
    );
    expect(screen.queryByText("Load safe sample")).not.toBeInTheDocument();
  });

  it("labels suggested matches as unconfirmed and locks commit", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(response(emptyPlayers))
        .mockResolvedValueOnce(response(ambiguousSession)),
    );

    render(<PlayerWorkspace />);
    await screen.findByText("0 players");
    await uploadCsv();
    await screen.findByText("Review before commit");
    fireEvent.click(screen.getByRole("button", { name: /Needs Review/ }));

    expect(await screen.findByText("Unconfirmed suggestion")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Commit import" })).toBeDisabled();
  });

  it("persists ignore and clear as real review decisions", async () => {
    const ignoredSession: PlayerImportSession = {
      ...ambiguousSession,
      ambiguous_count: 0,
      ignored_count: 1,
      rows: [
        {
          ...ambiguousSession.rows[0],
          outcome: "ignored",
          reason_code: "IMPORT.PLAYER.MANUAL_IGNORE",
          explanation: "This row will be skipped when the import is committed.",
        },
      ],
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(emptyPlayers))
      .mockResolvedValueOnce(response(ambiguousSession))
      .mockResolvedValueOnce(response(ignoredSession))
      .mockResolvedValueOnce(response(ambiguousSession));
    vi.stubGlobal("fetch", fetchMock);

    render(<PlayerWorkspace />);
    await screen.findByText("0 players");
    await uploadCsv();
    await screen.findByText("Review before commit");
    fireEvent.click(screen.getByRole("button", { name: /Needs Review/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Ignore row" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Undo decision" }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({
      decision: "ignore",
    });
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({
      decision: "clear",
    });
  });

  it("refreshes the canonical universe after a successful commit", async () => {
    const populatedPlayers: PlayerListResponse = {
      items: [canonicalPlayer],
      total: 1,
      limit: 25,
      offset: 0,
    };
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(response(emptyPlayers))
        .mockResolvedValueOnce(response(newSession))
        .mockResolvedValueOnce(
          response({
            session: { ...newSession, status: "committed" },
            created_players: 1,
            updated_players: 0,
            ignored_rows: 0,
          }),
        )
        .mockResolvedValueOnce(response(populatedPlayers)),
    );

    render(<PlayerWorkspace />);
    await screen.findByText("0 players");
    await uploadCsv();
    fireEvent.click(await screen.findByRole("button", { name: "Commit import" }));

    expect(await screen.findByText("1 player")).toBeInTheDocument();
    expect(
      screen.getByRole("rowheader", { name: /Marcus Hale/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Import complete: 1 created/)).toBeInTheDocument();
  });

  it("shows the safe API message and recovery action", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          {
            error: {
              message: "The player list could not be loaded.",
              action: "Restart the Hub and try again.",
              correlation_id: "safe-correlation-id",
            },
          },
          false,
        ),
      ),
    );

    render(<PlayerWorkspace />);

    expect(
      await screen.findByText("The player list could not be loaded."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Restart the Hub and try again."),
    ).toBeInTheDocument();
  });
});
