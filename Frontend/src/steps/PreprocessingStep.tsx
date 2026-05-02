import { useEffect, useState, useCallback } from "react";
import { Loader2, CheckCircle2, Sparkles, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { usePoll } from "@/hooks/usePoll";
import { getStatus, startPreprocessing } from "@/api/client";
import type { StatusResponse } from "@/api/client";
import { LogTerminal, ErrorBanner } from "@/components/app";

interface PreprocessingResult {
  recommendedModels: string[];
  recommendationsText: string | null;
  preprocessingPlan: Record<string, unknown> | null;
}

interface Props {
  jobId: string;
  onSuccess: (data: PreprocessingResult) => void;
}

function PreprocessingSteps({
  plan,
}: {
  plan: Record<string, unknown> | null;
}) {
  if (!plan) return null;
  const steps =
    (plan as Record<string, unknown[]>)["preprocessing_steps"] ??
    (plan as Record<string, unknown[]>)["steps"] ??
    [];
  if (!Array.isArray(steps) || steps.length === 0) return null;

  return (
    <div className="mt-4 space-y-1.5">
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
        Preprocessing plan
      </p>
      {(steps as Record<string, unknown>[]).map((s, i) => {
        const label =
          (s["step"] as string) ?? (s["action"] as string) ?? `Step ${i + 1}`;
        const reason =
          (s["reason"] as string) ?? (s["justification"] as string) ?? "";
        return (
          <div key={i} className="flex items-start gap-2.5 text-xs">
            <CheckCircle2
              size={13}
              className="text-emerald-500 flex-shrink-0 mt-0.5"
            />
            <div>
              <span className="text-slate-700 font-medium">{label}</span>
              {reason && (
                <span className="text-slate-400 ml-1">— {reason}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function PreprocessingStep({ jobId, onSuccess }: Props) {
  const [startError, setStartError] = useState<string | null>(null);
  const [showSummary, setShowSummary] = useState(false);
  const [summaryData, setSummaryData] = useState<StatusResponse | null>(null);

  const handleStart = useCallback(() => {
    setStartError(null);
    startPreprocessing(jobId).catch((err: unknown) => {
      setStartError(
        err instanceof Error ? err.message : "Failed to start preprocessing"
      );
    });
  }, [jobId]);

  useEffect(() => {
    handleStart();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { data, error: pollError } = usePoll<StatusResponse>({
    fetchFn: () => getStatus(jobId),
    isDone: (d) =>
      d.status === "preprocessing_done" || d.status === "error",
    enabled: !startError,
    intervalMs: 2000,
    maxConsecutiveErrors: 5,
    onComplete: (d) => {
      if (d.status === "preprocessing_done") {
        setSummaryData(d);
        setShowSummary(true);
        setTimeout(() => {
          onSuccess({
            recommendedModels: d.recommended_models,
            recommendationsText: d.recommendations_text,
            preprocessingPlan: d.preprocessing_plan,
          });
        }, 2200);
      }
    },
  });

  const logs = data?.logs ?? "";
  const isError =
    startError ||
    pollError ||
    (data?.status === "error" && data.error);
  const errorMsg = startError ?? pollError ?? data?.error ?? null;

  return (
    <div className="pipeline-enter w-full space-y-6">
      {/* Header */}
      <div>
        <div className="step-chip mb-4">
          <Bot size={11} />
          Step 2 of 6 — Preprocessing
        </div>
        <h2 className="text-3xl font-display font-bold text-slate-900 leading-tight">
          {showSummary ? (
            <>
              Data{" "}
              <span className="bg-gradient-to-r from-emerald-500 to-teal-500 bg-clip-text text-transparent">
                preprocessed
              </span>
            </>
          ) : (
            <>
              Analysing your{" "}
              <span className="bg-gradient-to-r from-pulse-500 to-orange-500 bg-clip-text text-transparent">
                dataset
              </span>
            </>
          )}
        </h2>
        <p className="mt-2 text-slate-500 text-sm">
          {showSummary
            ? "All steps complete — advancing to model selection."
            : "The preprocessing agent is cleaning and profiling your data."}
        </p>
      </div>

      {/* Error */}
      {isError && errorMsg && (
        <ErrorBanner
          message={
            pollError && !startError
              ? `${errorMsg} — The backend may have restarted and lost the job. Please restart the server with "python api_server.py" (without --reload) and re-upload your dataset.`
              : errorMsg
          }
          onRetry={startError ? handleStart : undefined}
        />
      )}

      {/* Summary card — shown when done */}
      {showSummary && summaryData && (
        <div className="pipeline-enter rounded-2xl bg-emerald-50 border border-emerald-200 p-5 space-y-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-100 flex items-center justify-center">
              <CheckCircle2 size={18} className="text-emerald-500" />
            </div>
            <div>
              <p className="text-slate-800 font-semibold text-sm">
                Preprocessing complete
              </p>
              <p className="text-slate-500 text-xs mt-0.5">
                {summaryData.recommended_models.length} model
                {summaryData.recommended_models.length !== 1 ? "s" : ""}{" "}
                recommended
              </p>
            </div>
          </div>

          {/* Recommended model chips */}
          {summaryData.recommended_models.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {summaryData.recommended_models.map((m) => (
                <span
                  key={m}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-pulse-500/10 text-pulse-600 border border-pulse-500/20"
                >
                  <Sparkles size={10} />
                  {m}
                </span>
              ))}
            </div>
          )}

          <PreprocessingSteps plan={summaryData.preprocessing_plan} />
        </div>
      )}

      {/* Log terminal */}
      {!showSummary && (
        <div className="space-y-3">
          <div className="flex items-center gap-2.5">
            <Loader2 size={15} className="text-pulse-500 animate-spin" />
            <span className="text-sm text-slate-500">
              Preprocessing agent is running…
            </span>
          </div>
          <LogTerminal logs={logs} maxHeight="max-h-64" />
        </div>
      )}

      {/* Auto-advance indicator */}
      {showSummary && (
        <div
          className={cn(
            "flex items-center justify-center gap-2 text-xs text-slate-400 pipeline-enter"
          )}
        >
          <Loader2 size={12} className="animate-spin" />
          Advancing to model selection…
        </div>
      )}
    </div>
  );
}
