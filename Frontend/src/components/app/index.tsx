import { useRef, useEffect } from "react";
import {
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Target,
  Upload,
  Cpu,
  BarChart2,
  Zap,
  TrendingUp,
  FileCode2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { PipelineStep } from "@/types/pipeline";
import type { ValidationMetricEntry } from "@/api/client";

// ─── StepRichData types ────────────────────────────────────────────────────────

export type StepRichData =
  | { kind: "upload"; filename: string; targetColumn: string; goal: string }
  | {
      kind: "preprocessing";
      models: string[];
      plan: Record<string, unknown> | null;
      recommendationsText: string | null;
    }
  | { kind: "model_selection"; selected: string[] }
  | {
      kind: "validation";
      bestModel: string;
      metrics: Record<string, ValidationMetricEntry> | null;
    }
  | {
      kind: "training";
      modelName: string;
      improved: boolean;
      codePath: string | null;
    };

// ─── StepSummary ──────────────────────────────────────────────────────────────

export interface StepSummary {
  stepId: PipelineStep;
  headline: string;
  details: string;
  richData?: StepRichData;
}

// ─── Helper: extract preprocessing steps from plan ────────────────────────────

function extractPlanSteps(
  plan: Record<string, unknown> | null
): Array<{ label: string; reason: string }> {
  if (!plan) return [];
  const raw =
    (plan as Record<string, unknown[]>)["preprocessing_steps"] ??
    (plan as Record<string, unknown[]>)["steps"] ??
    [];
  if (!Array.isArray(raw)) return [];
  return (raw as Record<string, unknown>[]).map((s, i) => ({
    label:
      (s["step"] as string) ?? (s["action"] as string) ?? `Step ${i + 1}`,
    reason:
      (s["reason"] as string) ?? (s["justification"] as string) ?? "",
  }));
}

// ─── Rich content renderers ────────────────────────────────────────────────────

function UploadRich({ d }: { d: Extract<StepRichData, { kind: "upload" }> }) {
  return (
    <div className="mt-3 grid grid-cols-3 gap-2">
      {[
        { label: "File", value: d.filename },
        { label: "Target", value: d.targetColumn },
        { label: "Goal", value: d.goal },
      ].map(({ label, value }) => (
        <div key={label} className="rounded-xl bg-slate-50 border border-slate-200 px-3 py-2">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">{label}</p>
          <p className="text-xs font-medium text-slate-800 mt-0.5 truncate" title={value}>{value}</p>
        </div>
      ))}
    </div>
  );
}

function PreprocessingRich({
  d,
}: {
  d: Extract<StepRichData, { kind: "preprocessing" }>;
}) {
  const planSteps = extractPlanSteps(d.plan);
  return (
    <div className="mt-3 space-y-3">
      {/* Recommended models */}
      {d.models.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
            Recommended models
          </p>
          <div className="flex flex-wrap gap-1.5">
            {d.models.map((m) => (
              <span
                key={m}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-pulse-500/10 text-pulse-600 border border-pulse-500/20"
              >
                <Sparkles size={9} />
                {m}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Preprocessing plan steps */}
      {planSteps.length > 0 && (
        <div>
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
            Preprocessing plan
          </p>
          <div className="space-y-1">
            {planSteps.map(({ label, reason }, i) => (
              <div key={i} className="flex items-start gap-2 text-xs">
                <CheckCircle2 size={12} className="text-emerald-500 flex-shrink-0 mt-0.5" />
                <span>
                  <span className="font-medium text-slate-700">{label}</span>
                  {reason && (
                    <span className="text-slate-400 ml-1">— {reason}</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ModelSelectionRich({
  d,
}: {
  d: Extract<StepRichData, { kind: "model_selection" }>;
}) {
  return (
    <div className="mt-3">
      <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-1.5">
        Selected for validation
      </p>
      <div className="flex flex-wrap gap-1.5">
        {d.selected.map((m) => (
          <span
            key={m}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium bg-slate-100 text-slate-700 border border-slate-200"
          >
            <Cpu size={9} />
            {m}
          </span>
        ))}
      </div>
    </div>
  );
}

function ValidationRich({
  d,
}: {
  d: Extract<StepRichData, { kind: "validation" }>;
}) {
  const entries = d.metrics ? Object.entries(d.metrics) : [];

  // Collect all metric keys that appear across any model (MAE/MSE/R2 etc.)
  const metricKeys = Array.from(
    entries.reduce((acc, [, entry]) => {
      Object.keys(entry.metrics ?? {}).forEach((k) => acc.add(k));
      return acc;
    }, new Set<string>())
  );

  const fmt = (v: number | undefined | null) =>
    v == null ? "—" : v.toFixed(4);

  return (
    <div className="mt-3 space-y-2">
      <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-pulse-500/10 border border-pulse-500/20">
        <TrendingUp size={11} className="text-pulse-600" />
        <span className="text-xs font-semibold text-pulse-600">{d.bestModel}</span>
      </div>
      {entries.length > 0 && metricKeys.length > 0 && (
        <div className="rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th className="text-left px-3 py-2 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                  Model
                </th>
                {metricKeys.map((k) => (
                  <th
                    key={k}
                    className="text-right px-3 py-2 text-[10px] font-semibold text-slate-500 uppercase tracking-wider"
                  >
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map(([model, entry], i) => {
                const m = entry.metrics ?? {};
                return (
                  <tr
                    key={model}
                    className={cn(
                      "border-b last:border-0 border-slate-100",
                      model === d.bestModel
                        ? "bg-pulse-500/[0.04]"
                        : i % 2 === 1
                        ? "bg-slate-50/50"
                        : ""
                    )}
                  >
                    <td className="px-3 py-2 font-medium text-slate-700 whitespace-nowrap">
                      {model === d.bestModel && (
                        <TrendingUp size={10} className="inline mr-1 text-pulse-500" />
                      )}
                      {model}
                    </td>
                    {metricKeys.map((k) => (
                      <td
                        key={k}
                        className={cn(
                          "px-3 py-2 text-right font-mono",
                          k.toUpperCase() === "R2" && model === d.bestModel
                            ? "text-pulse-600 font-semibold"
                            : "text-slate-500"
                        )}
                      >
                        {fmt(m[k as keyof typeof m])}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TrainingRich({
  d,
}: {
  d: Extract<StepRichData, { kind: "training" }>;
}) {
  const filename = d.codePath ? d.codePath.split(/[\\/]/).pop() : null;
  return (
    <div className="mt-3 space-y-2">
      {d.improved && (
        <div className="flex items-center gap-2 text-xs font-medium text-emerald-600">
          <Zap size={12} />
          Model improved by the Improvement Agent
        </div>
      )}
      {filename && (
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <FileCode2 size={12} />
          <span className="font-mono">{filename}</span>
        </div>
      )}
    </div>
  );
}

// ─── Step Summary Card ─────────────────────────────────────────────────────────

const STEP_LABELS_FULL: Record<PipelineStep, string> = {
  upload: "Upload",
  preprocessing: "Preprocessing",
  model_selection: "Model Selection",
  validation: "Validation",
  improvement: "Improvement",
  training: "Training",
  deployment: "Deployment",
};

const STEP_ICONS: Record<PipelineStep, React.ReactNode> = {
  upload: <Upload size={14} className="text-slate-500" />,
  preprocessing: <Target size={14} className="text-emerald-500" />,
  model_selection: <Cpu size={14} className="text-blue-500" />,
  validation: <BarChart2 size={14} className="text-purple-500" />,
  improvement: <Zap size={14} className="text-purple-500" />,
  training: <TrendingUp size={14} className="text-pulse-500" />,
  deployment: <Zap size={14} className="text-amber-500" />,
};

export function StepSummaryCard({ summary }: { summary: StepSummary }) {
  const { stepId, headline, richData } = summary;

  return (
    <div className="w-full px-5 py-4 rounded-2xl bg-white border border-slate-200 shadow-sm pipeline-enter">
      {/* Header row */}
      <div className="flex items-center gap-3">
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center">
          <CheckCircle2 size={14} className="text-emerald-500" />
        </div>
        <div className="flex-1 min-w-0 flex items-center gap-2">
          <span className="flex items-center gap-1.5 text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
            {STEP_ICONS[stepId]}
            {STEP_LABELS_FULL[stepId]}
          </span>
          <span className="text-slate-300">·</span>
          <p className="text-sm font-semibold text-slate-800 truncate">{headline}</p>
        </div>
      </div>

      {/* Rich content */}
      {richData && (
        <>
          {richData.kind === "upload" && <UploadRich d={richData} />}
          {richData.kind === "preprocessing" && <PreprocessingRich d={richData} />}
          {richData.kind === "model_selection" && <ModelSelectionRich d={richData} />}
          {richData.kind === "validation" && <ValidationRich d={richData} />}
          {richData.kind === "training" && <TrainingRich d={richData} />}
        </>
      )}
    </div>
  );
}

// ─── Pipeline Progress ─────────────────────────────────────────────────────────

const STEP_ORDER: PipelineStep[] = [
  "upload",
  "preprocessing",
  "model_selection",
  "validation",
  "improvement",
  "training",
  "deployment",
];

const STEP_LABELS: Record<PipelineStep, string> = {
  upload: "Upload",
  preprocessing: "Process",
  model_selection: "Models",
  validation: "Validate",
  improvement: "Improve",
  training: "Train",
  deployment: "Deploy",
};

export function PipelineProgress({ current }: { current: PipelineStep }) {
  const currentIdx = STEP_ORDER.indexOf(current);

  return (
    <div className="flex items-start mb-10">
      {STEP_ORDER.map((stepId, idx) => {
        const isDone = idx < currentIdx;
        const isActive = idx === currentIdx;
        const isFuture = idx > currentIdx;

        return (
          <div key={stepId} className="flex items-start flex-1 last:flex-none">
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  "w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold transition-all duration-300",
                  isDone &&
                    "bg-pulse-500 text-white shadow-[0_0_10px_rgba(249,115,22,0.3)]",
                  isActive &&
                    "bg-pulse-500/15 border-2 border-pulse-500 text-pulse-600",
                  isFuture &&
                    "bg-slate-100 border border-slate-300 text-slate-400"
                )}
              >
                {isDone ? <CheckCircle2 size={13} /> : <span>{idx + 1}</span>}
              </div>
              <span
                className={cn(
                  "text-[10px] font-medium mt-1 whitespace-nowrap",
                  isDone && "text-pulse-500",
                  isActive && "text-slate-800",
                  isFuture && "text-slate-400"
                )}
              >
                {STEP_LABELS[stepId]}
              </span>
            </div>
            {idx < STEP_ORDER.length - 1 && (
              <div
                className={cn(
                  "flex-1 h-px mt-3.5 mx-1 transition-all duration-500",
                  idx < currentIdx ? "bg-pulse-500/40" : "bg-slate-200"
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ─── Log Terminal ──────────────────────────────────────────────────────────────

interface LogTerminalProps {
  logs: string;
  className?: string;
  maxHeight?: string;
}

function lineColor(line: string): string {
  if (/error|traceback|exception/i.test(line)) return "text-red-400";
  if (/warning|warn/i.test(line)) return "text-yellow-300";
  if (/✓|✔|success|complete|done|saved|generated|finished/i.test(line))
    return "text-emerald-400";
  if (/={3,}|─{3,}|\*{3,}|#{3,}/i.test(line))
    return "text-slate-300 font-medium";
  if (/^\s+[-•]\s/.test(line)) return "text-slate-400";
  return "text-slate-500";
}

export function LogTerminal({
  logs,
  className,
  maxHeight = "max-h-52",
}: LogTerminalProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const lines = logs.split("\n").filter((l) => l.trim());

  return (
    <div
      className={cn(
        "bg-slate-900 border border-slate-700 rounded-xl overflow-hidden",
        className
      )}
    >
      {/* macOS-style titlebar */}
      <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-slate-700/80 bg-slate-800">
        <div className="w-2.5 h-2.5 rounded-full bg-red-500/70" />
        <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
        <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/70" />
        <span className="ml-2 text-[10px] text-slate-500 font-mono tracking-wide">
          agent · stdout
        </span>
      </div>
      <div
        className={cn(
          "p-4 font-mono text-[11px] leading-[1.7] overflow-y-auto",
          maxHeight
        )}
      >
        {lines.length === 0 ? (
          <span className="text-slate-600 animate-pulse">
            Waiting for output…
          </span>
        ) : (
          lines.map((line, i) => (
            <div key={i} className={lineColor(line)}>
              {line}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

// ─── Error Banner ──────────────────────────────────────────────────────────────

interface ErrorBannerProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-600 text-sm">
      <AlertCircle size={15} className="mt-0.5 flex-shrink-0 text-red-500" />
      <div className="flex-1 min-w-0">
        <span>{message}</span>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="ml-3 underline underline-offset-2 hover:text-red-700 transition-colors whitespace-nowrap"
          >
            Try again
          </button>
        )}
      </div>
    </div>
  );
}
