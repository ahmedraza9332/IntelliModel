import { useState } from "react";
import { Check, Loader2, Cpu, ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { validateModels } from "@/api/client";
import { ErrorBanner } from "@/components/app";

interface Props {
  jobId: string;
  recommendedModels: string[];
  recommendationsText: string | null;
  onSuccess: (selectedModels: string[]) => void;
}

/** Best-effort: extract the reason sentence for a model from the raw LLM text. */
function extractReason(text: string | null, name: string): string {
  if (!text) return "Recommended by AI analysis";
  const lower = text.toLowerCase();
  const nameIdx = lower.indexOf(name.toLowerCase());
  if (nameIdx === -1) return "Recommended by AI analysis";
  const after = text.slice(nameIdx, nameIdx + 600);
  const match = after.match(/[Rr]eason[:\s]+([^\n]{10,200})/);
  if (match) return match[1].trim().replace(/\.$/, "") + ".";
  const lines = after.split("\n").filter((l) => l.trim());
  if (lines.length > 1) {
    const second = lines[1].trim().replace(/^[-•*\d.]+\s*/, "");
    if (second.length > 10) return second;
  }
  return "Recommended by AI analysis";
}

export default function ModelSelectionStep({
  jobId,
  recommendedModels,
  recommendationsText,
  onSuccess,
}: Props) {
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(recommendedModels)
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysisOpen, setAnalysisOpen] = useState(false);

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  };

  const handleSubmit = async () => {
    if (selected.size === 0 || loading) return;
    setError(null);
    setLoading(true);
    try {
      await validateModels(jobId, [...selected]);
      onSuccess([...selected]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start validation");
      setLoading(false);
    }
  };

  return (
    <div className="pipeline-enter w-full space-y-6">
      {/* Header */}
      <div>
        <div className="step-chip mb-4">
          <Cpu size={11} />
          Step 3 of 6 — Model Selection
        </div>
        <h2 className="text-3xl font-display font-bold text-slate-900 leading-tight">
          Choose{" "}
          <span className="bg-gradient-to-r from-pulse-500 to-orange-500 bg-clip-text text-transparent">
            models
          </span>{" "}
          to validate
        </h2>
        <p className="mt-2 text-slate-500 text-sm">
          IntelliModel recommends these algorithms for your dataset. Select all
          that you want to benchmark.
        </p>
      </div>

      {/* Model cards */}
      <div className="space-y-3">
        {recommendedModels.length === 0 ? (
          <p className="text-slate-400 text-sm text-center py-8">
            No model recommendations found. Check the preprocessing logs.
          </p>
        ) : (
          recommendedModels.map((name) => {
            const isSelected = selected.has(name);
            const reason = extractReason(recommendationsText, name);
            return (
              <button
                key={name}
                type="button"
                onClick={() => toggle(name)}
                className={cn(
                  "w-full text-left p-4 rounded-2xl border transition-all duration-200",
                  "flex items-start gap-4",
                  isSelected
                    ? "bg-pulse-500/[0.07] border-pulse-500/40 shadow-[0_0_16px_rgba(249,115,22,0.10)]"
                    : "bg-slate-50 border-slate-200 hover:bg-slate-100 hover:border-slate-300"
                )}
              >
                {/* Checkbox */}
                <div
                  className={cn(
                    "mt-0.5 w-5 h-5 rounded-md border flex-shrink-0 flex items-center justify-center transition-all duration-150",
                    isSelected
                      ? "bg-pulse-500 border-pulse-500"
                      : "border-slate-300 bg-white"
                  )}
                >
                  {isSelected && <Check size={12} className="text-white" />}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-slate-900 font-semibold text-sm">
                      {name}
                    </span>
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-pulse-500/10 text-pulse-600 border border-pulse-500/20">
                      <Sparkles size={9} />
                      AI Pick
                    </span>
                  </div>
                  <p className="mt-1 text-slate-500 text-xs leading-relaxed">
                    {reason}
                  </p>
                </div>
              </button>
            );
          })
        )}
      </div>

      {/* Collapsible full AI analysis */}
      {recommendationsText && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 overflow-hidden">
          <button
            type="button"
            onClick={() => setAnalysisOpen((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-3 text-xs text-slate-500 hover:text-slate-700 transition-colors"
          >
            <span className="font-medium uppercase tracking-wider">
              View full AI analysis
            </span>
            {analysisOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          {analysisOpen && (
            <div className="px-4 pb-4 border-t border-slate-200">
              <pre className="text-[11px] text-slate-500 whitespace-pre-wrap leading-relaxed font-mono pt-3">
                {recommendationsText}
              </pre>
            </div>
          )}
        </div>
      )}

      {error && (
        <ErrorBanner
          message={error}
          onRetry={() => {
            setError(null);
            handleSubmit();
          }}
        />
      )}

      {/* Selection count + submit */}
      <div className="space-y-3 pt-1">
        {selected.size > 0 && (
          <p className="text-xs text-slate-400 text-center">
            {selected.size} model{selected.size !== 1 ? "s" : ""} selected
          </p>
        )}
        <button
          type="button"
          disabled={selected.size === 0 || loading}
          onClick={handleSubmit}
          className="pipeline-btn-primary w-full"
        >
          {loading ? (
            <>
              <Loader2 size={17} className="animate-spin" />
              Starting validation…
            </>
          ) : (
            <>
              <Cpu size={17} />
              Run Validation
            </>
          )}
        </button>
        {selected.size === 0 && !loading && (
          <p className="text-center text-xs text-slate-400">
            Select at least one model to continue
          </p>
        )}
      </div>
    </div>
  );
}
