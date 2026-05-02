/**
 * IntelliModel Workflow API Client
 * Talks to backend/api_server.py running on port 9000.
 * Every function is fully typed against the server's response shapes.
 */

export const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:9000";

// ─── Shared helpers ──────────────────────────────────────────────────────────

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? detail;
    } catch {
      /* ignore parse failure */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

function json(path: string, body: unknown, method = "POST") {
  return request(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

// ─── Response types ───────────────────────────────────────────────────────────

export interface UploadResponse {
  job_id: string;
  filename: string;
  target_column: string;
  goal: string;
  status: "uploaded";
}

export interface StartedResponse {
  status: "started";
  job_id: string;
  /** present on /validate and /improve */
  selected_models?: string[];
  /** present on /train and /improve */
  model_name?: string;
}

export type JobStatus =
  | "uploaded"
  | "preprocessing"
  | "preprocessing_done"
  | "recommending"
  | "validating"
  | "validation_done"
  | "training"
  | "training_done"
  | "improving"
  | "improvement_done"
  | "error";

export type TaskType = "regression" | "classification" | "forecasting";

export interface ValidationMetricEntry {
  metrics: {
    /** Regression */
    MAE?: number; MSE?: number; R2?: number; RMSE?: number;
    mae?: number; mse?: number; r2?: number; rmse?: number;
    /** Classification */
    Accuracy?: number; Precision?: number; Recall?: number; F1?: number; ROC_AUC?: number;
    accuracy?: number; precision?: number; recall?: number; f1?: number; roc_auc?: number;
    /** Forecasting */
    MAPE?: number; mape?: number;
    /** Allow any additional metric the LLM may emit */
    [key: string]: number | undefined;
  };
  code_path?: string;
  task_type?: TaskType;
}

export interface StatusResponse {
  job_id: string;
  status: JobStatus;
  /** Rolling stdout/stderr, capped at last 10 000 chars */
  logs: string;
  error: string | null;
  /** Available after preprocessing_done */
  recommendations_text: string | null;
  recommended_models: string[];
  preprocessing_plan: Record<string, unknown> | null;
  /** Inferred ML task type */
  task_type: TaskType | null;
  /** Available after validation_done */
  validation_metrics: Record<string, ValidationMetricEntry> | null;
  /** Available after training_done */
  training_code_path: string | null;
  /** Available after improvement_done */
  improvement_steps: string | null;
  improved_metrics: Record<string, number> | null;
  original_metrics: Record<string, number> | null;
  /** Number of improvement cycles run so far (0 before any improvement) */
  regeneration_count: number;
  /** True when the improvement agent halted early (e.g. dataset too small) */
  improvement_halted?: boolean;
  /** Human-readable reason for the halt, present when improvement_halted is true */
  improvement_halt_reason?: string | null;
}

export interface FeatureStat {
  dtype?: string;
  /** "datetime" → render a date-picker; absent → numeric or categorical */
  field_type?: "datetime" | "categorical" | "numeric";
  mean?: number;
  std?: number;
  min?: number;
  max?: number;
  /** For datetime fields: earliest date in training data */
  min_date?: string;
  /** For datetime fields: latest date in training data */
  max_date?: string;
  categories?: string[];
  binary?: boolean;
}

export interface DeploymentInfo {
  predict_url: string;
  features_url: string;
  health_url: string;
  example_predict_payload: Record<string, string | number>;
  feature_names: string[];
  target_column: string | null;
  feature_stats?: Record<string, FeatureStat>;
  start_deployment_server: string;
}

// ─── API calls ────────────────────────────────────────────────────────────────

/** POST /api/upload — saves the CSV and returns a job_id. */
export async function uploadDataset(
  file: File,
  targetColumn: string,
  goal: string
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("target_column", targetColumn);
  form.append("goal", goal);
  return request<UploadResponse>("/api/upload", { method: "POST", body: form });
}

/** POST /api/preprocess/{jobId} — starts preprocessing + recommendations. */
export async function startPreprocessing(
  jobId: string
): Promise<StartedResponse> {
  return request<StartedResponse>(`/api/preprocess/${jobId}`, {
    method: "POST",
  });
}

/** POST /api/recommend/{jobId} — re-generate model recommendations excluding previously validated. */
export async function reRecommendModels(
  jobId: string
): Promise<StartedResponse> {
  return request<StartedResponse>(`/api/recommend/${jobId}`, {
    method: "POST",
  });
}

/** GET /api/status/{jobId} — poll for status, logs, and results. */
export async function getStatus(jobId: string): Promise<StatusResponse> {
  return request<StatusResponse>(`/api/status/${jobId}`);
}

/** POST /api/validate/{jobId} — run validation for selected models. */
export async function validateModels(
  jobId: string,
  selectedModels: string[]
): Promise<StartedResponse> {
  return json(`/api/validate/${jobId}`, {
    selected_models: selectedModels,
  }) as Promise<StartedResponse>;
}

/** POST /api/train/{jobId} — generate + run full training code. */
export async function trainModel(
  jobId: string,
  modelName: string
): Promise<StartedResponse> {
  return json(`/api/train/${jobId}`, {
    model_name: modelName,
  }) as Promise<StartedResponse>;
}

/** POST /api/improve/{jobId} — run the improvement agent. */
export async function improveModel(
  jobId: string,
  modelName: string
): Promise<StartedResponse> {
  return json(`/api/improve/${jobId}`, {
    model_name: modelName,
  }) as Promise<StartedResponse>;
}

/** POST /api/confirm_improvement/{jobId} — persist improved code path and reset status to validation_done. */
export async function confirmImprovement(
  jobId: string
): Promise<{ status: string; job_id: string }> {
  return request<{ status: string; job_id: string }>(
    `/api/confirm_improvement/${jobId}`,
    { method: "POST" }
  );
}

/** POST /api/discard_improvement/{jobId} — discard improvement and reset status to validation_done. */
export async function discardImprovement(
  jobId: string
): Promise<{ status: string; job_id: string }> {
  return request<{ status: string; job_id: string }>(
    `/api/discard_improvement/${jobId}`,
    { method: "POST" }
  );
}

/** GET /api/deployment/{jobId} — get predict URL and example payload. */
export async function getDeploymentInfo(
  jobId: string
): Promise<DeploymentInfo> {
  return request<DeploymentInfo>(`/api/deployment/${jobId}`);
}

/** POST /api/target/{jobId} — update the target column for a job (re-try after bad target). */
export async function updateTargetColumn(
  jobId: string,
  targetColumn: string
): Promise<{ status: string }> {
  return json(`/api/target/${jobId}`, { target_column: targetColumn }) as Promise<{
    status: string;
  }>;
}

/** GET /api/health — server heartbeat. */
export async function apiHealth(): Promise<{ status: string }> {
  return request<{ status: string }>("/api/health");
}
