import type { components } from "./schema";

export type AppConfiguration = components["schemas"]["AppConfiguration"];
export type HealthResponse = components["schemas"]["HealthResponse"];
export type LeagueProfileSummary = components["schemas"]["LeagueProfileSummary"];
export type Board = components["schemas"]["BoardRead"];
export type BoardCreate = components["schemas"]["BoardCreate"];
export type BoardEntryCreate = components["schemas"]["BoardEntryCreate"];
export type BoardEntryPatch = components["schemas"]["BoardEntryPatch"];
export type BoardListResponse = components["schemas"]["BoardListResponse"];
export type BoardOrderUpdate = components["schemas"]["BoardOrderUpdate"];
export type BoardPatch = components["schemas"]["BoardPatch"];
export type BoardTierCreate = components["schemas"]["BoardTierCreate"];
export type BoardTierPatch = components["schemas"]["BoardTierPatch"];
export type GutEloActionCreate = components["schemas"]["GutEloActionCreate"];
export type GutEloSession = components["schemas"]["GutEloSessionRead"];
export type GutEloSessionCreate =
  components["schemas"]["GutEloSessionCreate"];
export type GutEloSessionList =
  components["schemas"]["GutEloSessionListResponse"];
export type GutEloSessionPatch = components["schemas"]["GutEloSessionPatch"];
export type DraftCandidateResponse =
  | components["schemas"]["DraftBlindCandidateListResponse"]
  | components["schemas"]["DraftContextCandidateListResponse"];
export type DraftPickCorrection =
  components["schemas"]["DraftPickCorrection"];
export type DraftPickCreate = components["schemas"]["DraftPickCreate"];
export type DraftRevisionGuard = components["schemas"]["DraftRevisionGuard"];
export type DraftSession = components["schemas"]["DraftSessionRead"];
export type DraftSessionCreate = components["schemas"]["DraftSessionCreate"];
export type DraftSessionList =
  components["schemas"]["DraftSessionListResponse"];
export type DraftSessionPatch = components["schemas"]["DraftSessionPatch"];
export type AlertDetail = components["schemas"]["AlertDetailRead"];
export type AlertEvent = components["schemas"]["AlertEventRead"];
export type AlertGroup = components["schemas"]["AlertGroupRead"];
export type DraftAlertConfiguration =
  components["schemas"]["DraftAlertConfigurationRead"];
export type DraftAlertConfigurationCreate =
  components["schemas"]["DraftAlertConfigurationCreate"];
export type DraftAlertConfigurationPatch =
  components["schemas"]["DraftAlertConfigurationPatch"];
export type DraftAlertEvaluationRequest =
  components["schemas"]["DraftAlertEvaluationRequest"];
export type DraftAlertEvaluationResponse =
  components["schemas"]["DraftAlertEvaluationResponse"];
export type DraftAlertEventStatusPatch =
  components["schemas"]["DraftAlertEventStatusPatch"];
export type DraftAlertList =
  components["schemas"]["DraftAlertListResponse"];
export type AlertEvidenceSnapshotList =
  components["schemas"]["AlertEvidenceSnapshotListResponse"];
export type AlertEvidenceSnapshot =
  components["schemas"]["AlertEvidenceSnapshotSummaryRead"];
export type AlertEvidencePreview =
  components["schemas"]["AlertEvidencePreviewRead"];
export type AlertEvidencePreviewRequest =
  components["schemas"]["AlertEvidencePreviewRequest"];
export type AlertEvidenceMappingDecision =
  components["schemas"]["AlertEvidenceMappingDecisionRequest"];
export type AlertEvidenceCommitResponse =
  components["schemas"]["AlertEvidenceCommitResponse"];
export type MockCpuPickCreate = components["schemas"]["MockCpuPickCreate"];
export type MockGuidanceStatusPatch =
  components["schemas"]["MockGuidanceStatusPatch"];
export type MockHistoryList =
  components["schemas"]["MockHistoryListResponse"];
export type MockLearningPatch = components["schemas"]["MockLearningPatch"];
export type MockPickDecision =
  components["schemas"]["MockPickDecisionAudit"];
export type MockSession = components["schemas"]["MockSessionRead"];
export type MockSessionCreate = components["schemas"]["MockSessionCreate"];
export type MockStrategyPivot =
  components["schemas"]["MockStrategyPivotCreate"];
export type CsvPreviewRequest = components["schemas"]["CsvPreviewRequest"];
export type MappingDecisionRequest =
  components["schemas"]["MappingDecisionRequest"];
export type PlayerImportCommitResponse =
  components["schemas"]["PlayerImportCommitResponse"];
export type PlayerImportSession = components["schemas"]["PlayerImportSessionRead"];
export type PlayerListResponse = components["schemas"]["PlayerListResponse"];
export type PlayerPatch = components["schemas"]["PlayerPatch"];
export type Player = components["schemas"]["PlayerRead"];
export type PlayerPosition = Player["primary_position"];
export type PlayerStatus = Player["status"];

export type PlayerFilters = {
  search?: string;
  position?: PlayerPosition | "";
  status?: PlayerStatus | "";
  rookieClass?: number;
  relevantOnly?: boolean;
  limit?: number;
  offset?: number;
};

type ErrorEnvelope = {
  error?: {
    message?: string;
    action?: string;
    correlation_id?: string;
  };
};

export class ApiError extends Error {
  action?: string;
  correlationId?: string;
  status?: number;

  constructor(
    message: string,
    action?: string,
    correlationId?: string,
    status?: number,
  ) {
    super(message);
    this.name = "ApiError";
    this.action = action;
    this.correlationId = correlationId;
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      "X-Friendly-Hub-Request": "1",
      ...init?.headers,
    },
    ...init,
  });

  if (!response.ok) {
    let payload: ErrorEnvelope = {};
    try {
      payload = (await response.json()) as ErrorEnvelope;
    } catch {
      // A safe generic message is used when a response is not JSON.
    }
    throw new ApiError(
      payload.error?.message ?? "The Hub could not complete that request.",
      payload.error?.action,
      payload.error?.correlation_id,
      response.status,
    );
  }

  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request("/api/v1/health");
}

export function getConfiguration(): Promise<AppConfiguration> {
  return request("/api/v1/config");
}

export function saveConfiguration(
  configuration: AppConfiguration,
): Promise<AppConfiguration> {
  return request("/api/v1/config", {
    method: "PUT",
    body: JSON.stringify(configuration),
  });
}

export function getLeagueProfiles(): Promise<LeagueProfileSummary[]> {
  return request("/api/v1/league-profiles");
}

export function loadEntropySample(): Promise<LeagueProfileSummary> {
  return request("/api/v1/league-profiles/samples/entropy", {
    method: "POST",
  });
}

export function getBoards(includeArchived = false): Promise<BoardListResponse> {
  return request(`/api/v1/boards?include_archived=${String(includeArchived)}`);
}

export function createBoard(payload: BoardCreate): Promise<Board> {
  return request("/api/v1/boards", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getBoard(boardId: string): Promise<Board> {
  return request(`/api/v1/boards/${encodeURIComponent(boardId)}`);
}

export function updateBoard(
  boardId: string,
  patch: BoardPatch,
): Promise<Board> {
  return request(`/api/v1/boards/${encodeURIComponent(boardId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function getBoardExportUrl(boardId: string): string {
  return `/api/v1/boards/${encodeURIComponent(boardId)}/export.csv`;
}

export function addBoardTier(
  boardId: string,
  payload: BoardTierCreate,
): Promise<Board> {
  return request(`/api/v1/boards/${encodeURIComponent(boardId)}/tiers`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateBoardTier(
  boardId: string,
  tierId: string,
  patch: BoardTierPatch,
): Promise<Board> {
  return request(
    `/api/v1/boards/${encodeURIComponent(boardId)}/tiers/${encodeURIComponent(tierId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(patch),
    },
  );
}

export function removeBoardTier(
  boardId: string,
  tierId: string,
): Promise<Board> {
  return request(
    `/api/v1/boards/${encodeURIComponent(boardId)}/tiers/${encodeURIComponent(tierId)}`,
    { method: "DELETE" },
  );
}

export function addBoardEntry(
  boardId: string,
  payload: BoardEntryCreate,
): Promise<Board> {
  return request(`/api/v1/boards/${encodeURIComponent(boardId)}/entries`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateBoardEntry(
  boardId: string,
  entryId: string,
  patch: BoardEntryPatch,
): Promise<Board> {
  return request(
    `/api/v1/boards/${encodeURIComponent(boardId)}/entries/${encodeURIComponent(entryId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(patch),
    },
  );
}

export function removeBoardEntry(
  boardId: string,
  entryId: string,
): Promise<Board> {
  return request(
    `/api/v1/boards/${encodeURIComponent(boardId)}/entries/${encodeURIComponent(entryId)}`,
    { method: "DELETE" },
  );
}

export function reorderBoard(
  boardId: string,
  payload: BoardOrderUpdate,
): Promise<Board> {
  return request(`/api/v1/boards/${encodeURIComponent(boardId)}/order`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getGutEloSessions(boardId: string): Promise<GutEloSessionList> {
  return request(
    `/api/v1/boards/${encodeURIComponent(boardId)}/gut-elo-sessions`,
  );
}

export function createGutEloSession(
  boardId: string,
  payload: GutEloSessionCreate,
): Promise<GutEloSession> {
  return request(
    `/api/v1/boards/${encodeURIComponent(boardId)}/gut-elo-sessions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getGutEloSession(
  sessionId: string,
): Promise<GutEloSession> {
  return request(
    `/api/v1/gut-elo-sessions/${encodeURIComponent(sessionId)}`,
  );
}

export function updateGutEloSession(
  sessionId: string,
  patch: GutEloSessionPatch,
): Promise<GutEloSession> {
  return request(
    `/api/v1/gut-elo-sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(patch),
    },
  );
}

export function recordGutEloAction(
  sessionId: string,
  payload: GutEloActionCreate,
): Promise<GutEloSession> {
  return request(
    `/api/v1/gut-elo-sessions/${encodeURIComponent(sessionId)}/actions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function undoGutEloAction(
  sessionId: string,
): Promise<GutEloSession> {
  return request(
    `/api/v1/gut-elo-sessions/${encodeURIComponent(sessionId)}/undo`,
    { method: "POST" },
  );
}

export function getDraftSessions(boardId: string): Promise<DraftSessionList> {
  return request(`/api/v1/boards/${encodeURIComponent(boardId)}/draft-sessions`);
}

export function createDraftSession(
  boardId: string,
  payload: DraftSessionCreate,
): Promise<DraftSession> {
  return request(
    `/api/v1/boards/${encodeURIComponent(boardId)}/draft-sessions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getDraftSession(sessionId: string): Promise<DraftSession> {
  return request(`/api/v1/draft-sessions/${encodeURIComponent(sessionId)}`);
}

export function updateDraftSession(
  sessionId: string,
  payload: DraftSessionPatch,
): Promise<DraftSession> {
  return request(`/api/v1/draft-sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function resetDraftSession(
  sessionId: string,
  payload: DraftRevisionGuard,
): Promise<DraftSession> {
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/reset`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getDraftCandidates(
  sessionId: string,
  options: {
    view: DraftCandidateResponse["view"];
    search?: string;
    positions?: string[];
    includeDrafted?: boolean;
    limit?: number;
    offset?: number;
  },
): Promise<DraftCandidateResponse> {
  const parameters = new URLSearchParams({
    view: options.view,
    include_drafted: String(options.includeDrafted ?? false),
    limit: String(options.limit ?? 200),
    offset: String(options.offset ?? 0),
  });
  if (options.search) parameters.set("search", options.search);
  for (const position of options.positions ?? []) {
    parameters.append("position", position);
  }
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/candidates?${parameters.toString()}`,
  );
}

export function recordDraftPick(
  sessionId: string,
  payload: DraftPickCreate,
): Promise<DraftSession> {
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/picks`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function correctDraftPick(
  sessionId: string,
  overallPick: number,
  payload: DraftPickCorrection,
): Promise<DraftSession> {
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/picks/${overallPick}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function undoDraftPick(
  sessionId: string,
  payload: DraftRevisionGuard,
): Promise<DraftSession> {
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/undo`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getDraftExportUrl(sessionId: string): string {
  return `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/export.csv`;
}

export function getAlertEvidenceSnapshots(
  limit = 100,
  offset = 0,
): Promise<AlertEvidenceSnapshotList> {
  return request(
    `/api/v1/alert-evidence-snapshots?limit=${limit}&offset=${offset}`,
  );
}

export function previewAlertEvidence(
  payload: AlertEvidencePreviewRequest,
): Promise<AlertEvidencePreview> {
  return request("/api/v1/alert-evidence-imports/preview", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function saveAlertEvidenceMapping(
  previewId: string,
  rowId: string,
  payload: AlertEvidenceMappingDecision,
): Promise<AlertEvidencePreview> {
  return request(
    `/api/v1/alert-evidence-imports/${encodeURIComponent(previewId)}/rows/${encodeURIComponent(rowId)}/decision`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
  );
}

export function commitAlertEvidence(
  previewId: string,
  contentHash: string,
): Promise<AlertEvidenceCommitResponse> {
  return request(
    `/api/v1/alert-evidence-imports/${encodeURIComponent(previewId)}/commit`,
    {
      method: "POST",
      body: JSON.stringify({
        content_hash: contentHash,
        permitted_use_confirmed: true,
      }),
    },
  );
}

export function getDraftAlertConfiguration(
  sessionId: string,
): Promise<DraftAlertConfiguration> {
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/alert-configuration`,
  );
}

export function attachDraftAlertConfiguration(
  sessionId: string,
  payload: DraftAlertConfigurationCreate,
): Promise<DraftAlertConfiguration> {
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/alert-configuration`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function updateDraftAlertConfiguration(
  sessionId: string,
  payload: DraftAlertConfigurationPatch,
): Promise<DraftAlertConfiguration> {
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/alert-configuration`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function evaluateDraftAlerts(
  sessionId: string,
  payload: DraftAlertEvaluationRequest,
): Promise<DraftAlertEvaluationResponse> {
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/alerts/evaluate`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getDraftAlerts(
  sessionId: string,
  scope: DraftAlertList["scope"] = "current",
  limit = 25,
  offset = 0,
): Promise<DraftAlertList> {
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/alerts?scope=${scope}&limit=${limit}&offset=${offset}`,
  );
}

export function getDraftAlert(
  sessionId: string,
  alertId: string,
): Promise<AlertDetail> {
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/alerts/${encodeURIComponent(alertId)}`,
  );
}

export function updateDraftAlertStatus(
  sessionId: string,
  alertId: string,
  payload: DraftAlertEventStatusPatch,
): Promise<AlertDetail> {
  return request(
    `/api/v1/draft-sessions/${encodeURIComponent(sessionId)}/alerts/${encodeURIComponent(alertId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function getMockSessions(
  boardId: string,
  limit = 20,
  offset = 0,
): Promise<MockHistoryList> {
  return request(
    `/api/v1/boards/${encodeURIComponent(boardId)}/mock-sessions?limit=${limit}&offset=${offset}`,
  );
}

export function createMockSession(
  boardId: string,
  payload: MockSessionCreate,
): Promise<MockSession> {
  return request(
    `/api/v1/boards/${encodeURIComponent(boardId)}/mock-sessions`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getMockSession(sessionId: string): Promise<MockSession> {
  return request(`/api/v1/mock-sessions/${encodeURIComponent(sessionId)}`);
}

export function advanceMockCpuPick(
  sessionId: string,
  payload: MockCpuPickCreate,
): Promise<MockSession> {
  return request(
    `/api/v1/mock-sessions/${encodeURIComponent(sessionId)}/cpu-pick`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function getMockDecision(
  sessionId: string,
  overallPick: number,
): Promise<MockPickDecision> {
  return request(
    `/api/v1/mock-sessions/${encodeURIComponent(sessionId)}/decisions/${overallPick}`,
  );
}

export function updateMockStrategy(
  sessionId: string,
  payload: MockStrategyPivot,
): Promise<MockSession> {
  return request(
    `/api/v1/mock-sessions/${encodeURIComponent(sessionId)}/strategy`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function updateMockGuidanceStatus(
  sessionId: string,
  eventId: string,
  payload: MockGuidanceStatusPatch,
): Promise<MockSession> {
  return request(
    `/api/v1/mock-sessions/${encodeURIComponent(sessionId)}/guidance/${encodeURIComponent(eventId)}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function updateMockLearning(
  sessionId: string,
  payload: MockLearningPatch,
): Promise<MockSession> {
  return request(
    `/api/v1/mock-sessions/${encodeURIComponent(sessionId)}/learning`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function getPlayers(
  filters: PlayerFilters = {},
): Promise<PlayerListResponse> {
  const parameters = new URLSearchParams();
  if (filters.search) parameters.set("search", filters.search);
  if (filters.position) parameters.set("position", filters.position);
  if (filters.status) parameters.set("status", filters.status);
  if (filters.rookieClass) {
    parameters.set("rookie_class", String(filters.rookieClass));
  }
  parameters.set("relevant_only", String(filters.relevantOnly ?? true));
  parameters.set("limit", String(filters.limit ?? 25));
  parameters.set("offset", String(filters.offset ?? 0));
  return request(`/api/v1/players?${parameters.toString()}`);
}

export function getPlayer(playerId: string): Promise<Player> {
  return request(`/api/v1/players/${encodeURIComponent(playerId)}`);
}

export function updatePlayer(
  playerId: string,
  patch: PlayerPatch,
): Promise<Player> {
  return request(`/api/v1/players/${encodeURIComponent(playerId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function getPlayerExportUrl(): string {
  return "/api/v1/players/export.csv";
}

export function previewPlayerFixture(): Promise<PlayerImportSession> {
  return request("/api/v1/player-imports/fixture/preview", {
    method: "POST",
  });
}

export function previewPlayerCsv(
  payload: CsvPreviewRequest,
): Promise<PlayerImportSession> {
  return request("/api/v1/player-imports/csv/preview", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getPlayerImport(sessionId: string): Promise<PlayerImportSession> {
  return request(`/api/v1/player-imports/${encodeURIComponent(sessionId)}`);
}

export function decidePlayerImportRow(
  sessionId: string,
  rowId: string,
  decision: MappingDecisionRequest,
): Promise<PlayerImportSession> {
  return request(
    `/api/v1/player-imports/${encodeURIComponent(sessionId)}/rows/${encodeURIComponent(rowId)}/decision`,
    {
      method: "PUT",
      body: JSON.stringify(decision),
    },
  );
}

export function commitPlayerImport(
  sessionId: string,
): Promise<PlayerImportCommitResponse> {
  return request(
    `/api/v1/player-imports/${encodeURIComponent(sessionId)}/commit`,
    { method: "POST" },
  );
}

export function cancelPlayerImport(
  sessionId: string,
): Promise<PlayerImportSession> {
  return request(
    `/api/v1/player-imports/${encodeURIComponent(sessionId)}/cancel`,
    { method: "POST" },
  );
}
