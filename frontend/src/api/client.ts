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

  constructor(message: string, action?: string, correlationId?: string) {
    super(message);
    this.name = "ApiError";
    this.action = action;
    this.correlationId = correlationId;
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

export function getPlayers(filters: PlayerFilters = {}): Promise<PlayerListResponse> {
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
