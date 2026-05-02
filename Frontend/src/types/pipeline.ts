export type PipelineStep =
  | "upload"
  | "preprocessing"
  | "model_selection"
  | "validation"
  | "improvement"
  | "training"
  | "deployment";
