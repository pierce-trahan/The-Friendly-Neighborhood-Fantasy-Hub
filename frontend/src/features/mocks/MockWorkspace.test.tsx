import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MockSession } from "../../api/client";
import { MockWorkspace } from "./MockWorkspace";

function response(payload: unknown, ok = true) {
  return {
    ok,
    json: async () => payload,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}

const board = {
  id: "board-1",
  name: "Neighborhood Board",
  description: null,
  league_profile_id: null,
  scope: "overall" as const,
  archived: false,
  entry_count: 6,
  created_at: "2026-07-28T10:00:00Z",
  updated_at: "2026-07-28T10:00:00Z",
};

function makeMock(
  overallPick = 1,
  overrides: Partial<MockSession> = {},
): MockSession {
  const selectingSlot = ((overallPick - 1) % 3) + 1;
  const userOnTheClock = selectingSlot === 3;
  const currentPick =
    overallPick <= 6
      ? {
          overall_pick: overallPick,
          round_number: Math.ceil(overallPick / 3),
          pick_in_round: ((overallPick - 1) % 3) + 1,
          selecting_slot: selectingSlot,
          selecting_team:
            selectingSlot === 3 ? "Your Team" : `CPU ${selectingSlot}`,
        }
      : null;
  const result: MockSession = {
    practice_simulation: true,
    draft: {
      id: "mock-1",
      name: "Strategy rehearsal",
      board_id: board.id,
      board_name: board.name,
      mode: "mock",
      draft_format: "snake",
      third_round_reversal: false,
      team_count: 3,
      round_count: 2,
      user_slot: 3,
      status: currentPick ? "active" : "completed",
      revision: overallPick - 1,
      active_pick_count: overallPick - 1,
      total_picks: 6,
      created_at: "2026-07-28T10:00:00Z",
      updated_at: "2026-07-28T10:00:00Z",
      league_profile_id: null,
      pick_timer_seconds: null,
      reset_from_session_id: null,
      teams: [
        { draft_slot: 1, display_name: "CPU 1", is_user: false },
        { draft_slot: 2, display_name: "CPU 2", is_user: false },
        { draft_slot: 3, display_name: "Your Team", is_user: true },
      ],
      current_pick: currentPick,
      user_on_the_clock: userOnTheClock,
      picks_until_user: currentPick
        ? userOnTheClock
          ? 0
          : 3 - selectingSlot
        : null,
      picks: [],
      candidate_total: 3,
      available_count: Math.max(0, 7 - overallPick),
      blind_data_hidden: true,
      recommendation_state_present: false,
      completed_at: currentPick ? null : "2026-07-28T10:30:00Z",
      reset_at: null,
      recovery_guidance: null,
    },
    mock: {
      content_fingerprint: "fingerprint-1",
      cpu_engine_version: "market-board-v1",
      created_at: "2026-07-28T10:00:00Z",
      current_strategy_key: "balanced",
      include_in_learning: false,
      learning_opted_in_at: null,
      learning_withdrawn_at: null,
      randomness: 25,
      reset_replay_status: "original",
      revision: overallPick - 1,
      rng_version: "sha256-counter-v1",
      seed: "20260728",
      strategy_compatibility: "reduced",
      strategy_definition_version: "strategy-v1",
      strategy_limitations: ["LEAGUE_SHAPE_UNAVAILABLE"],
      updated_at: "2026-07-28T10:00:00Z",
      market_baseline: {
        label: "Dynasty Superflex expert consensus",
        evidence_kind: "expert_consensus",
        source_name: "DynastyProcess",
        source_url:
          "https://github.com/dynastyprocess/data/blob/master/files/values.csv",
        rank_type: "dynasty_2qb_ecr",
        format: "dynasty_superflex_proxy",
        source_as_of: "2026-07-31",
        freshness: "fresh",
        player_count: 621,
        matched_candidate_count: 3,
        candidate_count: 3,
        coverage_percent: 100,
        confidence: "medium",
        limitations: ["ECR_NOT_ADP", "TE_PREMIUM_NOT_EXPLICIT"],
      },
    },
    current_checkpoint: {
      id: "guide-1",
      strategy_key: "balanced",
      strategy_definition_version: "strategy-v1",
      effective_overall_pick: overallPick,
      state: "insufficient_evidence",
      confidence: "unavailable",
      observed_counts: {},
      target_ranges: {},
      affected_positions: [],
      reason_codes: ["NO_TIMELINE_EVIDENCE"],
      limitation_codes: ["PLAYER_TIMELINE_UNAVAILABLE"],
      explanation_template_key: "insufficient",
      explanation:
        "The guide can track roster shape, but approved timeline evidence is unavailable.",
      pivot_template_key: null,
      viable_pivot_explanation: null,
      status: "open",
      created_at: "2026-07-28T10:00:00Z",
      resolved_at: null,
    },
    current_strategy_revision: {
      created_at: "2026-07-28T10:00:00Z",
      effective_overall_pick: 1,
      next_strategy_key: "balanced",
      previous_strategy_key: null,
      reason: "initial_strategy",
      sequence_number: 1,
      user_roster_counts: {},
    },
    user_roster_counts: {},
    guidance: [],
    cpu_profiles: [
      {
        archetype_key: "balanced",
        confidence: "not_applicable",
        draft_sample_count: 0,
        draft_slot: 1,
        pick_sample_count: 0,
        source: "fallback",
      },
      {
        archetype_key: "wr_heavy",
        confidence: "not_applicable",
        draft_sample_count: 0,
        draft_slot: 2,
        pick_sample_count: 0,
        source: "fallback",
      },
    ],
    last_cpu_decision:
      overallPick > 1
        ? {
            id: `decision-${overallPick - 1}`,
            overall_pick: overallPick - 1,
            selecting_slot: ((overallPick - 2) % 3) + 1,
            chosen_player_id: "player-1",
            chosen_player_display_name: "Marcus Hale",
            chosen_player_position: "QB",
            profile_source: "fallback",
            profile_archetype_key: "balanced",
            profile_confidence: "not_applicable",
            engine_version: "market-board-v1",
            rng_version: "sha256-counter-v1",
            total_score: 900,
            component_scores: {
              board_order: 700,
              starter_need: 200,
              depth_need: 0,
              archetype_fit: 0,
              duplication_penalty: 0,
              random_variation: 0,
            },
            reason_codes: ["MARKET_ECR_BASELINE", "STARTER_NEED"],
            limitation_codes: [],
            decision_status: "active",
            manually_corrected: false,
            created_at: "2026-07-28T10:01:00Z",
          }
        : null,
    can_advance_cpu: Boolean(currentPick && !userOnTheClock),
    recovery_guidance: null,
  };
  return { ...result, ...overrides };
}

const candidates = {
  view: "personal" as const,
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
      personal_rank: 1,
      favorite: true,
      tier_name: "Cornerstones",
      tier_color: "#74c7ff",
      board_note: null,
      snapshot_source: "personal_board" as const,
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
      personal_rank: 2,
      favorite: false,
      tier_name: "Core",
      tier_color: "#a8ff60",
      board_note: null,
      snapshot_source: "personal_board" as const,
    },
  ],
};

function history(mock: MockSession) {
  return {
    items: [
      {
        session_id: mock.draft.id,
        name: mock.draft.name,
        status: mock.draft.status,
        completion_state:
          mock.draft.status === "completed" ? ("completed" as const) : ("incomplete" as const),
        seed: mock.mock.seed,
        randomness: mock.mock.randomness,
        current_strategy_key: mock.mock.current_strategy_key,
        pivot_count: mock.current_strategy_revision.sequence_number - 1,
        mock_revision: mock.mock.revision,
        draft_format: mock.draft.draft_format,
        third_round_reversal: mock.draft.third_round_reversal,
        team_count: mock.draft.team_count,
        round_count: mock.draft.round_count,
        user_slot: mock.draft.user_slot,
        include_in_learning: mock.mock.include_in_learning,
        learning_opted_in_at: mock.mock.learning_opted_in_at,
        learning_withdrawn_at: mock.mock.learning_withdrawn_at,
        rng_version: mock.mock.rng_version,
        cpu_engine_version: mock.mock.cpu_engine_version,
        strategy_definition_version: mock.mock.strategy_definition_version,
        created_at: mock.draft.created_at,
        updated_at: mock.draft.updated_at,
        completed_at: mock.draft.completed_at,
        reset_at: mock.draft.reset_at,
      },
    ],
    total: 1,
    limit: 20,
    offset: 0,
  };
}

function baseHandler(initial: MockSession) {
  return async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/boards?include_archived=false") {
      return response({ items: [board] });
    }
    if (url.includes("/boards/board-1/mock-sessions?")) {
      return response(history(initial));
    }
    if (url === "/api/v1/mock-sessions/mock-1") {
      return response(initial);
    }
    if (url.includes("/draft-sessions/mock-1/candidates?")) {
      return response({ ...candidates, view: url.includes("view=blind") ? "blind" : "personal" });
    }
    throw new Error(`Unhandled request: ${url}`);
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("MockWorkspace", () => {
  it("creates a practice simulation with learning consent off", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/v1/boards?include_archived=false") {
          return response({ items: [board] });
        }
        if (url.includes("/boards/board-1/mock-sessions?")) {
          return response({ items: [], total: 0, limit: 20, offset: 0 });
        }
        if (
          url === "/api/v1/boards/board-1/mock-sessions" &&
          init?.method === "POST"
        ) {
          return response(makeMock(), true);
        }
        if (url.includes("/draft-sessions/mock-1/candidates?")) {
          return response(candidates);
        }
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<MockWorkspace />);
    fireEvent.change(await screen.findByLabelText("Rehearsal name"), {
      target: { value: "Opening night" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Create practice simulation" }),
    );

    await screen.findByText("Practice simulation created and saved locally.");
    const createCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url) === "/api/v1/boards/board-1/mock-sessions" &&
        init?.method === "POST",
    );
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      name: "Opening night",
      seed: "20260728",
      randomness: 25,
      strategy_key: "balanced",
      include_in_learning: false,
    });
  });

  it("runs one guarded CPU request at a time and stops on the user turn", async () => {
    const initial = makeMock(1);
    let cpuCalls = 0;
    let inFlight = 0;
    let maximumInFlight = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (
          url === "/api/v1/mock-sessions/mock-1/cpu-pick" &&
          init?.method === "POST"
        ) {
          cpuCalls += 1;
          inFlight += 1;
          maximumInFlight = Math.max(maximumInFlight, inFlight);
          await Promise.resolve();
          inFlight -= 1;
          return response(makeMock(cpuCalls + 1));
        }
        return baseHandler(initial)(input);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<MockWorkspace />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Run to my pick" }),
    );

    expect(
      await screen.findByText("The run stopped safely. You are on the clock."),
    ).toBeInTheDocument();
    expect(cpuCalls).toBe(2);
    expect(maximumInFlight).toBe(1);
    const payloads = fetchMock.mock.calls
      .filter(
        ([url, init]) =>
          String(url).endsWith("/cpu-pick") && init?.method === "POST",
      )
      .map(([, init]) => JSON.parse(String(init?.body)));
    expect(payloads).toEqual([
      {
        draft_revision: 0,
        mock_revision: 0,
        expected_overall_pick: 1,
        expected_selecting_slot: 1,
      },
      {
        draft_revision: 1,
        mock_revision: 1,
        expected_overall_pick: 2,
        expected_selecting_slot: 2,
      },
    ]);
  });

  it("stops after an in-flight CPU response and does not start another", async () => {
    const initial = makeMock(1);
    const gate = deferred<ReturnType<typeof response>>();
    let cpuCalls = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (
          url === "/api/v1/mock-sessions/mock-1/cpu-pick" &&
          init?.method === "POST"
        ) {
          cpuCalls += 1;
          return gate.promise;
        }
        return baseHandler(initial)(input);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<MockWorkspace />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Run to my pick" }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Stop after current pick" }),
    );
    gate.resolve(response(makeMock(2)));

    await screen.findByText("Stopped after the latest saved CPU pick.");
    expect(cpuCalls).toBe(1);
  });

  it("pauses only after the in-flight CPU pick is saved", async () => {
    const initial = makeMock(1);
    const afterCpu = makeMock(2);
    const paused: MockSession = {
      ...afterCpu,
      draft: { ...afterCpu.draft, status: "paused" },
      can_advance_cpu: false,
    };
    const gate = deferred<ReturnType<typeof response>>();
    let pauseSaved = false;
    let cpuCalls = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (
          url === "/api/v1/mock-sessions/mock-1/cpu-pick" &&
          init?.method === "POST"
        ) {
          cpuCalls += 1;
          return gate.promise;
        }
        if (
          url === "/api/v1/draft-sessions/mock-1" &&
          init?.method === "PATCH"
        ) {
          pauseSaved = true;
          return response(paused.draft);
        }
        if (url === "/api/v1/mock-sessions/mock-1") {
          return response(pauseSaved ? paused : initial);
        }
        return baseHandler(initial)(input);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<MockWorkspace />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Run to my pick" }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Pause" }));
    expect(pauseSaved).toBe(false);
    gate.resolve(response(afterCpu));

    await screen.findByText(
      "Practice paused after the latest saved CPU pick.",
    );
    expect(cpuCalls).toBe(1);
    const pauseCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url) === "/api/v1/draft-sessions/mock-1" &&
        init?.method === "PATCH",
    );
    expect(JSON.parse(String(pauseCall?.[1]?.body))).toEqual({
      revision: 1,
      status: "paused",
    });
  });

  it("never records a user pick before explicit confirmation", async () => {
    const userTurn = makeMock(3);
    const afterPick = makeMock(4);
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (
          url === "/api/v1/draft-sessions/mock-1/picks" &&
          init?.method === "POST"
        ) {
          return response(afterPick.draft);
        }
        if (url === "/api/v1/mock-sessions/mock-1") {
          return response(
            fetchMock.mock.calls.some(
              ([calledUrl, calledInit]) =>
                String(calledUrl).endsWith("/picks") &&
                calledInit?.method === "POST",
            )
              ? afterPick
              : userTurn,
          );
        }
        return baseHandler(userTurn)(input);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<MockWorkspace />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Draft" }))[0]);
    expect(
      fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).endsWith("/picks") && init?.method === "POST",
      ),
    ).toBeUndefined();
    fireEvent.click(screen.getByRole("button", { name: "Confirm pick" }));

    await screen.findByText(
      "Your pick is confirmed and saved. No CPU action was bundled with it.",
    );
    const pickCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).endsWith("/picks") && init?.method === "POST",
    );
    expect(JSON.parse(String(pickCall?.[1]?.body))).toMatchObject({
      revision: 2,
      expected_overall_pick: 3,
      player_id: "player-1",
    });
  });

  it("shows evidence limits, labels fallback profiles, and reverses learning consent", async () => {
    const initial = makeMock(1);
    const learningOn = makeMock(1, {
      mock: {
        ...initial.mock,
        revision: 1,
        include_in_learning: true,
        learning_opted_in_at: "2026-07-28T10:05:00Z",
      },
    });
    const pivoted = makeMock(1, {
      mock: {
        ...learningOn.mock,
        revision: 2,
        current_strategy_key: "hero_rb",
      },
      current_checkpoint: {
        ...learningOn.current_checkpoint,
        strategy_key: "hero_rb",
      },
    });
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (
          url === "/api/v1/mock-sessions/mock-1/learning" &&
          init?.method === "PATCH"
        ) {
          return response(learningOn);
        }
        if (
          url === "/api/v1/mock-sessions/mock-1/strategy" &&
          init?.method === "PATCH"
        ) {
          return response(pivoted);
        }
        return baseHandler(initial)(input);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<MockWorkspace />);
    expect(
      await screen.findByText("Fallback model — not learned manager behavior"),
    ).toBeInTheDocument();
    expect(screen.getByText("League shape unavailable")).toBeInTheDocument();
    expect(screen.getByText("Player timeline unavailable")).toBeInTheDocument();
    expect(
      screen.getByText("Dynasty Superflex expert consensus"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Expert consensus ranking — not average draft position"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Tight-end premium is not included in this baseline"),
    ).toBeInTheDocument();

    const toggle = screen.getByRole("checkbox", {
      name: /Include in local learning/,
    });
    expect(toggle).not.toBeChecked();
    fireEvent.click(toggle);
    await waitFor(() => expect(toggle).toBeChecked());
    const learningCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).endsWith("/learning") && init?.method === "PATCH",
    );
    expect(JSON.parse(String(learningCall?.[1]?.body))).toEqual({
      mock_revision: 0,
      include_in_learning: true,
    });

    fireEvent.change(screen.getByLabelText("Future strategy guide"), {
      target: { value: "hero_rb" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Pivot future guidance" }),
    );
    expect(
      await screen.findByText(
        "Guide pivoted. All 0 completed picks remain unchanged.",
      ),
    ).toBeInTheDocument();
    const pivotCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).endsWith("/strategy") && init?.method === "PATCH",
    );
    expect(JSON.parse(String(pivotCall?.[1]?.body))).toEqual({
      mock_revision: 1,
      expected_current_overall_pick: 1,
      strategy_key: "hero_rb",
    });
  });

  it("ignores run shortcuts inside form fields", async () => {
    const initial = makeMock(1);
    let cpuCalls = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (
          url === "/api/v1/mock-sessions/mock-1/cpu-pick" &&
          init?.method === "POST"
        ) {
          cpuCalls += 1;
          return response(makeMock(3));
        }
        return baseHandler(initial)(input);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<MockWorkspace />);
    const search = await screen.findByPlaceholderText("Search candidates");
    fireEvent.keyDown(search, { key: "r" });
    await Promise.resolve();
    expect(cpuCalls).toBe(0);

    fireEvent.keyDown(window, { key: "r" });
    await screen.findByText("The run stopped safely. You are on the clock.");
    expect(cpuCalls).toBe(1);
  });

  it("refreshes authoritative state after a rejected CPU guard", async () => {
    const initial = makeMock(1);
    const serverAdvanced = makeMock(3);
    let sessionReads = 0;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/v1/mock-sessions/mock-1") {
          sessionReads += 1;
          return response(sessionReads === 1 ? initial : serverAdvanced);
        }
        if (
          url === "/api/v1/mock-sessions/mock-1/cpu-pick" &&
          init?.method === "POST"
        ) {
          return response(
            {
              error: {
                message: "The mock changed before that CPU pick.",
                action: "Refresh and retry.",
              },
            },
            false,
          );
        }
        return baseHandler(initial)(input);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<MockWorkspace />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Advance one CPU pick" }),
    );

    expect(
      await screen.findByText("The mock changed before that CPU pick."),
    ).toBeInTheDocument();
    expect(await screen.findByText("Stopped for your pick")).toBeInTheDocument();
    expect(sessionReads).toBe(2);
  });
});
