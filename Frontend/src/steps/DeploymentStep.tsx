import { useEffect, useState, useCallback } from "react";
import {
  Copy,
  Check,
  ExternalLink,
  Play,
  Loader2,
  Globe,
  Info,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getDeploymentInfo } from "@/api/client";
import type { DeploymentInfo, FeatureStat } from "@/api/client";
import { ErrorBanner } from "@/components/app";

interface Props {
  jobId: string;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={cn(
        "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-150",
        copied
          ? "bg-emerald-100 text-emerald-600 border border-emerald-200"
          : "bg-slate-100 hover:bg-slate-200 text-slate-500 hover:text-slate-700 border border-slate-200"
      )}
      aria-label="Copy to clipboard"
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
      {copied ? "Copied!" : "Copy"}
    </button>
  );
}

interface TestFormProps {
  deploymentInfo: DeploymentInfo;
}

/** Return today's date as a YYYY-MM-DD string for default date inputs. */
function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

const NUMERIC_DTYPES = new Set([
  "int64", "int32", "int16", "int8",
  "uint64", "uint32", "uint16", "uint8",
  "float64", "float32", "float16",
  "number", "numeric",
]);

/** True when the feature should be treated as a number. */
function isNumericStat(stat?: FeatureStat): boolean {
  if (!stat) return false;
  const dt = (stat.dtype ?? "").toLowerCase();
  return NUMERIC_DTYPES.has(dt);
}

/** Derive a human-readable hint for a feature from its stats. */
function featureHint(stat?: FeatureStat): string | null {
  if (!stat) return null;
  if (stat.field_type === "datetime") {
    if (stat.max_date) return `latest in data: ${stat.max_date.slice(0, 10)}`;
    return "enter a date";
  }
  if (isNumericStat(stat)) {
    if (stat.binary) return "0 or 1";
    if (stat.min != null && stat.max != null) return `${stat.min} – ${stat.max}`;
    if (stat.mean != null && stat.std != null)
      return `avg ${stat.mean.toLocaleString(undefined, { maximumFractionDigits: 1 })} ± ${stat.std.toLocaleString(undefined, { maximumFractionDigits: 1 })}`;
    return "numeric";
  }
  return "text";
}

function TestForm({ deploymentInfo }: TestFormProps) {
  const { predict_url, feature_names, example_predict_payload, feature_stats } = deploymentInfo;
  const [values, setValues] = useState<Record<string, string>>(
    () =>
      Object.fromEntries(
        feature_names.map((f) => {
          const stat = feature_stats?.[f];
          if (stat?.field_type === "datetime") return [f, todayIso()];
          return [f, String(example_predict_payload[f] ?? "")];
        })
      )
  );
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePredict = async () => {
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const payload: Record<string, string | number> = {};
      for (const f of feature_names) {
        const stat = feature_stats?.[f];
        const val = values[f] ?? "";
        if (stat?.field_type === "datetime") {
          // Send the date string exactly as typed; the backend preprocessing
          // script will parse it the same way the training data was parsed.
          if (!val) throw new Error(`"${f}" requires a date value.`);
          payload[f] = val;
        } else if (isNumericStat(stat)) {
          const num = parseFloat(val);
          if (isNaN(num)) {
            throw new Error(`"${f}" must be a number. Got: "${val}"`);
          }
          payload[f] = num;
        } else {
          // Text / categorical / object columns — send as string
          if (!val.trim()) throw new Error(`"${f}" cannot be empty.`);
          payload[f] = val.trim();
        }
      }
      const res = await fetch(predict_url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `HTTP ${res.status}`);
      }
      const json = await res.json();
      const pred = json?.prediction ?? json?.result ?? JSON.stringify(json);
      setResult(String(pred));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Prediction failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div
        className={cn(
          "grid gap-x-4 gap-y-3",
          feature_names.length > 4 ? "grid-cols-2" : "grid-cols-1"
        )}
      >
        {feature_names.map((feat) => {
          const stat = feature_stats?.[feat];
          const hint = featureHint(stat);
          const isNumeric = isNumericStat(stat);
          return (
            <div key={feat}>
              <div className="flex items-center gap-1.5 mb-1">
                <label className="text-xs text-slate-600 font-mono truncate">
                  {feat}
                </label>
                {hint && (
                  <span className="inline-flex items-center gap-0.5 text-[10px] text-slate-400 font-sans whitespace-nowrap">
                    <Info size={9} className="text-slate-300" />
                    {hint}
                  </span>
                )}
              </div>
              {stat?.field_type === "datetime" ? (
                <input
                  type="date"
                  className="pipeline-input text-xs py-2"
                  value={values[feat] ?? todayIso()}
                  onChange={(e) =>
                    setValues((prev) => ({ ...prev, [feat]: e.target.value }))
                  }
                />
              ) : isNumeric ? (
                <input
                  type="number"
                  step="any"
                  className="pipeline-input text-xs py-2"
                  placeholder="enter a number"
                  value={values[feat] ?? ""}
                  onChange={(e) =>
                    setValues((prev) => ({ ...prev, [feat]: e.target.value }))
                  }
                />
              ) : (
                <input
                  type="text"
                  className="pipeline-input text-xs py-2"
                  placeholder="enter a value"
                  value={values[feat] ?? ""}
                  onChange={(e) =>
                    setValues((prev) => ({ ...prev, [feat]: e.target.value }))
                  }
                />
              )}
            </div>
          );
        })}
      </div>

      {error && <ErrorBanner message={error} />}

      {result != null && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-pulse-500/[0.07] border border-pulse-500/25">
          <div>
            <p className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">
              Prediction
              {deploymentInfo.target_column
                ? ` — ${deploymentInfo.target_column}`
                : ""}
            </p>
            <p className="text-2xl font-display font-bold text-pulse-600 mt-0.5">
              {result}
            </p>
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={handlePredict}
        disabled={loading}
        className="pipeline-btn-primary w-full"
      >
        {loading ? (
          <>
            <Loader2 size={16} className="animate-spin" />
            Predicting…
          </>
        ) : (
          <>
            <Play size={16} />
            Run Prediction
          </>
        )}
      </button>
    </div>
  );
}

export default function DeploymentStep({ jobId }: Props) {
  const [info, setInfo] = useState<DeploymentInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showTest, setShowTest] = useState(false);

  const loadData = useCallback(() => {
    setLoading(true);
    setError(null);
    getDeploymentInfo(jobId)
      .then(setInfo)
      .catch((err: unknown) =>
        setError(
          err instanceof Error ? err.message : "Failed to load deployment info"
        )
      )
      .finally(() => setLoading(false));
  }, [jobId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  return (
    <div className="pipeline-enter w-full space-y-6">
      {/* Header */}
      <div>
        <div className="step-chip mb-4">
          <Globe size={11} />
          Step 6 of 6 — Deployment
        </div>
        <h2 className="text-3xl font-display font-bold text-slate-900 leading-tight">
          Your model is{" "}
          <span className="bg-gradient-to-r from-pulse-500 to-orange-500 bg-clip-text text-transparent">
            deployed
          </span>
        </h2>
        <p className="mt-2 text-slate-500 text-sm">
          Use the endpoint below to serve predictions from your trained model.
        </p>
      </div>

      {loading && (
        <div className="flex items-center gap-2.5 text-slate-500 text-sm">
          <Loader2 size={15} className="animate-spin text-pulse-500" />
          Loading deployment info…
        </div>
      )}

      {error && <ErrorBanner message={error} onRetry={loadData} />}

      {info && (
        <>
          {/* Endpoint URL */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5 space-y-3">
            <div className="flex items-center gap-2 text-xs text-slate-500 font-semibold uppercase tracking-wider">
              <Globe size={12} />
              Predict Endpoint
            </div>
            <div className="flex items-center gap-3 flex-wrap">
              <code className="flex-1 min-w-0 font-mono text-sm text-pulse-600 break-all">
                {info.predict_url}
              </code>
              <div className="flex items-center gap-2 flex-shrink-0">
                <CopyButton text={info.predict_url} />
                <a
                  href={info.health_url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-slate-500 hover:text-slate-800 border border-slate-200 hover:border-slate-300 bg-white hover:bg-slate-50 transition-all"
                >
                  <ExternalLink size={11} />
                  Health
                </a>
              </div>
            </div>
          </div>

          {/* Example payload */}
          <div className="rounded-2xl border border-slate-700 bg-slate-900 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-700 bg-slate-800">
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
                <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/70" />
                <span className="ml-2 text-[10px] text-slate-500 font-mono">
                  example · POST /predict
                </span>
              </div>
              <CopyButton
                text={JSON.stringify(info.example_predict_payload, null, 2)}
              />
            </div>
            <pre className="p-4 text-xs font-mono text-slate-400 overflow-x-auto">
              {JSON.stringify(info.example_predict_payload, null, 2)}
            </pre>
          </div>

          {/* Feature list */}
          {info.feature_names.length > 0 && (
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 space-y-2">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                Expected features ({info.feature_names.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {info.feature_names.map((f) => (
                  <code
                    key={f}
                    className="px-2 py-0.5 rounded-md bg-white border border-slate-200 text-xs text-slate-600 font-mono shadow-sm"
                  >
                    {f}
                  </code>
                ))}
              </div>
            </div>
          )}

          {/* Live test panel */}
          <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm">
            <button
              type="button"
              onClick={() => setShowTest((v) => !v)}
              className="w-full flex items-center justify-between px-5 py-4 transition-colors text-sm font-medium text-slate-700 hover:text-slate-900 hover:bg-slate-50"
            >
              <div className="flex items-center gap-2">
                <Play size={15} className="text-pulse-500" />
                Live Test Form
              </div>
              <span className="text-xs text-slate-400">
                {showTest ? "Hide" : "Show"}
              </span>
            </button>

            {showTest && (
              <div className="px-5 pb-5 border-t border-slate-100">
                <p className="text-xs text-slate-400 my-4">
                  Calls{" "}
                  <code className="text-slate-500">{info.predict_url}</code>{" "}
                  directly from the browser. Make sure the deployment server is
                  running.
                </p>
                <TestForm deploymentInfo={info} />
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
