import type { components } from "./schema";

export type AppConfiguration = components["schemas"]["AppConfiguration"];
export type HealthResponse = components["schemas"]["HealthResponse"];
export type LeagueProfileSummary = components["schemas"]["LeagueProfileSummary"];

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
