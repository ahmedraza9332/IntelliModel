import React, { useRef, useState, useEffect } from "react";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { cn } from "@/lib/utils";
import {
  UploadCloud,
  ShieldCheck,
  Workflow,
  Sparkles,
  LineChart,
  RefreshCw,
  Settings2,
  CheckCircle2,
  Play,
  Square,
  Download,
  ExternalLink,
  TrendingUp,
  X
} from "lucide-react";
import { toast } from "sonner";
import { Progress } from "@/components/ui/progress";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import api from "@/api/api";
import type {
  DatasetUploadResponse,
  DatasetProfile,
  ModelOption,
  ModelSelectionResponse,
  TrainingStatus,
  TrainingResults,
} from "@/api/types";
import { usePipeline } from "@/hooks/usePipeline";
import PipelineProgressBar from "@/components/PipelineProgressBar";
import PipelineMilestoneList from "@/components/PipelineMilestoneList";
import type { Milestone } from "@/components/PipelineMilestoneList";
import ModelSelection from "@/components/ModelSelection";
import MetricsDisplay from "@/components/MetricsDisplay";
import ImprovementAgentDisplay from "@/components/ImprovementAgentDisplay";
import IterationDialog, { MetricsDecisionDialog, ImprovementSatisfactionDialog } from "@/components/IterationDialog";
import MultiModelProgress from "@/components/MultiModelProgress";
import type { ModelTrainingState, UserDecision, OptimizationTechnique } from "@/api/iterativeTypes";
import { trainModel, runImprovementAgent, createImprovementIteration, deployModel } from "@/api/iterativeService";

const acceptedFileTypes = ".csv,.xlsx,.xls";

const pipelineHighlights = [
  {
    title: "Data Processing Agent",
    description:
      "Automatically profiles your dataset, cleans missing values, encodes categories, and engineers new features for optimal performance.",
    icon: Workflow
  },
  {
    title: "AI Orchestration Agent",
    description:
      "Selects the most promising ML models, generates tailored training code, and executes it locally to keep your data private.",
    icon: Sparkles
  },
  {
    title: "Improvement Agent",
    description:
      "Tunes hyperparameters, runs cross-validation, and iterates until the best-performing model is ready for deployment.",
    icon: Settings2
  }
];

const assurancePoints = [
  "Your data never leaves your workspace—everything runs locally.",
  "Automated validation ensures data integrity before training begins.",
  "You review every model report before deployment to production.",
  "Each finalized model is stored with metadata and version history."
];

type WorkflowStage = 'upload' | 'model-selection' | 'multi-training' | 'metrics-review' | 'improvement' | 'deployment' | 'results';

const TryNow = () => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [activeDrag, setActiveDrag] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  
  // Workflow state
  const [stage, setStage] = useState<WorkflowStage>('upload');
  const [isUploading, setIsUploading] = useState(false);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [datasetProfile, setDatasetProfile] = useState<DatasetProfile | null>(null);
  
  // Model selection state
  const [models, setModels] = useState<ModelOption[]>([]);
  const [selectedModelIds, setSelectedModelIds] = useState<string[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(false);
  const [modelSelectionReasoning, setModelSelectionReasoning] = useState<string | null>(null);
  
  // Multi-model training state
  const [modelTrainingStates, setModelTrainingStates] = useState<Map<string, ModelTrainingState>>(new Map());
  
  // Iterative workflow state
  const [currentModelId, setCurrentModelId] = useState<string | null>(null);
  const [showMetricsDialog, setShowMetricsDialog] = useState(false);
  const [showImprovementDialog, setShowImprovementDialog] = useState(false);
  const [improvementTechniques, setImprovementTechniques] = useState<OptimizationTechnique[]>([]);
  const [isImproving, setIsImproving] = useState(false);
  
  // Training state (legacy, kept for compatibility)
  const [trainingId, setTrainingId] = useState<string | null>(null);
  const [trainingStatus, setTrainingStatus] = useState<TrainingStatus | null>(null);
  const [isTrainingPolling, setIsTrainingPolling] = useState(false);
  
  // Results state
  const [results, setResults] = useState<TrainingResults | null>(null);
  
  // Pipeline state
  const [pipelineId, setPipelineId] = useState<string | null>(null);
  const { state: pipelineState, startPipeline, resetPipeline } = usePipeline(pipelineId);

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
  };

  const isSupportedFile = (file: File) => {
    const extension = file.name.split(".").pop()?.toLowerCase();
    return extension ? ["csv", "xlsx", "xls"].includes(extension) : false;
  };

  const handleFileSelect = (files: FileList | null) => {
    if (!files || files.length === 0) {
      return;
    }

    const file = files[0];

    if (!isSupportedFile(file)) {
      setSelectedFile(null);
      setUploadError("Unsupported file type. Please upload a CSV or Excel file.");
      return;
    }

    setUploadError(null);
    setSelectedFile(file);
  };

  const triggerFileDialog = () => {
    fileInputRef.current?.click();
  };

  const handleDragEvents = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();

    if (event.type === "dragenter" || event.type === "dragover") {
      setActiveDrag(true);
    } else if (event.type === "dragleave") {
      setActiveDrag(false);
    }
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setActiveDrag(false);

    const files = event.dataTransfer?.files;
    handleFileSelect(files ?? null);
  };

  // Handle dataset upload
  const handleUpload = async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setUploadError(null);

    try {
      const response: DatasetUploadResponse = await api.uploadDataset({
        file: selectedFile,
      });

      setDatasetId(response.datasetId);
      setDatasetProfile(response.profile || null);
      
      // Initialize and start pipeline
      const newPipelineId = `pipeline_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      setPipelineId(newPipelineId);
      
      // Start pipeline after a short delay to show upload milestone completion
      setTimeout(() => {
        startPipeline();
      }, 300);
      
      setStage('model-selection');
      toast.success(response.message || 'Dataset uploaded successfully');

      // Automatically fetch model suggestions
      await loadModelSuggestions(response.datasetId);
    } catch (error: any) {
      const errorMessage = error?.message || 'Failed to upload dataset';
      setUploadError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setIsUploading(false);
    }
  };

  // Load model suggestions
  const loadModelSuggestions = async (id: string) => {
    setIsLoadingModels(true);
    try {
      const response: ModelSelectionResponse = await api.getModelSuggestions(id);
      setModels(response.models);
      setModelSelectionReasoning(response.reasoning);
      // Auto-select recommended model
      setSelectedModelIds([response.recommendedModelId]);
      toast.success('Model suggestions loaded successfully');
    } catch (error: any) {
      toast.error(error?.message || 'Failed to load model suggestions');
    } finally {
      setIsLoadingModels(false);
    }
  };

  // Start multi-model training
  const handleStartMultiModelTraining = async () => {
    if (!datasetId || selectedModelIds.length === 0) {
      toast.error('Please select at least one model');
      return;
    }

    setStage('multi-training');
    
    // Initialize training states for each selected model
    const newStates = new Map<string, ModelTrainingState>();
    selectedModelIds.forEach((modelId) => {
      const model = models.find((m) => m.id === modelId);
      if (model) {
        newStates.set(modelId, {
          modelId,
          modelName: model.name,
          status: 'pending',
          progress: 0,
          improvementIterations: 0,
          improvementHistory: [],
        });
      }
    });
    
    setModelTrainingStates(newStates);
    
    // Start training for each model in parallel
    selectedModelIds.forEach((modelId) => {
      trainModelForModel(modelId);
    });
  };

  // Train a single model
  const trainModelForModel = async (modelId: string) => {
    const model = models.find((m) => m.id === modelId);
    if (!model) return;

    // Update status to training
    setModelTrainingStates((prev) => {
      const updated = new Map(prev);
      const state = updated.get(modelId);
      if (state) {
        updated.set(modelId, { ...state, status: 'training', progress: 0 });
      }
      return updated;
    });

    try {
      const metrics = await trainModel(modelId, model.name, (progress) => {
        setModelTrainingStates((prev) => {
          const updated = new Map(prev);
          const state = updated.get(modelId);
          if (state) {
            updated.set(modelId, { ...state, progress });
          }
          return updated;
        });
      });

      // Update with completed metrics
      setModelTrainingStates((prev) => {
        const updated = new Map(prev);
        const state = updated.get(modelId);
        if (state) {
          updated.set(modelId, {
            ...state,
            status: 'completed',
            progress: 100,
            metrics,
            executionTime: metrics.executionTime,
          });
        }
        return updated;
      });

      // Check if all models are done - check latest state
      setTimeout(() => {
        setModelTrainingStates((currentStates) => {
          const allStates = Array.from(currentStates.values());
          const allCompleted = allStates.every(
            (s) => s.status === 'completed' || s.status === 'failed'
          );
          
          if (allCompleted && allStates.length > 0) {
            // Show metrics for the first completed model
            const firstCompleted = allStates.find((s) => s.status === 'completed');
            if (firstCompleted) {
              setTimeout(() => {
                setStage('metrics-review');
                setCurrentModelId(firstCompleted.modelId);
                setShowMetricsDialog(true);
              }, 500);
            }
          }
          return currentStates;
        });
      }, 500);
    } catch (error: any) {
      setModelTrainingStates((prev) => {
        const updated = new Map(prev);
        const state = updated.get(modelId);
        if (state) {
          updated.set(modelId, { ...state, status: 'failed' });
        }
        return updated;
      });
      toast.error(`Failed to train ${model.name}`);
    }
  };

  // Handle metrics decision
  const handleMetricsDecision = async (decision: UserDecision) => {
    setShowMetricsDialog(false);
    
    if (decision.type === 'proceed_to_deployment') {
      if (!currentModelId) return;
      await handleDeployment(currentModelId);
    } else if (decision.type === 'send_to_improvement') {
      if (!currentModelId) return;
      await handleStartImprovement(currentModelId);
    }
  };

  // Handle cancel confirmation
  const handleConfirmCancel = () => {
    setShowMetricsDialog(false);
    handleReset();
    toast.info('Workflow cancelled. All progress has been reset.');
  };

  // Start improvement agent
  const handleStartImprovement = async (modelId: string) => {
    const state = modelTrainingStates.get(modelId);
    if (!state || !state.metrics) return;

    setIsImproving(true);
    setStage('improvement');
    setCurrentModelId(modelId);

    try {
      const beforeMetrics = state.metrics;
      
      const { techniques, improvedMetrics, improvements } = await runImprovementAgent(
        beforeMetrics,
        (technique) => {
          setImprovementTechniques((prev) => {
            const existing = prev.find((t) => t.name === technique.name);
            if (existing) {
              return prev.map((t) =>
                t.name === technique.name ? technique : t
              );
            }
            return [...prev, technique];
          });
        }
      );

      // Update model state with improvement
      setModelTrainingStates((prev) => {
        const updated = new Map(prev);
        const currentState = updated.get(modelId);
        if (currentState) {
          const iteration = createImprovementIteration(
            currentState.improvementIterations + 1,
            beforeMetrics,
            improvedMetrics,
            techniques
          );

          updated.set(modelId, {
            ...currentState,
            metrics: improvedMetrics,
            improvementIterations: currentState.improvementIterations + 1,
            improvementHistory: [...currentState.improvementHistory, iteration],
          });
        }
        return updated;
      });

      setImprovementTechniques(techniques);
      setIsImproving(false);
      setShowImprovementDialog(true);
    } catch (error: any) {
      toast.error('Failed to run improvement agent');
      setIsImproving(false);
    }
  };

  // Handle improvement satisfaction decision
  const handleImprovementDecision = async (decision: UserDecision) => {
    setShowImprovementDialog(false);
    
    const state = currentModelId ? modelTrainingStates.get(currentModelId) : null;
    if (!state) return;

    if (decision.type === 'proceed_to_deployment') {
      await handleDeployment(currentModelId!);
    } else if (decision.type === 'send_to_improvement') {
      if (state.improvementIterations >= 3) {
        toast.error('Maximum improvement iterations reached');
        return;
      }
      await handleStartImprovement(currentModelId!);
    } else if (decision.type === 'reject_and_reselect') {
      setStage('model-selection');
      toast.info('Returning to model selection');
    }
  };

  // Handle deployment
  const handleDeployment = async (modelId: string) => {
    setStage('deployment');
    toast.info('Starting deployment...');

    try {
      const result = await deployModel(modelId);
      setStage('results');
      toast.success(result.message);
    } catch (error: any) {
      toast.error('Deployment failed');
    }
  };

  // Legacy single model training handler (for backward compatibility)
  const handleStartTraining = async () => {
    if (selectedModelIds.length > 0) {
      await handleStartMultiModelTraining();
    }
  };

  // Poll training status
  useEffect(() => {
    if (!isTrainingPolling || !trainingId) return;

    // Initial fetch
    const fetchStatus = async () => {
      try {
        const status = await api.getTrainingStatus(trainingId);
        setTrainingStatus(status);

        if (status.status === 'completed') {
          setIsTrainingPolling(false);
          await loadResults(trainingId);
        } else if (status.status === 'failed' || status.status === 'stopped') {
          setIsTrainingPolling(false);
          toast.error(status.message || 'Training stopped or failed');
        }
      } catch (error: any) {
        console.error('Error fetching training status:', error);
      }
    };

    fetchStatus();

    // Poll every 2 seconds
    const pollInterval = setInterval(async () => {
      try {
        const status = await api.getTrainingStatus(trainingId);
        setTrainingStatus(status);

        if (status.status === 'completed') {
          clearInterval(pollInterval);
          setIsTrainingPolling(false);
          await loadResults(trainingId);
        } else if (status.status === 'failed' || status.status === 'stopped') {
          clearInterval(pollInterval);
          setIsTrainingPolling(false);
          toast.error(status.message || 'Training stopped or failed');
        }
      } catch (error: any) {
        console.error('Error polling training status:', error);
        // Don't clear interval on error, keep trying
      }
    }, 2000);

    return () => clearInterval(pollInterval);
  }, [isTrainingPolling, trainingId]);

  // Stop training
  const handleStopTraining = async () => {
    if (!trainingId) return;

    try {
      await api.stopTraining(trainingId);
      setIsTrainingPolling(false);
      toast.success('Training stopped successfully');
    } catch (error: any) {
      toast.error(error?.message || 'Failed to stop training');
    }
  };

  // Load training results
  const loadResults = async (id: string) => {
    try {
      const resultsData = await api.getResults(id);
      setResults(resultsData);
      setStage('results');
      toast.success('Training completed successfully!');
    } catch (error: any) {
      // Results might not be ready yet
      console.error('Error loading results:', error);
    }
  };

  // Reset workflow
  const handleReset = () => {
    setStage('upload');
    setSelectedFile(null);
    setDatasetId(null);
    setDatasetProfile(null);
    setModels([]);
    setSelectedModelIds([]);
    setModelTrainingStates(new Map());
    setCurrentModelId(null);
    setShowMetricsDialog(false);
    setShowImprovementDialog(false);
    setImprovementTechniques([]);
    setIsImproving(false);
    setTrainingId(null);
    setTrainingStatus(null);
    setResults(null);
    setUploadError(null);
    setIsTrainingPolling(false);
    resetPipeline();
    setPipelineId(null);
  };
  
  // Convert pipeline milestones to component format
  const pipelineMilestones: Milestone[] = pipelineState?.milestones.map((m) => ({
    id: m.id,
    title: m.title,
    description: m.description,
    status: m.status,
  })) || [];

  // Format time
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Navbar />
      <main className="flex-1">
        <section className="relative overflow-hidden bg-gradient-to-b from-white via-white/90 to-slate-100 pt-32 pb-24">
          <div className="pointer-events-none absolute inset-0 -z-10">
            <img
              src="/background-section2.png"
              alt=""
              className="absolute right-0 top-0 hidden h-full w-auto opacity-50 lg:block"
              loading="lazy"
            />
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,#fde5c7,transparent_55%)] opacity-80" />
          </div>

          <div className="container relative z-10 px-4 sm:px-6 lg:px-8">
            {/* Upload Stage */}
            {stage === 'upload' && (
              <div className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-center">
                <div className="space-y-8 text-center lg:text-left">
                  <span className="inline-flex items-center rounded-full bg-pulse-100 px-4 py-1 text-sm font-medium text-pulse-600 shadow-sm">
                    Upload your data · Launch intelligent models
                  </span>
                  <h1 className="text-4xl font-bold tracking-tight text-gray-900 md:text-5xl">
                    Transform datasets into production-ready intelligence
                  </h1>
                  <p className="mx-auto max-w-xl text-lg text-gray-600 lg:mx-0">
                    IntelliModel orchestrates your entire machine learning lifecycle.
                    Upload a CSV or Excel file and let our agents profile, train, and
                    deploy the best model while keeping you in full control.
                  </p>
                  <div className="grid gap-4 rounded-2xl border border-white/80 bg-white/80 p-6 shadow-elegant backdrop-blur">
                  <div
                    className={cn(
                      "relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-10 transition-all duration-300",
                      activeDrag
                        ? "border-pulse-500 bg-pulse-50 shadow-lg"
                        : "border-slate-200 bg-white shadow-sm hover:border-pulse-300 hover:shadow-md"
                    )}
                    onDragEnter={handleDragEvents}
                    onDragOver={handleDragEvents}
                    onDragLeave={handleDragEvents}
                    onDrop={handleDrop}
                  >
                    <UploadCloud className="mb-4 h-12 w-12 text-pulse-500" />
                    <p className="text-lg font-semibold text-gray-900">
                      Drag & drop your dataset here
                    </p>
                    <p className="mt-2 text-sm text-gray-500">
                      or
                      <button
                        type="button"
                        className="ml-2 font-medium text-pulse-600 hover:text-pulse-500 focus:outline-none"
                        onClick={triggerFileDialog}
                      >
                        browse files
                      </button>
                    </p>
                    <p className="mt-4 text-xs uppercase tracking-[0.2em] text-gray-400">
                      Supported formats: CSV, XLSX
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept={acceptedFileTypes}
                      className="hidden"
                      onChange={(event) => handleFileSelect(event.target.files)}
                    />
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm">
                      <div className="flex items-center gap-3">
                        <ShieldCheck className="h-6 w-6 text-green-500" />
                        <div>
                          <p className="text-sm font-semibold text-gray-900">
                            Private by design
                          </p>
                          <p className="text-xs text-gray-500">
                            Processing runs on your machine — never in the cloud.
                          </p>
                        </div>
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm">
                      <div className="flex items-center gap-3">
                        <LineChart className="h-6 w-6 text-pulse-500" />
                        <div>
                          <p className="text-sm font-semibold text-gray-900">
                            Deployable APIs in minutes
                          </p>
                          <p className="text-xs text-gray-500">
                            Best model is packaged with full metadata & endpoints.
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                  {uploadError && (
                    <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-left text-sm text-red-600">
                      {uploadError}
                    </div>
                  )}
                  {selectedFile && !uploadError && (
                    <div className="rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm">
                      <div className="flex flex-wrap items-center justify-between gap-4">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">
                            {selectedFile.name}
                          </p>
                          <p className="text-xs text-gray-500">
                            {formatFileSize(selectedFile.size)} · Ready for validation
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={handleUpload}
                          disabled={isUploading}
                          className="inline-flex items-center rounded-full bg-pulse-500 px-5 py-2 text-sm font-medium text-white shadow-md transition-all duration-200 hover:bg-pulse-600 focus:outline-none focus:ring-2 focus:ring-pulse-300 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {isUploading ? (
                            <>
                              <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                              Uploading...
                            </>
                          ) : (
                            'Process dataset'
                          )}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="relative mx-auto w-full max-w-md">
                <div className="absolute -top-16 -right-10 hidden h-56 w-56 rounded-full bg-orange-200/40 blur-3xl lg:block" />
                <div className="glass-card relative overflow-hidden rounded-3xl border border-white/20 bg-white/80 p-6 shadow-elegant">
                  <div className="absolute -right-24 -top-24 h-48 w-48 rounded-full bg-pulse-200/50 blur-3xl" />
                  <img
                    src="/hero-image.jpg"
                    alt="Workflow preview"
                    className="relative z-10 rounded-2xl object-cover shadow-lg"
                  />
                  <div className="relative z-10 mt-6 space-y-4">
                    <div className="flex items-center gap-3 rounded-2xl bg-white/90 p-4 shadow-inner">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-pulse-100 text-pulse-600">
                        <RefreshCw className="h-5 w-5" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">
                          Continuous retraining
                        </p>
                        <p className="text-xs text-gray-500">
                          Monitor drift, auto-trigger improvement agent, and deploy updates safely.
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 rounded-2xl bg-white/90 p-4 shadow-inner">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                        <ShieldCheck className="h-5 w-5" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">
                          Audit-ready reports
                        </p>
                        <p className="text-xs text-gray-500">
                          Every experiment logged with metrics, lineage, and governance checks.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            )}

            {/* Model Selection Stage */}
            {stage === 'model-selection' && (
              <div className="mx-auto max-w-5xl space-y-8">
                <div className="text-center">
                  <span className="inline-flex items-center rounded-full bg-pulse-100 px-4 py-1 text-sm font-medium text-pulse-600 shadow-sm">
                    Step 2 of 4 · Model Selection
                  </span>
                  <h1 className="mt-4 text-4xl font-bold tracking-tight text-gray-900 md:text-5xl">
                    Choose Your Model
                  </h1>
                  <p className="mx-auto mt-4 max-w-2xl text-lg text-gray-600">
                    Based on your dataset analysis, here are the recommended models
                  </p>
                </div>

                {modelSelectionReasoning && (
                  <Card className="border-pulse-200 bg-pulse-50/50">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Sparkles className="h-5 w-5 text-pulse-600" />
                        AI Recommendation
                      </CardTitle>
                      <CardDescription>{modelSelectionReasoning}</CardDescription>
                    </CardHeader>
                  </Card>
                )}

                {isLoadingModels ? (
                  <div className="flex items-center justify-center py-12">
                    <RefreshCw className="h-8 w-8 animate-spin text-pulse-500" />
                    <span className="ml-3 text-gray-600">Analyzing dataset and generating model suggestions...</span>
                  </div>
                ) : (
                  <ModelSelection
                    models={models}
                    selectedModelIds={selectedModelIds}
                    onSelectionChange={setSelectedModelIds}
                    recommendedModelId={models.find(m => m.recommended)?.id}
                    reasoning={modelSelectionReasoning || undefined}
                  />
                )}

                {!isLoadingModels && models.length > 0 && (
                  <div className="flex justify-center gap-4">
                    <Button
                      variant="outline"
                      onClick={handleReset}
                      className="rounded-full"
                    >
                      Start Over
                    </Button>
                    <Button
                      onClick={handleStartMultiModelTraining}
                      disabled={selectedModelIds.length === 0}
                      className="rounded-full bg-pulse-500 hover:bg-pulse-600"
                    >
                      <Play className="mr-2 h-4 w-4" />
                      Start Training {selectedModelIds.length > 1 ? `(${selectedModelIds.length} models)` : ''}
                    </Button>
                  </div>
                )}
              </div>
            )}

            {/* Multi-Model Training Stage */}
            {stage === 'multi-training' && (
              <div className="mx-auto max-w-5xl space-y-8">
                <div className="text-center">
                  <span className="inline-flex items-center rounded-full bg-pulse-100 px-4 py-1 text-sm font-medium text-pulse-600 shadow-sm">
                    Training Multiple Models
                  </span>
                  <h1 className="mt-4 text-4xl font-bold tracking-tight text-gray-900 md:text-5xl">
                    Training in Progress
                  </h1>
                  <p className="mx-auto mt-4 max-w-xl text-lg text-gray-600">
                    Training {Array.from(modelTrainingStates.values()).length} model(s) in parallel
                  </p>
                </div>

                <MultiModelProgress models={Array.from(modelTrainingStates.values())} />
              </div>
            )}

            {/* Metrics Review Stage */}
            {stage === 'metrics-review' && currentModelId && (
              <div className="mx-auto max-w-5xl space-y-8">
                <div className="text-center">
                  <span className="inline-flex items-center rounded-full bg-emerald-100 px-4 py-1 text-sm font-medium text-emerald-600 shadow-sm">
                    Training Complete
                  </span>
                  <h1 className="mt-4 text-4xl font-bold tracking-tight text-gray-900 md:text-5xl">
                    Model Performance Metrics
                  </h1>
                  <p className="mx-auto mt-4 max-w-xl text-lg text-gray-600">
                    Review the training results for your model
                  </p>
                </div>

                {(() => {
                  const modelState = modelTrainingStates.get(currentModelId);
                  if (!modelState || !modelState.metrics) return null;

                  const lastImprovement = modelState.improvementHistory[modelState.improvementHistory.length - 1];
                  const showComparison = !!lastImprovement;

                  return (
                    <MetricsDisplay
                      metrics={modelState.metrics}
                      beforeMetrics={lastImprovement?.beforeMetrics}
                      title={`${modelState.modelName} - Performance Metrics`}
                      showComparison={showComparison}
                    />
                  );
                })()}
              </div>
            )}

            {/* Improvement Stage */}
            {stage === 'improvement' && currentModelId && (
              <div className="mx-auto max-w-5xl space-y-8">
                <div className="text-center">
                  <span className="inline-flex items-center rounded-full bg-pulse-100 px-4 py-1 text-sm font-medium text-pulse-600 shadow-sm">
                    Improvement Agent Active
                  </span>
                  <h1 className="mt-4 text-4xl font-bold tracking-tight text-gray-900 md:text-5xl">
                    Optimizing Model Performance
                  </h1>
                  <p className="mx-auto mt-4 max-w-xl text-lg text-gray-600">
                    The improvement agent is applying optimization techniques
                  </p>
                </div>

                {improvementTechniques.length > 0 && (
                  <ImprovementAgentDisplay
                    techniques={improvementTechniques}
                    onComplete={() => {
                      setIsImproving(false);
                    }}
                  />
                )}
              </div>
            )}

            {/* Training Stage */}
            {stage === 'training' && trainingStatus && (
              <div className="mx-auto max-w-3xl space-y-8">
                <div className="text-center">
                  <span className="inline-flex items-center rounded-full bg-pulse-100 px-4 py-1 text-sm font-medium text-pulse-600 shadow-sm">
                    Step 3 of 4 · Training in Progress
                  </span>
                  <h1 className="mt-4 text-4xl font-bold tracking-tight text-gray-900 md:text-5xl">
                    Training Your Model
                  </h1>
                  <p className="mx-auto mt-4 max-w-xl text-lg text-gray-600">
                    Our agents are working to create the best model for your data
                  </p>
                </div>

                <Card className="border-pulse-200">
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle>Training Progress</CardTitle>
                      <span className="text-sm font-medium text-gray-600">
                        {trainingStatus.progress}%
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <Progress value={trainingStatus.progress} className="h-3" />
                    
                    <div className="space-y-2">
                      <p className="text-sm font-semibold text-gray-900">
                        {trainingStatus.currentStep || 'Processing...'}
                      </p>
                      
                      {trainingStatus.elapsedTime !== undefined && (
                        <div className="flex gap-6 text-sm text-gray-600">
                          <span>Elapsed: {formatTime(trainingStatus.elapsedTime)}</span>
                          {trainingStatus.estimatedTimeRemaining !== undefined && trainingStatus.estimatedTimeRemaining > 0 && (
                            <span>Remaining: ~{formatTime(trainingStatus.estimatedTimeRemaining)}</span>
                          )}
                        </div>
                      )}
                    </div>

                    {trainingStatus.status === 'running' && (
                      <div className="flex justify-center">
                        <Button
                          variant="outline"
                          onClick={handleStopTraining}
                          className="rounded-full"
                        >
                          <Square className="mr-2 h-4 w-4" />
                          Stop Training
                        </Button>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            )}

            {/* Results Stage */}
            {stage === 'results' && results && (
              <div className="mx-auto max-w-4xl space-y-8">
                <div className="text-center">
                  <span className="inline-flex items-center rounded-full bg-emerald-100 px-4 py-1 text-sm font-medium text-emerald-600 shadow-sm">
                    Step 4 of 4 · Training Complete
                  </span>
                  <h1 className="mt-4 text-4xl font-bold tracking-tight text-gray-900 md:text-5xl">
                    Training Results
                  </h1>
                  <p className="mx-auto mt-4 max-w-xl text-lg text-gray-600">
                    Your model has been trained successfully
                  </p>
                </div>

                <div className="grid gap-6 md:grid-cols-2">
                  <Card>
                    <CardHeader>
                      <CardTitle>Performance Metrics</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {results.metrics.accuracy !== undefined && (
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-gray-600">Accuracy</span>
                          <span className="text-lg font-bold text-gray-900">
                            {(results.metrics.accuracy * 100).toFixed(2)}%
                          </span>
                        </div>
                      )}
                      {results.metrics.precision !== undefined && (
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-gray-600">Precision</span>
                          <span className="text-lg font-bold text-gray-900">
                            {(results.metrics.precision * 100).toFixed(2)}%
                          </span>
                        </div>
                      )}
                      {results.metrics.recall !== undefined && (
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-gray-600">Recall</span>
                          <span className="text-lg font-bold text-gray-900">
                            {(results.metrics.recall * 100).toFixed(2)}%
                          </span>
                        </div>
                      )}
                      {results.metrics.f1Score !== undefined && (
                        <div className="flex items-center justify-between">
                          <span className="text-sm text-gray-600">F1 Score</span>
                          <span className="text-lg font-bold text-gray-900">
                            {(results.metrics.f1Score * 100).toFixed(2)}%
                          </span>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle>Training Details</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">Duration</span>
                        <span className="text-lg font-bold text-gray-900">
                          {formatTime(results.trainingDuration)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">Model ID</span>
                        <span className="text-sm font-mono text-gray-900">
                          {results.modelId}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">Status</span>
                        <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-medium text-emerald-700">
                          Completed
                        </span>
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {results.modelSummary && (
                  <Card>
                    <CardHeader>
                      <CardTitle>Model Summary</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-gray-700">{results.modelSummary}</p>
                    </CardContent>
                  </Card>
                )}

                {results.metrics.featureImportance && results.metrics.featureImportance.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle>Feature Importance</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        {results.metrics.featureImportance.map((feature, idx) => (
                          <div key={idx} className="space-y-1">
                            <div className="flex items-center justify-between text-sm">
                              <span className="font-medium text-gray-900">{feature.feature}</span>
                              <span className="text-gray-600">{(feature.importance * 100).toFixed(1)}%</span>
                            </div>
                            <Progress value={feature.importance * 100} className="h-2" />
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                <div className="flex justify-center gap-4">
                  {results.downloadUrl && (
                    <Button variant="outline" className="rounded-full">
                      <Download className="mr-2 h-4 w-4" />
                      Download Model
                    </Button>
                  )}
                  {results.apiEndpoint && (
                    <Button variant="outline" className="rounded-full">
                      <ExternalLink className="mr-2 h-4 w-4" />
                      View API Endpoint
                    </Button>
                  )}
                  <Button
                    onClick={handleReset}
                    className="rounded-full bg-pulse-500 hover:bg-pulse-600"
                  >
                    Train Another Model
                  </Button>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Pipeline Progress Section - Persistent across all stages */}
        {pipelineId && pipelineState && stage !== 'upload' && (
          <section className="relative py-12 bg-gradient-to-b from-slate-50 to-white">
            <div className="container px-4 sm:px-6 lg:px-8">
              <div className="mx-auto max-w-4xl">
                <Card className="border-pulse-200 bg-white shadow-lg">
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Workflow className="h-5 w-5 text-pulse-600" />
                      Pipeline Execution Progress
                    </CardTitle>
                    <CardDescription>
                      Real-time progress of your ML pipeline execution
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    <PipelineProgressBar
                      progress={pipelineState.overallProgress}
                    />
                    <div className="border-t pt-4">
                      <h3 className="text-sm font-semibold text-gray-900 mb-4">
                        Milestones
                      </h3>
                      <PipelineMilestoneList milestones={pipelineMilestones} />
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          </section>
        )}

        <section className="relative py-24">
          <div className="absolute inset-0 -z-10 bg-gradient-to-b from-white via-slate-50 to-white" />
          <div className="container px-4 sm:px-6 lg:px-8">
            <div className="mx-auto max-w-3xl text-center">
              <h2 className="section-title">Three agents working in harmony</h2>
              <p className="section-subtitle">
                IntelliModel choreographs specialized agents to transform raw datasets
                into deployable intelligence. Sit back while each step is handled with
                transparency and human oversight.
              </p>
            </div>
            <div className="mt-16 grid gap-8 lg:grid-cols-3">
              {pipelineHighlights.map(({ title, description, icon: Icon }) => (
                <div
                  key={title}
                  className="feature-card glass-card h-full p-8 text-left"
                >
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-pulse-100 text-pulse-600">
                    <Icon className="h-6 w-6" />
                  </div>
                  <h3 className="mt-6 text-xl font-semibold text-gray-900">
                    {title}
                  </h3>
                  <p className="mt-4 text-sm text-gray-600">
                    {description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="relative overflow-hidden py-24">
          <div className="absolute inset-0 -z-10">
            <img
              src="/background-section3.png"
              alt=""
              className="h-full w-full object-cover opacity-60"
              loading="lazy"
            />
            <div className="absolute inset-0 bg-gradient-to-r from-white via-white/90 to-white/70" />
          </div>
          <div className="container relative z-10 px-4 sm:px-6 lg:px-8">
            <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
              <div className="space-y-6">
                <h2 className="section-title">
                  What happens after you upload your dataset?
                </h2>
                <div className="space-y-4">
                  <div className="rounded-2xl border border-white/70 bg-white/80 p-6 shadow-elegant">
                    <h3 className="text-lg font-semibold text-gray-900">
                      Step-by-step orchestration
                    </h3>
                    <ul className="mt-4 space-y-3 text-sm text-gray-600">
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-emerald-500" />
                        Dataset validation, schema detection, and intelligent profile summary.
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-emerald-500" />
                        Automated model selection with cross-validation and explainability reports.
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-emerald-500" />
                        Human approval gate before retraining the winning model for production.
                      </li>
                    </ul>
                  </div>
                  <div className="rounded-2xl border border-white/70 bg-white/80 p-6 shadow-elegant">
                    <h3 className="text-lg font-semibold text-gray-900">
                      Governance & deployment
                    </h3>
                    <p className="mt-4 text-sm text-gray-600">
                      Once approved, IntelliModel retrains with your latest dataset, packages
                      the model with metadata, and exposes a secure REST API ready to plug into
                      BI dashboards like Power BI or Tableau. Continuous monitoring ensures your
                      models stay performant.
                    </p>
                  </div>
                </div>
              </div>
              <div className="glass-card relative rounded-3xl border border-white/20 bg-white/80 p-8 shadow-elegant">
                <h3 className="text-lg font-semibold text-gray-900">
                  Built-in safeguards you can trust
                </h3>
                <ul className="mt-6 space-y-4 text-sm text-gray-600">
                  {assurancePoints.map((point) => (
                    <li key={point} className="flex items-start gap-3">
                      <ShieldCheck className="mt-0.5 h-5 w-5 flex-shrink-0 text-pulse-500" />
                      {point}
                    </li>
                  ))}
                </ul>
                <div className="mt-8 flex flex-col gap-4 rounded-2xl bg-white/90 p-6 shadow-inner">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-pulse-100 text-pulse-600">
                      <LineChart className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-900">
                        Monitoring made effortless
                      </p>
                      <p className="text-xs text-gray-500">
                        Drift detection and alerting keep your stakeholders informed in real time.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                      <RefreshCw className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-900">
                        Continuous improvement loop
                      </p>
                      <p className="text-xs text-gray-500">
                        Automated retraining ensures your deployed models stay accurate and reliable.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {/* Decision Dialogs */}
      {currentModelId && modelTrainingStates.get(currentModelId)?.metrics && (
        <MetricsDecisionDialog
          open={showMetricsDialog}
          metrics={modelTrainingStates.get(currentModelId)!.metrics!}
          onSelect={handleMetricsDecision}
          onCancel={() => setShowMetricsDialog(false)}
          onConfirmCancel={handleConfirmCancel}
          iterationCount={modelTrainingStates.get(currentModelId)?.improvementIterations || 0}
        />
      )}

      {currentModelId && modelTrainingStates.get(currentModelId) && (
        <ImprovementSatisfactionDialog
          open={showImprovementDialog}
          onSelect={handleImprovementDecision}
          onCancel={() => setShowImprovementDialog(false)}
          iterationCount={modelTrainingStates.get(currentModelId)?.improvementIterations || 0}
        />
      )}

      <Footer />
    </div>
  );
};

export default TryNow;

