import { useState } from "react";
import {
  Loader2,
  TrendingUp,
  ThumbsUp,
  ThumbsDown,
  RotateCcw,
  Zap,
  CheckCircle2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Rocket,
  Info,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { usePoll } from "@/hooks/usePoll";
import {
  getStatus,
  confirmImprovement,
  discardImprovement,
  improveModel,
} from "@/api/client";
import type { StatusResponse } from "@/api/client";
import { LogTerminal, ErrorBanner } from "@/components/app";

export interface ImprovementSnapshot {
  original: Record<string, number> | null;
  improved: Record<string, number> | null;
  halted: boolean;
  haltReason: string | null;
  improvementRunSucceeded?: boolean | null;
  improvementRunError?: string | null;
  improvementSteps?: string | null;
}

/** Backend says run did not "succeed" and copy indicates metrics were already strong enough. */
export function isMetricsAlreadyExcellentBanner(params: {
  improvement_run_succeeded?: boolean | null;
  improvement_halt_reason?: string | null;
  improvement_steps?: string | null;
}): boolean {
  if (params.improvement_run_succeeded !== false) return false;
  const t = `${params.improvement_halt_reason ?? ""} ${params.improvement_steps ?? ""}`.toLowerCase();
  return (
    t.includes("already excellent") ||
    t.includes("no improvement needed")
  );
}

export function metricsExcellentBannerText(
  improvement_steps: string | null | undefined,
  improvement_halt_reason: string | null | undefined
): string {
  const s = (improvement_steps?.trim() || improvement_halt_reason?.trim() || "").trim();
  return (
    s ||
    "Metrics are already strong enough that no further improvement run was required."
  );
}

type Phase =
  | "improving"   // polling for improvement_done
  | "done"        // results ready, awaiting decision
  | "confirming"  // calling confirmImprovement
  | "discarding"  // calling discardImprovement, then show choices
  | "restarting"; // calling improveModel again before next cycle

type UnsatisfiedChoice = null | "recommend" | "reselect";

interface Props {
  jobId: string;
  modelName: string;
  /** Called after confirmImprovement succeeds — App should then call trainModel. */
  onSatisfied: (snapshot: ImprovementSnapshot) => void;
  /** Called after discardImprovement: re-run re-recommend flow (LLM generates new models). */
  onRecommend: () => void;
  /** Called after discardImprovement: go back to model_selection with existing recommendations. */
  onReselect: () => void;
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
        better ? "bg-emerald-100 text-emerald-600" : "bg-red-100 text-red-500"
      )}
    >
      {better ? "+" : ""}
      {pct.toFixed(1)}%
    </span>
  );
}

function isImprovedMetricsEmpty(
  improved: Record<string, number> | null | undefined,
  keys: string[]
): boolean {
  if (!improved || Object.keys(improved).length === 0) return true;
  return keys.every(
    (k) =>
      improved[k] == null ||
      (typeof improved[k] === "number" && Number.isNaN(improved[k] as number))
  );
}

export function MetricsComparison({
  original,
  improved,
  halted = false,
  improvementRunSucceeded = null,
  improvementRunError = null,
}: {
  original: Record<string, number>;
  improved: Record<string, number> | null | undefined;
  halted?: boolean;
  improvementRunSucceeded?: boolean | null;
  improvementRunError?: string | null;
}) {
  const keys = Object.keys(original);
  if (keys.length === 0) return null;

  const imp = improved ?? {};
  const useBaselineAfter = !halted && isImprovedMetricsEmpty(imp, keys);

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-4">
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

        <div
          className={cn(
            "rounded-2xl border p-4 space-y-3",
            halted || useBaselineAfter
              ? "border-slate-200 bg-slate-50"
              : "border-pulse-500/25 bg-pulse-500/[0.04]"
          )}
        >
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
            <p
              className={cn(
                "text-xs font-semibold uppercase tracking-wider",
                halted || useBaselineAfter ? "text-slate-400" : "text-pulse-600"
              )}
            >
              After improvement
            </p>
            {useBaselineAfter && (
              <span className="text-[10px] font-medium text-slate-400 normal-case tracking-normal">
                (no change)
              </span>
            )}
          </div>
          {keys.map((k) => {
            const rawAfter = halted ? original[k] : imp[k];
            const afterVal =
              halted || rawAfter == null || Number.isNaN(Number(rawAfter))
                ? original[k]
                : rawAfter;
            const showDelta =
              !halted &&
              !useBaselineAfter &&
              original[k] != null &&
              imp[k] != null &&
              !Number.isNaN(Number(imp[k]));

            return (
              <div key={k} className="flex items-center justify-between">
                <span className="text-xs text-slate-500 font-mono">{k}</span>
                <div className="flex items-center">
                  <span
                    className={cn(
                      "text-xs font-mono font-semibold",
                      halted || useBaselineAfter ? "text-slate-500" : "text-slate-900"
                    )}
                  >
                    {fmt(afterVal)}
                  </span>
                  {showDelta && (
                    <MetricDelta before={original[k]} after={imp[k] as number} />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {improvementRunSucceeded === false && improvementRunError ? (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          {improvementRunError}
        </p>
      ) : null}
    </div>
  );
}

function ChangesApplied({ steps }: { steps: string }) {
  const [open, setOpen] = useState(false);
  const lines = steps
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
      >
        <span className="flex items-center gap-2">
          <Zap size={14} className="text-purple-500" />
          Changes applied by the improvement agent
        </span>
        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-1.5 border-t border-slate-100 pt-3">
          {lines.map((line, i) => (
            <p key={i} className="text-xs text-slate-500 leading-relaxed">
              {line}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

function RunsBadge({ count }: { count: number }) {
  const label =
    count === 0
      ? "First improvement run"
      : count === 1
        ? "1 improvement run completed"
        : `${count} improvement runs completed`;
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold border bg-slate-100 text-slate-600 border-slate-200">
      <RefreshCw size={11} />
      {label}
    </span>
  );
}

export default function ImprovementStep({
  jobId,
  modelName,
  onSatisfied,
  onRecommend,
  onReselect,
}: Props) {
  const [phase, setPhase] = useState<Phase>("improving");
  const [actionError, setActionError] = useState<string | null>(null);
  const [unsatisfiedChoice, setUnsatisfiedChoice] =
    useState<UnsatisfiedChoice>(null);

  // Snapshot results we display — updated on each completed cycle
  const [displayData, setDisplayData] = useState<{
    original: Record<string, number> | null;
    improved: Record<string, number> | null;
    steps: string | null;
    cycleCount: number;
    halted: boolean;
    haltReason: string | null;
    improvementRunSucceeded: boolean | null;
    improvementRunError: string | null;
  }>({
    original: null,
    improved: null,
    steps: null,
    cycleCount: 0,
    halted: false,
    haltReason: null,
    improvementRunSucceeded: null,
    improvementRunError: null,
  });

  const { data, error: pollError } = usePoll<StatusResponse>({
    fetchFn: () => getStatus(jobId),
    isDone: (d) => d.status === "improvement_done" || d.status === "error",
    enabled: phase === "improving",
    intervalMs: 2000,
    onComplete: (d) => {
      if (d.status === "improvement_done") {
        setDisplayData({
          original: d.original_metrics,
          improved: d.improved_metrics,
          steps: d.improvement_steps,
          cycleCount: d.regeneration_count ?? 0,
          halted: d.improvement_halted ?? false,
          haltReason: d.improvement_halt_reason ?? null,
          improvementRunSucceeded: d.improvement_run_succeeded ?? null,
          improvementRunError: d.improvement_run_error ?? null,
        });
        setPhase("done");
      }
    },
  });

  const logs = data?.logs ?? "";
  const isError = data?.status === "error";

  // ── Action: satisfied → confirm + train ────────────────────────────────────
  const handleSatisfied = async () => {
    setActionError(null);
    setPhase("confirming");
    try {
      await confirmImprovement(jobId);
      onSatisfied({
        original: displayData.original,
        improved: displayData.improved,
        halted: displayData.halted,
        haltReason: displayData.haltReason,
        improvementRunSucceeded: displayData.improvementRunSucceeded,
        improvementRunError: displayData.improvementRunError,
        improvementSteps: displayData.steps,
      });
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to confirm improvement"
      );
      setPhase("done");
    }
  };

  // ── Action: try another improvement cycle ───────────────────────────────────
  const handleTryAgain = async () => {
    setActionError(null);
    setPhase("restarting");
    try {
      await improveModel(jobId, modelName);
      setPhase("improving");
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to start new improvement cycle"
      );
      setPhase("done");
    }
  };

  // ── Action: not satisfied → discard, then show choices ─────────────────────
  const handleChooseDifferent = async () => {
    setActionError(null);
    setPhase("discarding");
    try {
      await discardImprovement(jobId);
      // Stay in "discarding" phase to reveal the two sub-choices below
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : "Failed to discard improvement"
      );
      setPhase("done");
    }
  };

  return (
    <div className="pipeline-enter w-full space-y-6">
      {/* Header */}
      <div>
        <div className="step-chip mb-4">
          <Zap size={11} />
          Step 5 of 7 — Improvement
        </div>
        <h2 className="text-3xl font-display font-bold text-slate-900 leading-tight">
          {phase === "improving" || phase === "restarting" ? (
            <>
              Improving{" "}
              <span className="bg-gradient-to-r from-purple-500 to-violet-500 bg-clip-text text-transparent">
                the model
              </span>
            </>
          ) : phase === "confirming" ? (
            <>
              Confirming{" "}
              <span className="bg-gradient-to-r from-emerald-500 to-teal-500 bg-clip-text text-transparent">
                improvement
              </span>
            </>
          ) : phase === "discarding" ? (
            <>
              Discarding{" "}
              <span className="bg-gradient-to-r from-slate-500 to-slate-400 bg-clip-text text-transparent">
                improvement
              </span>
            </>
          ) : (
            <>
              Improvement{" "}
              <span className="bg-gradient-to-r from-pulse-500 to-orange-500 bg-clip-text text-transparent">
                complete
              </span>
            </>
          )}
        </h2>
        <p className="mt-2 text-slate-500 text-sm">
          {(phase === "improving" || phase === "restarting") &&
            `Improvement agent is analysing and rewriting ${modelName}…`}
          {phase === "done" &&
            "Review the results below and decide how to proceed."}
          {phase === "confirming" && "Persisting improved code path…"}
          {phase === "discarding" && "Improvement discarded. Choose your next step."}
        </p>
      </div>

      {/* Running / restarting log */}
      {(phase === "improving" || phase === "restarting") && (
        <div className="space-y-3">
          <div className="flex items-center gap-2.5">
            <Loader2 size={15} className="text-purple-500 animate-spin" />
            <span className="text-sm text-slate-500">
              {phase === "restarting"
                ? "Starting new improvement cycle…"
                : "Improvement agent is running…"}
            </span>
          </div>
          {phase === "improving" && (
            <LogTerminal logs={logs} maxHeight="max-h-64" />
          )}
        </div>
      )}

      {/* Confirming spinner */}
      {phase === "confirming" && (
        <div className="flex items-center gap-2.5 py-4">
          <Loader2 size={15} className="text-emerald-500 animate-spin" />
          <span className="text-sm text-slate-500">Saving improved code path…</span>
        </div>
      )}

      {/* Errors */}
      {(pollError || isError) && (
        <ErrorBanner
          message={pollError ?? data?.error ?? "Improvement failed"}
        />
      )}
      {actionError && <ErrorBanner message={actionError} />}

      {/* Results section (visible when done or discarding) */}
      {(phase === "done" || phase === "discarding") && (
        <>
          {(() => {
            const showExcellentOnly = isMetricsAlreadyExcellentBanner({
              improvement_run_succeeded: displayData.improvementRunSucceeded,
              improvement_halt_reason: displayData.haltReason,
              improvement_steps: displayData.steps,
            });
            const hasOriginalMetrics =
              displayData.original && Object.keys(displayData.original).length > 0;

            return (
              <>
                {/* Cycles counter */}
                <div className="flex items-center gap-3">
                  <RunsBadge count={displayData.cycleCount} />
                  {hasOriginalMetrics && (
                    <span className="text-xs text-slate-400 flex items-center gap-1">
                      <TrendingUp size={11} />
                      Metrics for {modelName}
                    </span>
                  )}
                </div>

                {/* Metrics already excellent — single success message, no steps/code UI */}
                {showExcellentOnly && (
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 flex items-start gap-3 shadow-sm">
                    <CheckCircle2
                      size={20}
                      className="text-emerald-600 flex-shrink-0 mt-0.5"
                    />
                    <p className="text-sm text-emerald-900 leading-relaxed">
                      {metricsExcellentBannerText(
                        displayData.steps,
                        displayData.haltReason
                      )}
                    </p>
                  </div>
                )}

                {/* Halt info banner (dataset infeasible, etc.) — not the "already excellent" path */}
                {!showExcellentOnly && displayData.halted && displayData.haltReason && (
                  <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 flex items-start gap-3">
                    <Info size={16} className="text-blue-500 flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-semibold text-blue-800">
                        Improvement was not attempted
                      </p>
                      <p className="text-xs text-blue-700 mt-1 leading-relaxed">
                        {displayData.haltReason}
                      </p>
                    </div>
                  </div>
                )}

                {/* Before/after metrics (hidden when "already excellent" — banner carries the summary) */}
                {hasOriginalMetrics && !showExcellentOnly ? (
                  <MetricsComparison
                    original={displayData.original!}
                    improved={displayData.improved ?? {}}
                    halted={displayData.halted}
                    improvementRunSucceeded={displayData.improvementRunSucceeded}
                    improvementRunError={displayData.improvementRunError}
                  />
                ) : !hasOriginalMetrics ? (
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 flex items-center gap-3">
                    <CheckCircle2 size={16} className="text-emerald-500 flex-shrink-0" />
                    <span className="text-sm text-slate-700">
                      Improvement complete for {modelName}.
                    </span>
                  </div>
                ) : null}

                {/* Changes applied (collapsible) — hidden when metrics were already excellent */}
                {displayData.steps && !showExcellentOnly && (
                  <ChangesApplied steps={displayData.steps} />
                )}
              </>
            );
          })()}
        </>
      )}

      {/* Decision buttons — shown when done */}
      {phase === "done" && (
        <div className="pipeline-enter rounded-2xl border border-slate-200 bg-white p-6 space-y-3">
          <p className="text-sm font-semibold text-slate-800">
            What would you like to do?
          </p>

          {/* Row 1: Deploy + Try again */}
          <div className="flex gap-3">
            {/* Deploy / Full Training */}
            <button
              type="button"
              onClick={handleSatisfied}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 border-emerald-200 bg-emerald-50 text-emerald-700 font-semibold text-sm hover:bg-emerald-100 hover:border-emerald-300 transition-all"
            >
              <Rocket size={16} />
              Deploy / Full Training
            </button>

            {/* Try another cycle */}
            <button
              type="button"
              onClick={handleTryAgain}
              title="Run the improvement agent again on this model"
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 border-purple-200 bg-purple-50 text-purple-700 hover:bg-purple-100 hover:border-purple-300 text-sm font-semibold transition-all"
            >
              <RefreshCw size={16} />
              Try another improvement
            </button>
          </div>

          {/* Row 2: Choose a different model */}
          <button
            type="button"
            onClick={handleChooseDifferent}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-slate-500 font-medium text-sm hover:bg-slate-100 hover:border-slate-300 transition-all"
          >
            <ThumbsDown size={14} />
            Choose a different model
          </button>
        </div>
      )}

      {/* After discard — choose next path */}
      {phase === "discarding" && (
        <div className="pipeline-enter rounded-2xl border border-slate-200 bg-white p-6 space-y-4">
          <p className="text-sm font-semibold text-slate-800">
            What would you like to do instead?
          </p>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => {
                setUnsatisfiedChoice("recommend");
                onRecommend();
              }}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 text-sm font-semibold transition-all",
                unsatisfiedChoice === "recommend"
                  ? "border-pulse-500 bg-pulse-500/10 text-pulse-600"
                  : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 hover:border-slate-300"
              )}
            >
              <Zap size={16} />
              Generate new model suggestions
            </button>
            <button
              type="button"
              onClick={() => {
                setUnsatisfiedChoice("reselect");
                onReselect();
              }}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border-2 text-sm font-semibold transition-all",
                unsatisfiedChoice === "reselect"
                  ? "border-blue-500 bg-blue-500/10 text-blue-600"
                  : "border-slate-200 bg-slate-50 text-slate-600 hover:bg-slate-100 hover:border-slate-300"
              )}
            >
              <RotateCcw size={16} />
              Choose from current model list
            </button>
          </div>
        </div>
      )}

      {/* Satisfied indicator while confirming */}
      {phase === "confirming" && (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <ThumbsUp size={14} className="text-emerald-500" />
          <span>Confirmed — preparing for full training…</span>
        </div>
      )}
    </div>
  );
}
