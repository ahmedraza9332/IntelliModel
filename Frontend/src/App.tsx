import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import Navbar from "@/components/landing/Navbar";

import type { PipelineStep } from "@/types/pipeline";
import { trainModel, improveModel, reRecommendModels, getStatus } from "@/api/client";
import type { ValidationMetricEntry } from "@/api/client";
import { PipelineProgress, StepSummaryCard } from "@/components/app";
import type { StepSummary } from "@/components/app";

import LandingPage from "@/pages/LandingPage";
import UploadStep from "@/steps/UploadStep";
import type { UploadInfo } from "@/steps/UploadStep";
import PreprocessingStep from "@/steps/PreprocessingStep";
import ModelSelectionStep from "@/steps/ModelSelectionStep";
import ValidationStep from "@/steps/ValidationStep";
import ImprovementStep from "@/steps/ImprovementStep";
import type { ImprovementSnapshot } from "@/steps/ImprovementStep";
import TrainingStep from "@/steps/TrainingStep";
import type { TrainingResult } from "@/steps/TrainingStep";
import DeploymentStep from "@/steps/DeploymentStep";

const queryClient = new QueryClient();

// ─── Pipeline view (route: /try-now) ─────────────────────────────────────────

function PipelineView() {
  // ── Core state ──────────────────────────────────────────────────────────────
  const [step, setStep] = useState<PipelineStep>("upload");
  const [jobId, setJobId] = useState<string | null>(null);
  const [summaries, setSummaries] = useState<StepSummary[]>([]);

  // ── Data passed between steps ────────────────────────────────────────────────
  const [recommendedModels, setRecommendedModels] = useState<string[]>([]);
  const [recommendationsText, setRecommendationsText] = useState<string | null>(null);
  const [selectedTrainingModel, setSelectedTrainingModel] = useState<string | null>(null);
  const [improvementSnapshot, setImprovementSnapshot] = useState<ImprovementSnapshot | null>(null);

  // ── Auto-scroll to the active step card on every transition ─────────────────
  const activeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (step !== "upload") {
      const id = setTimeout(() => {
        activeRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 150);
      return () => clearTimeout(id);
    }
  }, [step]);

  const addSummary = (s: StepSummary) =>
    setSummaries((prev) => [...prev, s]);

  // ── Step transition handlers ─────────────────────────────────────────────────

  const handleUploadSuccess = (id: string, info: UploadInfo) => {
    setJobId(id);
    addSummary({
      stepId: "upload",
      headline: `${info.filename} uploaded`,
      details: `Target: ${info.targetColumn}`,
      richData: {
        kind: "upload",
        filename: info.filename,
        targetColumn: info.targetColumn,
        goal: info.goal,
      },
    });
    setStep("preprocessing");
  };

  const handlePreprocessingSuccess = (data: {
    recommendedModels: string[];
    recommendationsText: string | null;
    preprocessingPlan: Record<string, unknown> | null;
  }) => {
    setRecommendedModels(data.recommendedModels);
    setRecommendationsText(data.recommendationsText);
    addSummary({
      stepId: "preprocessing",
      headline: "Preprocessing complete",
      details: `${data.recommendedModels.length} models recommended`,
      richData: {
        kind: "preprocessing",
        models: data.recommendedModels,
        plan: data.preprocessingPlan,
        recommendationsText: data.recommendationsText,
      },
    });
    setStep("model_selection");
  };

  const handleModelSelectionSuccess = (selectedModels: string[]) => {
    addSummary({
      stepId: "model_selection",
      headline: "Models selected for validation",
      details: selectedModels.join(", "),
      richData: {
        kind: "model_selection",
        selected: selectedModels,
      },
    });
    setStep("validation");
  };

  const [reRecommendLoading, setReRecommendLoading] = useState(false);

  const handleValidationReselect = async () => {
    if (!jobId) return;
    setSummaries((prev) =>
      prev.filter((s) => s.stepId !== "model_selection" && s.stepId !== "validation")
    );
    setReRecommendLoading(true);
    try {
      await reRecommendModels(jobId);
      const poll = async () => {
        for (let i = 0; i < 300; i++) {
          await new Promise((r) => setTimeout(r, 2000));
          const s = await getStatus(jobId);
          if (s.status === "preprocessing_done") {
            setRecommendedModels(s.recommended_models);
            setRecommendationsText(s.recommendations_text);
            setReRecommendLoading(false);
            setStep("model_selection");
            return;
          }
          if (s.status === "error") {
            throw new Error(s.error ?? "Re-recommendation failed");
          }
        }
        throw new Error("Re-recommendation timed out");
      };
      await poll();
    } catch {
      setReRecommendLoading(false);
      setStep("model_selection");
    }
  };

  const handleValidationSuccess = async (
    model: string,
    metrics: Record<string, ValidationMetricEntry> | null
  ) => {
    setSelectedTrainingModel(model);
    addSummary({
      stepId: "validation",
      headline: `Best model: ${model}`,
      details: "Validation complete — training on full dataset",
      richData: {
        kind: "validation",
        bestModel: model,
        metrics,
      },
    });
    // trainModel was already called inside ValidationStep; just navigate
    setStep("training");
  };

  const handleValidationImprove = async (
    model: string,
    metrics: Record<string, ValidationMetricEntry> | null
  ) => {
    setSelectedTrainingModel(model);
    addSummary({
      stepId: "validation",
      headline: `${model} selected for improvement`,
      details: "Running improvement agent",
      richData: {
        kind: "validation",
        bestModel: model,
        metrics,
      },
    });
    try {
      await improveModel(jobId!, model);
    } catch {
      // ImprovementStep will surface any errors via polling
    }
    setStep("improvement");
  };

  // Called by ImprovementStep after confirmImprovement succeeds.
  // Now we trigger full training on the (patched) improved code.
  const handleImprovementSatisfied = async (snapshot: ImprovementSnapshot) => {
    setImprovementSnapshot(snapshot);
    if (!jobId || !selectedTrainingModel) return;
    try {
      await trainModel(jobId, selectedTrainingModel);
    } catch {
      // TrainingStep will handle errors via polling
    }
    setStep("training");
  };

  // Called by ImprovementStep "not satisfied" → "Generate new model suggestions"
  const handleImprovementRecommend = () => {
    setSummaries((prev) =>
      prev.filter(
        (s) =>
          s.stepId !== "model_selection" &&
          s.stepId !== "validation" &&
          s.stepId !== "improvement"
      )
    );
    handleValidationReselect();
  };

  // Called by ImprovementStep "not satisfied" → "Choose from current model list"
  const handleImprovementReselect = () => {
    setSummaries((prev) =>
      prev.filter(
        (s) => s.stepId !== "validation" && s.stepId !== "improvement"
      )
    );
    setStep("model_selection");
  };

  const handleTrainingSuccess = (result: TrainingResult) => {
    addSummary({
      stepId: "training",
      headline: result.improved
        ? `${selectedTrainingModel} trained & improved`
        : `${selectedTrainingModel} trained`,
      details: result.codePath
        ? `Artifact: ${result.codePath.split(/[\\/]/).pop()}`
        : "Model ready for deployment",
      richData: {
        kind: "training",
        modelName: selectedTrainingModel ?? "",
        improved: result.improved,
        codePath: result.codePath,
      },
    });
    setStep("deployment");
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="relative min-h-screen bg-slate-50 overflow-x-hidden">
      {/* Subtle ambient glows */}
      <div
        aria-hidden
        className="pointer-events-none fixed top-0 right-0 w-[600px] h-[600px] opacity-20 z-0"
        style={{
          background:
            "radial-gradient(ellipse at top right, rgba(249,115,22,0.12) 0%, transparent 65%)",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none fixed bottom-0 left-0 w-[400px] h-[400px] opacity-15 z-0"
        style={{
          background:
            "radial-gradient(ellipse at bottom left, rgba(168,85,247,0.10) 0%, transparent 65%)",
        }}
      />
      {/* Dot grid */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 z-0"
        style={{
          backgroundImage:
            "radial-gradient(rgba(0,0,0,0.04) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />

      <Navbar />

      <main className="relative z-10 px-4 sm:px-6 pt-28 pb-24">
        <div className="max-w-3xl mx-auto space-y-4">

          {/* ── Scrollable history of completed steps ── */}
          {summaries.map((s, i) => (
            <StepSummaryCard key={i} summary={s} />
          ))}

          {/* ── Active step card (auto-scrolled to on transition) ── */}
          <div
            ref={activeRef}
            className="pipeline-card p-8 sm:p-10 shadow-md scroll-mt-28"
          >
            {step !== "upload" && <PipelineProgress current={step} />}

            {step === "upload" && (
              <UploadStep onSuccess={handleUploadSuccess} />
            )}

            {step === "preprocessing" && jobId && (
              <PreprocessingStep
                jobId={jobId}
                onSuccess={handlePreprocessingSuccess}
              />
            )}

            {step === "model_selection" && (
              <ModelSelectionStep
                jobId={jobId!}
                recommendedModels={recommendedModels}
                recommendationsText={recommendationsText}
                onSuccess={handleModelSelectionSuccess}
              />
            )}

            {step === "validation" && jobId && !reRecommendLoading && (
              <ValidationStep
                jobId={jobId}
                onSuccess={handleValidationSuccess}
                onReselect={handleValidationReselect}
                onImprove={handleValidationImprove}
              />
            )}

            {reRecommendLoading && (
              <div className="pipeline-enter w-full space-y-6">
                <div>
                  <div className="step-chip mb-4">
                    <Loader2 size={11} className="animate-spin" />
                    Re-recommending
                  </div>
                  <h2 className="text-3xl font-display font-bold text-slate-900 leading-tight">
                    Finding{" "}
                    <span className="bg-gradient-to-r from-pulse-500 to-orange-500 bg-clip-text text-transparent">
                      new models
                    </span>
                  </h2>
                  <p className="mt-2 text-slate-500 text-sm">
                    The LLM is generating alternative model suggestions (excluding previously validated models)…
                  </p>
                </div>
                <div className="flex items-center justify-center gap-2.5 py-8">
                  <Loader2 size={20} className="text-pulse-500 animate-spin" />
                  <span className="text-sm text-slate-500">This may take a minute…</span>
                </div>
              </div>
            )}

            {step === "improvement" && jobId && selectedTrainingModel && (
              <ImprovementStep
                jobId={jobId}
                modelName={selectedTrainingModel}
                onSatisfied={handleImprovementSatisfied}
                onRecommend={handleImprovementRecommend}
                onReselect={handleImprovementReselect}
              />
            )}

            {step === "training" && jobId && selectedTrainingModel && (
              <TrainingStep
                jobId={jobId}
                modelName={selectedTrainingModel}
                improvementSnapshot={improvementSnapshot}
                onSuccess={handleTrainingSuccess}
              />
            )}

            {step === "deployment" && jobId && (
              <DeploymentStep jobId={jobId} />
            )}
          </div>

        </div>
      </main>
    </div>
  );
}

// ─── Root app with routing ────────────────────────────────────────────────────

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Sonner
          theme="light"
          toastOptions={{
            classNames: {
              toast: "bg-white border border-slate-200 text-slate-900 shadow-lg",
              title: "text-slate-900 font-medium",
              description: "text-slate-500",
            },
          }}
        />
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/try-now" element={<PipelineView />} />
            <Route path="*" element={<LandingPage />} />
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
