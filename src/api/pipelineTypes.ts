/**
 * Types for pipeline execution and milestones
 */

export type PipelineStageStatus = "pending" | "running" | "completed" | "failed";

export interface PipelineMilestone {
  id: string;
  title: string;
  description?: string;
  status: PipelineStageStatus;
  startedAt?: string;
  completedAt?: string;
  error?: string;
}

export type PipelineFlowState = 
  | "UPLOAD" 
  | "PREPROCESS" 
  | "RECOMMENDATION_WAIT"
  | "TRAINING" 
  | "METRICS_WAIT"
  | "IMPROVEMENT" 
  | "IMPROVEMENT_WAIT"
  | "DEPLOYMENT";

export interface PipelineState {
  pipelineId: string;
  milestones: PipelineMilestone[];
  overallProgress: number; // 0-100
  currentStage: string | null;
  status: "idle" | "running" | "completed" | "failed" | "waiting";
  flowState: PipelineFlowState | null;
  startedAt?: string;
  completedAt?: string;
  waitingForUser: boolean;
}

export interface PipelineEvent {
  type: "milestone_started" | "milestone_completed" | "milestone_failed" | "pipeline_started" | "pipeline_completed" | "pipeline_failed" | "pipeline_waiting" | "pipeline_resumed";
  milestoneId?: string;
  timestamp: string;
  data?: any;
}

export const PIPELINE_MILESTONES = [
  {
    id: "dataset_uploaded",
    title: "Dataset Uploaded",
    description: "Dataset file validated and received",
  },
  {
    id: "schema_profiling",
    title: "Schema Profiling",
    description: "Preprocessing Agent analyzing schema and data structure",
  },
  {
    id: "preprocessing_complete",
    title: "Preprocessing Complete",
    description: "Data cleaned, validated, and preprocessed",
  },
  {
    id: "model_suggestions_ready",
    title: "Model Suggestions Ready",
    description: "LLM Orchestration ranked model recommendations",
  },
  {
    id: "code_generation",
    title: "Code Generation",
    description: "LLM generating executable validation & training code",
  },
  {
    id: "training_in_progress",
    title: "Training in Progress",
    description: "Local Executor running experiments",
  },
  {
    id: "metrics_returned",
    title: "Metrics Returned",
    description: "Training metrics and validation results received",
  },
  {
    id: "improvement_iteration",
    title: "Improvement Iteration",
    description: "Improvement Agent optimizing model performance",
  },
  {
    id: "final_model_trained",
    title: "Final Model Trained",
    description: "Model trained on full dataset",
  },
  {
    id: "model_deployed",
    title: "Model Deployed",
    description: "Deployment Service deployed endpoint",
  },
] as const;

