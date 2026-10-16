import type {
  Applicant,
  CounterfactualResponse,
  DecisionResponse,
  ExplainResponse,
  HealthResponse,
  ModelMetadata,
  PredictResponse,
  StatsResponse,
} from "./types";

// In development the API runs separately on :8000. In production (Vercel) the
// Python function is served under /api on the same origin, so set
// NEXT_PUBLIC_API_BASE_URL=/api there.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(
      "Could not reach the TrustScore API. Is the backend running?",
      0,
    );
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export const api = {
  predict: (applicant: Applicant) =>
    request<PredictResponse>("/predict", {
      method: "POST",
      body: JSON.stringify(applicant),
    }),
  explain: (applicant: Applicant) =>
    request<ExplainResponse>("/explain", {
      method: "POST",
      body: JSON.stringify(applicant),
    }),
  decision: (applicant: Applicant, thresholds?: { approve_max_pd?: number; decline_min_pd?: number }) =>
    request<DecisionResponse>("/decision", {
      method: "POST",
      body: JSON.stringify({ applicant, ...thresholds }),
    }),
  counterfactual: (applicant: Applicant) =>
    request<CounterfactualResponse>("/counterfactual", {
      method: "POST",
      body: JSON.stringify(applicant),
    }),
  model: () => request<ModelMetadata>("/model"),
  health: () => request<HealthResponse>("/health"),
  stats: () => request<StatsResponse>("/stats"),
};

export { ApiError };
