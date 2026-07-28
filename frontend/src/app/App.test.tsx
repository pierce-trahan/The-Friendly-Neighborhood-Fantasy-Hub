import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const configuration = {
  schema_version: 1,
  active_league_season_id: null,
  display: {
    timezone: "America/Chicago",
    theme: "system",
    reduced_motion: false,
  },
  backups: {
    automatic: true,
    retention_count: 10,
  },
  safety: {
    confirm_reset: true,
    confirm_delete: true,
  },
};

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({
            status: "ok",
            app_version: "0.1.0",
            database_schema_version: "20260724_0001",
          }),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => configuration,
        })
        .mockResolvedValueOnce({
          ok: true,
          json: async () => [],
        }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the local launch proof when the backend is healthy", async () => {
    render(<App />);

    expect(
      await screen.findByRole("heading", {
        name: "Friendly Neighborhood Fantasy Hub",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Local database connected")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Load Entropy sample" }),
    ).toBeEnabled();
    expect(screen.getByRole("button", { name: "Gut ELO" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Draft room" })).toBeEnabled();
  });
});
