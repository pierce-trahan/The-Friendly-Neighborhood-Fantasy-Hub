import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  AlertDetail,
  DraftAlertConfiguration,
  DraftAlertList,
  DraftSession,
} from "../../api/client";
import { DraftAlertRail } from "./DraftAlertRail";

function response(payload: unknown, ok = true, status = ok ? 200 : 400) {
  return {
    ok,
    status,
    json: async () => payload,
  };
}

const draft: DraftSession = {
  id: "draft-1",
  name: "Entropy Draft",
  board_id: "board-1",
  board_name: "Personal Board",
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
  teams: Array.from({ length: 10 }, (_, index) => ({
    draft_slot: index + 1,
    display_name: `Team ${index + 1}`,
    is_user: index === 1,
  })),
  current_pick: {
    overall_pick: 1,
    round_number: 1,
    pick_in_round: 1,
    selecting_slot: 1,
    selecting_team: "Team 1",
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

const snapshot = {
  id: "snapshot-1",
  content_hash: "safe-hash",
  source_label: "Neighborhood Synthetic Market",
  source_kind: "synthetic" as const,
  source_namespace: "sanitized_fixture",
  source_as_of: "2026-07-28T00:00:00Z",
  imported_at: "2026-07-28T01:00:00Z",
  status: "active",
  schema_version: 1,
  compatibility_state: "exact" as const,
  freshness_states: { market: "fresh" },
  format: {
    league_type: "dynasty" as const,
    draft_purpose: "startup" as const,
    team_count: 10,
    draft_format: "snake" as const,
    third_round_reversal: true,
    rounds: 24,
    qb_mode: "superflex" as const,
    reception_scoring: "ppr" as const,
    te_premium: true,
  },
  supported_draft_depth: 240,
  mapped_player_count: 10,
  expected_selection_count: 10,
  pick_value_count: 12,
  expected_selection_available: true,
  pick_curve_available: true,
  limitation_codes: [],
};

const configuration: DraftAlertConfiguration = {
  id: "configuration-1",
  draft_session_id: draft.id,
  draft_revision: draft.revision,
  evidence_snapshot_id: snapshot.id,
  enabled: true,
  personal_qualifier_mode: "tier_or_favorite",
  eligible_tier_count: 2,
  minimum_conservative_gap: 6,
  snooze_pick_count: 5,
  engine_version: "phase5-v1",
  rule_version: "phase5-alert-rules-v1",
  freshness_policy_version: "phase5-freshness-v1",
  revision: 3,
  format_compatibility: "exact",
  compatibility_reasons: [],
  evidence_snapshot: snapshot,
  created_at: "2026-07-29T10:00:00Z",
  updated_at: "2026-07-29T10:00:00Z",
};

const baseEvidence = {
  source_label: snapshot.source_label,
  source_as_of: snapshot.source_as_of,
  format_compatibility: "exact" as const,
  expected_selection: { low: 4, high: 8 },
  market_gap: { low: 6, high: 10 },
  return_risk: "unlikely_to_return" as const,
  current_overall_pick: 1,
  next_user_pick: 10,
  personal_reason: {
    manual_rank: 2,
    tier_order: 1,
    favorite: true,
    qualifier_mode: "tier_or_favorite" as const,
    qualified: true,
  },
  components: {
    market: {
      state: "available" as const,
      band: "premium",
      reasons: ["compatible_market_window"],
    },
    production: {
      state: "unavailable" as const,
      band: null,
      reasons: ["production_unavailable"],
    },
    age_risk: {
      state: "available" as const,
      band: "middle",
      reasons: ["bounded_age_context"],
    },
  },
  target_pick_window: { low: 4, high: 7 },
  cost_availability: "available" as const,
  confidence_reasons: ["exact_format", "fresh_market_evidence"],
  limitation_codes: ["PICK_COST_REFERENCE_ONLY"],
  engine_version: "phase5-v1",
  rule_version: "phase5-alert-rules-v1",
  freshness_policy_version: "phase5-freshness-v1",
  configuration_revision: configuration.revision,
  draft_revision: draft.revision,
};

const valueEvent = {
  id: "alert-value",
  kind: "value_watch" as const,
  status: "open" as const,
  confidence: "high" as const,
  freshness: "fresh" as const,
  first_confirmed_draft_revision: 7,
  last_confirmed_draft_revision: 7,
  explanation_template_keys: ["value_watch_personal_market_gap"],
  limitation_codes: ["PICK_COST_REFERENCE_ONLY"],
  snooze_boundary: null,
  dismissed_at: null,
  superseded_at: null,
  evidence: baseEvidence,
  created_at: "2026-07-29T10:01:00Z",
  updated_at: "2026-07-29T10:01:00Z",
};

const returnEvent = {
  ...valueEvent,
  id: "alert-return",
  kind: "return_risk" as const,
  confidence: "medium" as const,
};

const alertList: DraftAlertList = {
  scope: "current",
  evaluation_state: "current",
  draft_revision: draft.revision,
  configuration_revision: configuration.revision,
  alerts_enabled: true,
  latest_evaluation: {
    id: "evaluation-1",
    draft_revision: draft.revision,
    configuration_revision: configuration.revision,
    current_overall_pick: 1,
    next_user_pick: 10,
    candidate_count: 2,
    opened_count: 2,
    updated_count: 0,
    superseded_count: 0,
    limitation_codes: [],
    evaluated_at: "2026-07-29T10:01:00Z",
    idempotent: false,
  },
  items: [
    {
      player: {
        id: "player-1",
        display_name: "Marcus Hale",
        primary_position: "QB",
        team: "CHI",
      },
      events: [valueEvent, returnEvent],
    },
  ],
  total: 1,
  limit: 25,
  offset: 0,
};

const unevaluatedAlertList: DraftAlertList = {
  ...alertList,
  evaluation_state: "missing",
  latest_evaluation: null,
  items: [],
  total: 0,
};

const detail: AlertDetail = {
  player: alertList.items[0].player,
  event: valueEvent,
  original_evidence: baseEvidence,
  current_evidence: baseEvidence,
  trade_reference: {
    target_pick_window: { low: 4, high: 7 },
    target_round_pick_labels: ["1.04", "1.07"],
    incremental_cost: { low: 120, high: 180 },
    pick_only_references: [
      {
        label: "Future first",
        season_offset: 1,
        round: 1,
        value: { low: 500, high: 650 },
      },
    ],
    cost_availability: "available",
    explanation_template_key: "pick_only_cost_band",
    limitation_codes: ["PICK_COST_REFERENCE_ONLY"],
  },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("DraftAlertRail", () => {
  it("restores a current saved evaluation after restart without a stale re-evaluation", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/alert-configuration")) {
          return response(configuration);
        }
        if (url.includes("/alerts?scope=current")) {
          return response(alertList);
        }
        if (url.endsWith("/alerts/evaluate") && init?.method === "POST") {
          throw new Error("A current saved evaluation must not be re-evaluated.");
        }
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftAlertRail draft={draft} />);

    expect(await screen.findByText("Marcus Hale")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          String(url).endsWith("/alerts/evaluate") &&
          init?.method === "POST",
      ),
    ).toBe(false);
  });

  it("evaluates grouped alerts and opens a privacy-safe evidence drawer", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/alert-configuration")) {
          return response(configuration);
        }
        if (url.includes("/alerts?scope=current")) {
          return response(unevaluatedAlertList);
        }
        if (url.endsWith("/alerts/evaluate") && init?.method === "POST") {
          return response({
            evaluation: alertList.latest_evaluation,
            alerts: alertList,
          });
        }
        if (url.endsWith("/alerts/alert-value")) {
          return response(detail);
        }
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftAlertRail draft={draft} />);

    expect(await screen.findByText("Marcus Hale")).toBeInTheDocument();
    expect(screen.getByText("Value watch")).toBeInTheDocument();
    expect(screen.getByText("Return risk")).toBeInTheDocument();
    expect(screen.getByText("Conservative gap: spots 6–10")).toBeInTheDocument();
    expect(screen.getByText("Age Risk").closest("span")).toHaveTextContent(
      "Age Risk Middle",
    );
    expect(screen.getByText("Fresh")).toBeInTheDocument();
    expect(screen.getByText("picks 4–7")).toBeInTheDocument();
    expect(screen.getByText("Pick Cost Reference Only")).toBeInTheDocument();

    const evaluationCall = fetchMock.mock.calls.find(([url, init]) => {
      return String(url).endsWith("/alerts/evaluate") && init?.method === "POST";
    });
    expect(JSON.parse(String(evaluationCall?.[1]?.body))).toEqual({
      draft_revision: 7,
      configuration_revision: 3,
      expected_current_overall_pick: 1,
      last_evaluation_draft_revision: null,
    });

    fireEvent.click(
      screen.getByRole("button", { name: "Inspect evidence" }),
    );

    const drawer = await screen.findByRole("dialog", {
      name: "Marcus Hale",
    });
    expect(drawer).toHaveTextContent("Neighborhood Synthetic Market");
    expect(drawer).toHaveTextContent("Production");
    expect(drawer).toHaveTextContent("Unavailable");
    expect(drawer).not.toHaveTextContent("Production 0");
    expect(drawer).toHaveTextContent(
      "Confirm any real trade yourself outside the Hub.",
    );
    expect(drawer).not.toHaveTextContent("private-provider-reference");
    expect(drawer).not.toHaveTextContent("configuration-1");
    expect(
      fetchMock.mock.calls.some(([url, init]) => {
        const value = String(url);
        return (
          (value.includes("/picks") || value.includes("/trade")) &&
          init?.method === "POST"
        );
      }),
    ).toBe(false);
  });

  it("requires confirmation to snooze and sends the exact lifecycle guard", async () => {
    let snoozed = false;
    const emptyCurrent: DraftAlertList = {
      ...alertList,
      items: [],
      total: 0,
    };
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/alert-configuration")) {
          return response(configuration);
        }
        if (url.includes("/alerts?scope=current")) {
          return response(snoozed ? emptyCurrent : unevaluatedAlertList);
        }
        if (url.endsWith("/alerts/evaluate") && init?.method === "POST") {
          return response({
            evaluation: alertList.latest_evaluation,
            alerts: snoozed ? emptyCurrent : alertList,
          });
        }
        if (
          url.endsWith("/alerts/alert-value") &&
          init?.method === "PATCH"
        ) {
          snoozed = true;
          return response({
            ...detail,
            event: {
              ...valueEvent,
              status: "snoozed",
              snooze_boundary: 2,
            },
          });
        }
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftAlertRail draft={draft} />);
    fireEvent.click(await screen.findByRole("button", { name: "Snooze" }));

    expect(
      screen.getByRole("dialog", { name: "Snooze alert" }),
    ).toHaveTextContent("5 saved picks or your next turn");
    expect(
      fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).endsWith("/alerts/alert-value") &&
          init?.method === "PATCH",
      ),
    ).toBeUndefined();

    fireEvent.click(screen.getByRole("button", { name: "Confirm snooze" }));

    await waitFor(() => {
      const patchCall = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).endsWith("/alerts/alert-value") &&
          init?.method === "PATCH",
      );
      expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({
        configuration_revision: 3,
        expected_status: "open",
        status: "snoozed",
      });
    });
    expect(
      await screen.findByText(
        "No current decision points meet your personal and evidence thresholds.",
      ),
    ).toBeInTheDocument();
  });

  it("supports alert shortcuts while ignoring form fields", async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/alert-configuration")) {
          return response(configuration);
        }
        if (url.includes("/alerts?scope=current")) {
          return response(unevaluatedAlertList);
        }
        if (url.endsWith("/alerts/evaluate") && init?.method === "POST") {
          return response({
            evaluation: alertList.latest_evaluation,
            alerts: alertList,
          });
        }
        if (url.endsWith("/alerts/alert-value")) return response(detail);
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftAlertRail draft={draft} />);
    await screen.findByText("Marcus Hale");

    const rail = screen.getByRole("complementary", {
      name: "Decision support",
    });
    fireEvent.keyDown(window, { key: "a" });
    expect(rail).toHaveFocus();

    const alertCard = screen.getByText("Marcus Hale").closest("article");
    alertCard?.focus();
    fireEvent.keyDown(window, { key: "e" });
    expect(
      await screen.findByRole("dialog", { name: "Marcus Hale" }),
    ).toBeInTheDocument();
    const closeButton = screen.getByRole("button", { name: "Close" });
    expect(closeButton).toHaveFocus();
    fireEvent.keyDown(closeButton, { key: "Escape" });
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Marcus Hale" }),
      ).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(alertCard).toHaveFocus());

    const kindButton = screen.getByRole("button", { name: "Value watch" });
    kindButton.focus();
    fireEvent.keyDown(kindButton, { key: "s" });
    expect(
      screen.queryByRole("dialog", { name: "Snooze alert" }),
    ).not.toBeInTheDocument();

    alertCard?.focus();
    fireEvent.keyDown(window, { key: "s" });
    expect(
      screen.getByRole("dialog", { name: "Snooze alert" }),
    ).toBeInTheDocument();
    const cancelSnooze = screen.getByRole("button", { name: "Cancel" });
    expect(cancelSnooze).toHaveFocus();
    fireEvent.keyDown(cancelSnooze, { key: "Escape" });
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Snooze alert" }),
      ).not.toBeInTheDocument(),
    );
    await waitFor(() => expect(alertCard).toHaveFocus());
  });

  it("attaches an existing snapshot only after explicit user action", async () => {
    let attached = false;
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/alert-configuration") && !init?.method) {
          return response(
            {
              error: {
                message: "No decision-support evidence is attached.",
              },
            },
            false,
            404,
          );
        }
        if (url.includes("/alert-evidence-snapshots?")) {
          return response({
            items: [snapshot],
            total: 1,
            limit: 100,
            offset: 0,
          });
        }
        if (
          url.endsWith("/alert-configuration") &&
          init?.method === "POST"
        ) {
          attached = true;
          return response(configuration, true, 201);
        }
        if (url.includes("/alerts?scope=current")) {
          return response(unevaluatedAlertList);
        }
        if (url.endsWith("/alerts/evaluate") && init?.method === "POST") {
          return response({
            evaluation: alertList.latest_evaluation,
            alerts: alertList,
          });
        }
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftAlertRail draft={draft} />);

    expect(await screen.findByText("No evidence attached")).toBeInTheDocument();
    expect(attached).toBe(false);
    fireEvent.click(
      screen.getByRole("button", { name: "Attach with defaults" }),
    );

    await waitFor(() => expect(attached).toBe(true));
    const attachCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).endsWith("/alert-configuration") &&
        init?.method === "POST",
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
    expect(await screen.findByText("Marcus Hale")).toBeInTheDocument();
  });

  it("preserves suppressed history and reopens it with the exact status guard", async () => {
    let reopened = false;
    const historyList: DraftAlertList = {
      ...alertList,
      scope: "history",
      items: [
        {
          ...alertList.items[0],
          events: [
            {
              ...valueEvent,
              status: reopened ? "open" : "snoozed",
              snooze_boundary: reopened ? null : 12,
            },
          ],
        },
      ],
    };
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/alert-configuration")) {
          return response(configuration);
        }
        if (url.includes("/alerts?scope=current")) {
          return response(unevaluatedAlertList);
        }
        if (url.endsWith("/alerts/evaluate") && init?.method === "POST") {
          return response({
            evaluation: alertList.latest_evaluation,
            alerts: alertList,
          });
        }
        if (url.includes("/alerts?scope=history")) {
          return response({
            ...historyList,
            items: historyList.items.map((group) => ({
              ...group,
              events: group.events.map((event) => ({
                ...event,
                status: reopened ? "open" : "snoozed",
                snooze_boundary: reopened ? null : 12,
              })),
            })),
          });
        }
        if (
          url.endsWith("/alerts/alert-value") &&
          init?.method === "PATCH"
        ) {
          reopened = true;
          return response(detail);
        }
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftAlertRail draft={draft} />);
    await screen.findByText("Marcus Hale");
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    fireEvent.click(await screen.findByRole("button", { name: "Reopen" }));

    await waitFor(() => expect(reopened).toBe(true));
    const patchCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).endsWith("/alerts/alert-value") &&
        init?.method === "PATCH",
    );
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({
      configuration_revision: 3,
      expected_status: "snoozed",
      status: "open",
    });
    expect(await screen.findByRole("button", { name: "Dismiss" })).toBeEnabled();
  });

  it("disables alerts without mutating the draft or deleting history", async () => {
    const disabledConfiguration = { ...configuration, enabled: false, revision: 4 };
    const disabledList: DraftAlertList = {
      ...alertList,
      alerts_enabled: false,
      items: [],
      total: 0,
    };
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/alert-configuration") && !init?.method) {
          return response(configuration);
        }
        if (url.includes("/alerts?scope=current")) {
          return response(
            fetchMock.mock.calls.some(
              ([calledUrl, calledInit]) =>
                String(calledUrl).endsWith("/alert-configuration") &&
                calledInit?.method === "PATCH",
            )
              ? disabledList
              : unevaluatedAlertList,
          );
        }
        if (url.endsWith("/alerts/evaluate") && init?.method === "POST") {
          return response({
            evaluation: alertList.latest_evaluation,
            alerts: alertList,
          });
        }
        if (
          url.endsWith("/alert-configuration") &&
          init?.method === "PATCH"
        ) {
          return response(disabledConfiguration);
        }
        throw new Error(`Unhandled request: ${url}`);
      },
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<DraftAlertRail draft={draft} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Disable alerts" }),
    );

    expect(
      await screen.findByText(
        "Alerts are disabled. The draft and saved alert history are unchanged.",
      ),
    ).toBeInTheDocument();
    const patchCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        String(url).endsWith("/alert-configuration") &&
        init?.method === "PATCH",
    );
    expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({
      draft_revision: 7,
      configuration_revision: 3,
      enabled: false,
    });
    expect(
      fetchMock.mock.calls.some(([url, init]) => {
        const value = String(url);
        return (
          (value.includes("/picks") || value.includes("/trade")) &&
          ["POST", "PATCH"].includes(String(init?.method))
        );
      }),
    ).toBe(false);
  });
});
