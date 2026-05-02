import { useState, useEffect, useRef } from "react";
import { Loader2, CheckCircle2, Zap, TrendingUp, Rocket, ArrowRight, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePoll } from "@/hooks/usePoll";
import { getStatus, improveModel } from "@/api/client";
import type { StatusResponse } from "@/api/client";
import { LogTerminal, ErrorBanner } from "@/components/app";
import type { ImprovementSnapshot } from "@/steps/ImprovementStep";

type TrainingPhase = "training" | "trained" | "improving" | "improved";

export interface TrainingResult {
  codePath: string | null;
  improved: boolean;
}

interface Props {
  jobId: string;
  modelName: string;
  skipToImprove?: boolean;
  /** Snapshot from a prior improvement step — shown read-only after training. */
  improvementSnapshot?: ImprovementSnapshot | null;
  onSuccess: (result: TrainingResult) => void;
}

const fmt = (n: number | undefined | null, d = 4) =>
  n == null ? "—" : n.toFixed(d);

function MetricDelta({ before, after }: { before: number; after: number }) {
  const delta = after - before;
  const pct = before !== 0 ? (delta / Math.abs(before)) * 100 : 0;
  const better = delta > 0;
  return (
    <span
      className={cn(
        "ml-2 text-[10px] font-semibold px-1.5 py-0.5 rounded",
        better
          ? "bg-emerald-100 text-emerald-600"
          : "bg-red-100 text-red-500"
      )}
    >
      {better ? "+" : ""}
      {pct.toFixed(1)}%
    </span>
  );
}

function MetricsComparison({
  original,
  improved,
}: {
  original: Record<string, number>;
  improved: Record<string, number>;
}) {
  const keys = Object.keys(original);
  if (keys.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-4">
      {/* Before */}
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 space-y-3">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
          Before improvement
        </p>
        {keys.map((k) => (
          <div key={k} className="flex items-center justify-between">
            <span className="text-xs text-slate-500 font-mono">{k}</span>
            <span className="text-xs text-slate-700 font-mono font-semibold">
              {fmt(original[k])}
            </span>
          </div>
        ))}
      </div>

      {/* After */}
      <div className="rounded-2xl border border-pulse-500/25 bg-pulse-500/[0.04] p-4 space-y-3">
        <p className="text-xs font-semibold text-pulse-600 uppercase tracking-wider">
          After improvement
        </p>
        {keys.map((k) => (
          <div key={k} className="flex items-center justify-between">
            <span className="text-xs text-slate-500 font-mono">{k}</span>
            <div className="flex items-center">
              <span className="text-xs text-slate-900 font-mono font-semibold">
                {fmt(improved[k])}
              </span>
              {original[k] != null && improved[k] != null && (
                <MetricDelta before={original[k]} after={improved[k]} />
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function TrainingStep({
  jobId,
  modelName,
  skipToImprove = false,
  improvementSnapshot = null,
  onSuccess,
}: Props) {
  const [phase, setPhase] = useState<TrainingPhase>("training");
  const [trainData, setTrainData] = useState<StatusResponse | null>(null);
  const [improveData, setImproveData] = useState<StatusResponse | null>(null);
  const [improveError, setImproveError] = useState<string | null>(null);
  const [improveLoading, setImproveLoading] = useState(false);
  const autoImproveRef = useRef(false);

  // ── Training poll ────────────────────────────────────────────────────────────
  const { data: trainPollData, error: trainPollError } = usePoll<StatusResponse>({
    fetchFn: () => getStatus(jobId),
    isDone: (d) => d.status === "training_done" || d.status === "error",
    enabled: phase === "training",
    intervalMs: 2000,
    onComplete: (d) => {
      if (d.status === "training_done") {
        setTrainData(d);
        if (skipToImprove) {
          setPhase("improving");
        } else {
          setPhase("trained");
        }
      }
    },
  });

  // ── Auto-start improvement after training completes when skipToImprove ──────
  useEffect(() => {
    if (!skipToImprove || phase !== "improving" || autoImproveRef.current) return;
    autoImproveRef.current = true;
    (async () => {
      try {
        await improveModel(jobId, modelName);
      } catch (err) {
        setImproveError(
          err instanceof Error ? err.message : "Failed to start improvement"
        );
        setPhase("trained");
      }
    })();
  }, [skipToImprove, phase, jobId, modelName]);

  // ── Improvement poll ─────────────────────────────────────────────────────────
  const { data: improvePollData, error: improvePollError } = usePoll<StatusResponse>({
    fetchFn: () => getStatus(jobId),
    isDone: (d) => d.status === "improvement_done" || d.status === "error",
    enabled: phase === "improving",
    intervalMs: 2000,
    onComplete: (d) => {
      if (d.status === "improvement_done") {
        setImproveData(d);
        setPhase("improved");
      }
    },
  });

  const handleImprove = async () => {
    if (improveLoading) return;
    setImproveError(null);
    setImproveLoading(true);
    try {
      await improveModel(jobId, modelName);
      setPhase("improving");
    } catch (err) {
      setImproveError(
        err instanceof Error ? err.message : "Failed to start improvement"
      );
    } finally {
      setImproveLoading(false);
    }
  };

  const trainingLogs = trainPollData?.logs ?? "";
  const improvingLogs = improvePollData?.logs ?? "";

  const originalMetrics =
    improveData?.original_metrics ?? improvePollData?.original_metrics;
  const improvedMetrics =
    improveData?.improved_metrics ?? improvePollData?.improved_metrics;

  return (
    <div className="pipeline-enter w-full space-y-6">
      {/* Header */}
      <div>
        <div className="step-chip mb-4">
          <Zap size={11} />
          Step 5 of 6 — Training &amp; Improvement
        </div>
        <h2 className="text-3xl font-display font-bold text-slate-900 leading-tight">
          {phase === "training" && (
            <>
              Training{" "}
              <span className="bg-gradient-to-r from-pulse-500 to-orange-500 bg-clip-text text-transparent">
                {modelName}
              </span>
            </>
          )}
          {phase === "trained" && (
            <>
              Model{" "}
              <span className="bg-gradient-to-r from-emerald-500 to-teal-500 bg-clip-text text-transparent">
                trained
              </span>
            </>
          )}
          {phase === "improving" && (
            <>
              Improving{" "}
              <span className="bg-gradient-to-r from-purple-500 to-violet-500 bg-clip-text text-transparent">
                the model
              </span>
            </>
          )}
          {phase === "improved" && (
            <>
              Model{" "}
              <span className="bg-gradient-to-r from-pulse-500 to-orange-500 bg-clip-text text-transparent">
                improved
              </span>
            </>
          )}
        </h2>
        <p className="mt-2 text-slate-500 text-sm">
          {phase === "training" && "Generating and executing full training code…"}
          {phase === "trained" && "Training complete. Ready to deploy."}
          {phase === "improving" &&
            "Improvement agent is analysing and rewriting the model…"}
          {phase === "improved" &&
            "Improvement complete. Review the results before deploying."}
        </p>
      </div>

      {/* Training phase */}
      {phase === "training" && (
        <div className="space-y-3">
          <div className="flex items-center gap-2.5">
            <Loader2 size={15} className="text-pulse-500 animate-spin" />
            <span className="text-sm text-slate-500">Training agent is running…</span>
          </div>
          <LogTerminal logs={trainingLogs} maxHeight="max-h-64" />
        </div>
      )}

      {trainPollError && <ErrorBanner message={trainPollError} />}

      {/* Trained phase — success card */}
      {(phase === "trained" || phase === "improving" || phase === "improved") && (
        <div className="pipeline-enter rounded-2xl border bg-emerald-50 border-emerald-200 p-5 space-y-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-100 flex items-center justify-center flex-shrink-0">
              <CheckCircle2 size={18} className="text-emerald-500" />
            </div>
            <div className="min-w-0">
              <p className="text-slate-800 font-semibold text-sm">Training complete</p>
              <p className="text-slate-500 text-xs mt-0.5 truncate">
                Model: {modelName}
              </p>
            </div>
          </div>
          {trainData?.training_code_path && (
            <div className="flex items-start gap-2 text-xs text-slate-500">
              <span className="flex-shrink-0 font-mono text-slate-600">artifact:</span>
              <code className="text-slate-400 font-mono break-all">
                {trainData.training_code_path}
              </code>
            </div>
          )}
        </div>
      )}

      {/* Improving phase */}
      {phase === "improving" && (
        <div className="space-y-3 pipeline-enter">
          <div className="flex items-center gap-2.5">
            <Loader2 size={15} className="text-purple-500 animate-spin" />
            <span className="text-sm text-slate-500">
              Improvement agent is running…
            </span>
          </div>
          <LogTerminal logs={improvingLogs} maxHeight="max-h-52" />
        </div>
      )}

      {improvePollError && <ErrorBanner message={improvePollError} />}

      {/* Before / after comparison */}
      {phase === "improved" && originalMetrics && improvedMetrics && (
        <div className="pipeline-enter space-y-3">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <TrendingUp size={14} className="text-pulse-500" />
            <span>Improvement results</span>
          </div>
          <MetricsComparison original={originalMetrics} improved={improvedMetrics} />
        </div>
      )}

      {improveError && (
        <ErrorBanner
          message={improveError}
          onRetry={() => {
            setImproveError(null);
            handleImprove();
          }}
        />
      )}

      {/* Read-only improvement summary from prior improvement step */}
      {phase === "trained" && improvementSnapshot && (
        <div className="pipeline-enter space-y-3">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <TrendingUp size={14} className="text-pulse-500" />
            <span>Improvement results (from improvement step)</span>
          </div>
          {improvementSnapshot.halted && improvementSnapshot.haltReason && (
            <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 flex items-start gap-3">
              <Info size={16} className="text-blue-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-blue-800">
                  Improvement was not attempted
                </p>
                <p className="text-xs text-blue-700 mt-1 leading-relaxed">
                  {improvementSnapshot.haltReason}
                </p>
              </div>
            </div>
          )}
          {improvementSnapshot.original && improvementSnapshot.improved && (
            <MetricsComparison
              original={improvementSnapshot.original}
              improved={improvementSnapshot.improved}
            />
          )}
        </div>
      )}

      {/* Action buttons */}
      <div className="pipeline-enter space-y-3 pt-1">
        {phase === "trained" && (
          <button
            type="button"
            onClick={() =>
              onSuccess({
                codePath: trainData?.training_code_path ?? null,
                improved: false,
              })
            }
            className="pipeline-btn-primary w-full"
          >
            <Rocket size={17} />
            Go to Deployment
            <ArrowRight size={15} />
          </button>
        )}

        {phase === "improved" && (
          <button
            type="button"
            onClick={() =>
              onSuccess({
                codePath: trainData?.training_code_path ?? null,
                improved: true,
              })
            }
            className="pipeline-btn-primary w-full"
          >
            <Rocket size={17} />
            Deploy Improved Model
            <ArrowRight size={15} />
          </button>
        )}
      </div>
    </div>
  );
}
