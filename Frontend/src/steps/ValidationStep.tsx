import { useState, useCallback } from "react";
import {
  Loader2,
  Trophy,
  BarChart3,
  RotateCcw,
  Zap,
  Tag,
  ArrowRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { usePoll } from "@/hooks/usePoll";
import { getStatus, trainModel } from "@/api/client";
import type { StatusResponse, ValidationMetricEntry, TaskType } from "@/api/client";
import { LogTerminal, ErrorBanner } from "@/components/app";

interface Props {
  jobId: string;
  onReselect: () => void;
  onImprove: (
    selectedModel: string,
    metrics: Record<string, ValidationMetricEntry> | null
  ) => void;
  /** Called when user skips improvement and trains directly from validation. */
  onSuccess: (
    selectedModel: string,
    metrics: Record<string, ValidationMetricEntry> | null
  ) => void;
}

const fmt = (n: number | undefined | null, d = 4) =>
  n == null ? "—" : n.toFixed(d);

type MetricCol = { key: string; label: string; decimals?: number };

const TASK_COLUMNS: Record<TaskType, MetricCol[]> = {
  regression:     [
    { key: "MAE",  label: "MAE",  decimals: 4 },
    { key: "MSE",  label: "MSE",  decimals: 4 },
    { key: "RMSE", label: "RMSE", decimals: 4 },
    { key: "R2",   label: "R²",   decimals: 4 },
  ],
  classification: [
    { key: "Accuracy",  label: "Accuracy",  decimals: 4 },
    { key: "Precision", label: "Precision", decimals: 4 },
    { key: "Recall",    label: "Recall",    decimals: 4 },
    { key: "F1",        label: "F1",        decimals: 4 },
    { key: "ROC_AUC",   label: "ROC AUC",   decimals: 4 },
  ],
  forecasting: [
    { key: "MAE",  label: "MAE",  decimals: 4 },
    { key: "RMSE", label: "RMSE", decimals: 4 },
    { key: "MAPE", label: "MAPE (%)", decimals: 2 },
  ],
};

const TASK_PRIMARY: Record<TaskType, { key: string; higherIsBetter: boolean }> = {
  regression:     { key: "R2",  higherIsBetter: true  },
  classification: { key: "F1",  higherIsBetter: true  },
  forecasting:    { key: "MAE", higherIsBetter: false },
};

function getMetricValue(m: ValidationMetricEntry["metrics"], key: string): number | undefined {
  return (m as Record<string, number | undefined>)[key]
    ?? (m as Record<string, number | undefined>)[key.toLowerCase()];
}

function bestModelKey(
  metrics: Record<string, ValidationMetricEntry>,
  taskType: TaskType
): string | null {
  const primary = TASK_PRIMARY[taskType] ?? TASK_PRIMARY.regression;
  let best: string | null = null;
  let bestVal = primary.higherIsBetter ? -Infinity : Infinity;

  for (const [name, entry] of Object.entries(metrics)) {
    const v = getMetricValue(entry.metrics, primary.key);
    if (v == null) continue;
    if (primary.higherIsBetter ? v > bestVal : v < bestVal) {
      bestVal = v;
      best = name;
    }
  }
  return best;
}

const TASK_LABEL: Record<TaskType, string> = {
  regression:     "Regression",
  classification: "Classification",
  forecasting:    "Forecasting",
};

export default function ValidationStep({
  jobId,
  onReselect,
  onImprove,
  onSuccess,
}: Props) {
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [improveLoading, setImproveLoading] = useState(false);
  const [trainLoading, setTrainLoading] = useState(false);
  const [trainError, setTrainError] = useState<string | null>(null);

  const { data, error: pollError } = usePoll<StatusResponse>({
    fetchFn: () => getStatus(jobId),
    isDone: (d) =>
      d.status === "validation_done" || d.status === "error",
    intervalMs: 2000,
    onComplete: (d) => {
      if (d.status === "validation_done" && d.validation_metrics) {
        const tt = (d.task_type ?? "regression") as TaskType;
        const best = bestModelKey(d.validation_metrics, tt);
        if (best) setSelectedModel(best);
      }
    },
  });

  const isDone = data?.status === "validation_done";
  const logs = data?.logs ?? "";
  const metrics = data?.validation_metrics;
  const taskType: TaskType = (data?.task_type ?? "regression") as TaskType;
  const columns = TASK_COLUMNS[taskType] ?? TASK_COLUMNS.regression;
  const primaryMeta = TASK_PRIMARY[taskType] ?? TASK_PRIMARY.regression;
  const bestKey = metrics ? bestModelKey(metrics, taskType) : null;

  const handleImprove = useCallback(async () => {
    if (!selectedModel || improveLoading) return;
    setImproveLoading(true);
    onImprove(selectedModel, metrics ?? null);
  }, [selectedModel, improveLoading, onImprove, metrics]);

  const handleTrain = useCallback(async () => {
    if (!selectedModel || trainLoading) return;
    setTrainError(null);
    setTrainLoading(true);
    try {
      await trainModel(jobId, selectedModel);
      onSuccess(selectedModel, metrics ?? null);
    } catch (err) {
      setTrainError(
        err instanceof Error ? err.message : "Failed to start training"
      );
      setTrainLoading(false);
    }
  }, [jobId, selectedModel, trainLoading, onSuccess, metrics]);

  return (
    <div className="pipeline-enter w-full space-y-6">
      {/* Header */}
      <div>
        <div className="step-chip mb-4">
          <BarChart3 size={11} />
          Step 4 of 7 — Validation Results
        </div>
        <h2 className="text-3xl font-display font-bold text-slate-900 leading-tight">
          {isDone ? (
            <>
              Validation{" "}
              <span className="bg-gradient-to-r from-emerald-500 to-teal-500 bg-clip-text text-transparent">
                complete
              </span>
            </>
          ) : (
            <>
              Validating{" "}
              <span className="bg-gradient-to-r from-pulse-500 to-orange-500 bg-clip-text text-transparent">
                models
              </span>
            </>
          )}
        </h2>
        <p className="mt-2 text-slate-500 text-sm">
          {isDone
            ? "Select a model below, then run the improvement agent or get new suggestions."
            : "Running quick validation on each selected model…"}
        </p>
      </div>

      {/* Log terminal while running */}
      {!isDone && (
        <div className="space-y-3">
          <div className="flex items-center gap-2.5">
            <Loader2 size={15} className="text-pulse-500 animate-spin" />
            <span className="text-sm text-slate-500">
              Validation agent is running…
            </span>
          </div>
          <LogTerminal logs={logs} maxHeight="max-h-52" />
        </div>
      )}

      {/* Poll error */}
      {(pollError || data?.status === "error") && (
        <ErrorBanner
          message={pollError ?? data?.error ?? "Validation failed"}
        />
      )}

      {/* Metrics table */}
      {isDone && metrics && (
        <div className="pipeline-enter space-y-4">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
              <Tag size={11} />
              {TASK_LABEL[taskType] ?? taskType}
            </span>
            <span className="text-xs text-slate-400">
              Best model ranked by {primaryMeta.key} ({primaryMeta.higherIsBetter ? "higher is better" : "lower is better"})
            </span>
          </div>

          <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Model
                  </th>
                  {columns.map((col) => (
                    <th
                      key={col.key}
                      className={cn(
                        "px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider",
                        col.key === primaryMeta.key
                          ? "text-pulse-600"
                          : "text-slate-500"
                      )}
                    >
                      {col.label}
                    </th>
                  ))}
                  <th className="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Select
                  </th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(metrics).map(([name, entry]) => {
                  const isBest = name === bestKey;
                  const isChosen = name === selectedModel;
                  const m = entry.metrics;
                  return (
                    <tr
                      key={name}
                      onClick={() => setSelectedModel(name)}
                      className={cn(
                        "border-b border-slate-100 last:border-0 cursor-pointer transition-colors duration-150",
                        isBest && "bg-pulse-500/[0.05]",
                        isChosen && !isBest && "bg-slate-50",
                        "hover:bg-slate-50"
                      )}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span
                            className={cn(
                              "font-medium text-sm",
                              isBest ? "text-slate-900" : "text-slate-700"
                            )}
                          >
                            {name}
                          </span>
                          {isBest && (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-pulse-500/15 text-pulse-600 border border-pulse-500/25">
                              <Trophy size={9} />
                              Best {primaryMeta.key}
                            </span>
                          )}
                        </div>
                      </td>
                      {columns.map((col) => {
                        const isPrimary = col.key === primaryMeta.key;
                        const val = getMetricValue(m, col.key);
                        return (
                          <td
                            key={col.key}
                            className={cn(
                              "px-4 py-3 text-right font-mono text-xs",
                              isPrimary && isBest
                                ? "text-pulse-600 font-semibold"
                                : "text-slate-500"
                            )}
                          >
                            {fmt(val, col.decimals ?? 4)}
                          </td>
                        );
                      })}
                      <td className="px-4 py-3 text-right">
                        <div
                          className={cn(
                            "ml-auto w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all",
                            isChosen
                              ? "bg-pulse-500 border-pulse-500"
                              : "border-slate-300"
                          )}
                        >
                          {isChosen && (
                            <div className="w-2 h-2 rounded-full bg-white" />
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <p className="text-xs text-slate-400">
            Click a row to select the model you want to proceed with. The best {primaryMeta.key} model is pre-selected.
          </p>
        </div>
      )}

      {/* Action buttons */}
      {isDone && metrics && (
        <div className="pipeline-enter rounded-2xl border border-slate-200 bg-white p-6 space-y-4">
          <p className="text-sm font-semibold text-slate-800">
            What would you like to do?
          </p>

          {trainError && (
            <ErrorBanner
              message={trainError}
              onRetry={() => {
                setTrainError(null);
                handleTrain();
              }}
            />
          )}

          {/* Primary actions row */}
          <div className="flex gap-3">
            <button
              type="button"
              onClick={handleTrain}
              disabled={!selectedModel || trainLoading || improveLoading}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 border-emerald-200 bg-emerald-50 text-emerald-700 font-semibold text-sm hover:bg-emerald-100 hover:border-emerald-300 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {trainLoading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Starting training…
                </>
              ) : (
                <>
                  <ArrowRight size={16} />
                  Train on full dataset
                  {selectedModel && (
                    <span className="font-normal opacity-60 text-xs">
                      ({selectedModel})
                    </span>
                  )}
                </>
              )}
            </button>
            <button
              type="button"
              onClick={handleImprove}
              disabled={!selectedModel || improveLoading || trainLoading}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 text-sm font-semibold transition-all",
                !selectedModel || improveLoading || trainLoading
                  ? "border-slate-200 bg-slate-50 text-slate-400 cursor-not-allowed"
                  : "border-purple-200 bg-purple-50 text-purple-700 hover:bg-purple-100 hover:border-purple-300"
              )}
            >
              {improveLoading ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Starting improvement…
                </>
              ) : (
                <>
                  <Zap size={16} />
                  Run improvement agent
                  {selectedModel && (
                    <span className="font-normal opacity-60 text-xs">
                      ({selectedModel})
                    </span>
                  )}
                </>
              )}
            </button>
          </div>

          {/* Secondary action */}
          <button
            type="button"
            onClick={onReselect}
            disabled={trainLoading || improveLoading}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-slate-500 font-medium text-sm hover:bg-slate-100 hover:border-slate-300 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RotateCcw size={14} />
            Get new model suggestions
          </button>

          {!selectedModel && (
            <p className="text-center text-xs text-slate-400">
              Select a model from the table above first
            </p>
          )}
        </div>
      )}
    </div>
  );
}
