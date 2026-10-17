import type {
  AbCompareResult,
  Applicant,
  ApplicationResult,
  BiasInjectResult,
  CounterfactualResponse,
  DecisionResponse,
  DriftResult,
  ExplainResponse,
  HealthResponse,
  JobEvent,
  JobResponse,
  MacroContext,
  MitigationInfo,
  ModelMetadata,
  ModelsResponse,
  PredictResponse,
  SimulationResult,
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
  } catch {
    throw new ApiError(
      "Could not reach the TrustScore API. Is the backend running?",
      0,
    );
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail)
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

export interface ApplicantOptions {
  model?: string | null;
  apply_fairness?: boolean;
  mitigation_attribute?: string | null;
  region?: string;
  use_macro_tilt?: boolean;
}

export interface PolicySimulationRequest {
  approve_max_pd?: number;
  decline_min_pd?: number;
  costs?: { false_approve: number; false_decline: number; review: number };
  apply_fairness?: boolean;
  mitigation_attribute?: string | null;
  model?: string | null;
  margin_rate?: number;
  loss_given_default?: number;
  include_sweep?: boolean;
}

export const api = {
  predict: (applicant: Applicant, model?: string | null) =>
    request<PredictResponse>(
      `/predict${model ? `?model=${encodeURIComponent(model)}` : ""}`,
      { method: "POST", body: JSON.stringify(applicant) },
    ),
  explain: (applicant: Applicant, model?: string | null) =>
    request<ExplainResponse>(
      `/explain${model ? `?model=${encodeURIComponent(model)}` : ""}`,
      { method: "POST", body: JSON.stringify(applicant) },
    ),
  decision: (
    applicant: Applicant,
    overrides?: {
      approve_max_pd?: number;
      decline_min_pd?: number;
      model?: string | null;
      apply_fairness?: boolean;
      mitigation_attribute?: string | null;
      region?: string;
      use_macro_tilt?: boolean;
    },
  ) =>
    request<DecisionResponse>("/decision", {
      method: "POST",
      body: JSON.stringify({ applicant, ...overrides }),
    }),
  counterfactual: (applicant: Applicant, model?: string | null) =>
    request<CounterfactualResponse>(
      `/counterfactual${model ? `?model=${encodeURIComponent(model)}` : ""}`,
      { method: "POST", body: JSON.stringify(applicant) },
    ),
  model: () => request<ModelMetadata>("/model"),
  health: () => request<HealthResponse>("/health"),
  stats: () => request<StatsResponse>("/stats"),

  // --- advanced ---------------------------------------------------------
  submitApplication: (applicant: Applicant, options: ApplicantOptions = {}) =>
    request<JobResponse>("/apply", {
      method: "POST",
      body: JSON.stringify({ applicant, ...options }),
    }),
  getJob: (jobId: string) => request<JobResponse>(`/jobs/${jobId}`),

  policySimulate: (body: PolicySimulationRequest) =>
    request<SimulationResult>("/policy/simulate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  abCompare: (body: {
    model_a?: string | null;
    model_b?: string | null;
    approve_max_pd?: number;
    decline_min_pd?: number;
    mitigation_attribute?: string | null;
  }) =>
    request<AbCompareResult>("/ab/compare", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  biasInject: (body: {
    group: string;
    factor?: number;
    approve_max_pd?: number;
    decline_min_pd?: number;
    mitigation_attribute?: string | null;
  }) =>
    request<BiasInjectResult>("/bias/inject", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  driftLive: (shift = 0) =>
    request<DriftResult>(`/drift/live?shift=${shift}&source=auto`),
  alertTest: (body: { severity?: string; message?: string; shift?: number; deliver?: boolean }) =>
    request<{ delivered: boolean; webhook_configured: boolean; payload: unknown; note: string }>(
      "/alerts/test",
      { method: "POST", body: JSON.stringify(body) },
    ),
  models: () => request<ModelsResponse>("/models"),
  mitigation: () => request<MitigationInfo>("/mitigation"),
  portfolio: () =>
    request<{
      n: number;
      group_attribute: string;
      attributes: string[];
      group_values: Record<string, string[]>;
      fields: string[];
      note: string;
    }>("/portfolio"),
  context: (region = "national") =>
    request<{ regions: { id: string; label: string }[]; context: MacroContext }>(
      `/context?region=${encodeURIComponent(region)}`,
    ),
};

/** Absolute URL for the compliance PDF, suitable for a direct anchor/download. */
export function reportPdfUrl(): string {
  return `${API_BASE}/report.pdf`;
}

// ---------------------------------------------------------------------------
// Job watching: WebSocket when available, polling as a guaranteed fallback.
// ---------------------------------------------------------------------------
export interface JobHandlers {
  onEvent?: (event: JobEvent) => void;
  onDone?: (job: JobResponse) => void;
  onError?: (message: string) => void;
  onTransport?: (transport: "websocket" | "polling") => void;
}

function websocketUrl(jobId: string): string {
  // Relative bases (e.g. "/api") are not usable for a WebSocket path, so fall
  // back to the page origin, which is correct for the containerised deployment.
  if (/^https?:\/\//i.test(API_BASE)) {
    return `${API_BASE.replace(/^http/i, "ws")}/ws/jobs/${jobId}`;
  }
  if (typeof window === "undefined") return "";
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws/jobs/${jobId}`;
}

/**
 * Watch a job to completion. Returns a cancel function.
 *
 * The WebSocket is attempted first because it streams milestones live. If it
 * cannot connect (Vercel serverless functions cannot hold a socket), we degrade
 * to polling `GET /jobs/{id}` -- both paths deliver the same events.
 */
export function watchJob(jobId: string, handlers: JobHandlers): () => void {
  let stopped = false;
  let socket: WebSocket | null = null;
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  const seen = new Set<string>();

  const dispatch = (event: JobEvent) => {
    const key = `${event.step}:${event.at ?? ""}:${event.status}`;
    if (seen.has(key)) return;
    seen.add(key);
    handlers.onEvent?.(event);
  };

  const stop = () => {
    stopped = true;
    if (pollTimer) clearTimeout(pollTimer);
    if (socket && socket.readyState <= WebSocket.OPEN) socket.close();
  };

  const poll = async () => {
    if (stopped) return;
    try {
      const job = await api.getJob(jobId);
      job.events.forEach(dispatch);
      if (job.status === "complete" || job.status === "error") {
        if (job.status === "error") handlers.onError?.(job.error ?? "Job failed");
        handlers.onDone?.(job);
        stop();
        return;
      }
    } catch (err) {
      handlers.onError?.(err instanceof Error ? err.message : "Job lookup failed");
    }
    if (!stopped) pollTimer = setTimeout(poll, 800);
  };

  const startPolling = () => {
    if (stopped || pollTimer) return;
    handlers.onTransport?.("polling");
    void poll();
  };

  const url = websocketUrl(jobId);
  if (url && typeof WebSocket !== "undefined") {
    try {
      socket = new WebSocket(url);
      const fallback = setTimeout(() => {
        if (socket && socket.readyState !== WebSocket.OPEN) startPolling();
      }, 1500);
      socket.onopen = () => {
        clearTimeout(fallback);
        handlers.onTransport?.("websocket");
      };
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as JobEvent;
          dispatch(event);
          if (event.step === "complete") {
            void api
              .getJob(jobId)
              .then((job) => handlers.onDone?.(job))
              .catch(() => handlers.onDone?.(undefined as unknown as JobResponse));
            stop();
          } else if (event.step === "error") {
            handlers.onError?.(event.error ?? "Job failed");
            stop();
          }
        } catch {
          /* ignore malformed frame */
        }
      };
      socket.onerror = () => {
        clearTimeout(fallback);
        socket = null;
        startPolling();
      };
      socket.onclose = () => {
        if (!stopped && (!socket || socket.readyState > WebSocket.CLOSED)) {
          startPolling();
        }
      };
    } catch {
      startPolling();
    }
  } else {
    startPolling();
  }

  return stop;
}

export type { ApplicationResult, JobEvent, JobResponse };
export { ApiError };
