/**
 * TypeScript types for API requests and responses
 */

export interface DatasetUploadRequest {
  file: File;
}

export interface DatasetUploadResponse {
  success: boolean;
  datasetId: string;
  message: string;
  profile?: DatasetProfile;
}

export interface DatasetProfile {
  rowCount: number;
  columnCount: number;
  columns: ColumnInfo[];
  dataTypes: Record<string, string>;
  missingValues: Record<string, number>;
  summary: string;
}

export interface ColumnInfo {
  name: string;
  type: string;
  nullable: boolean;
  sampleValues: any[];
}

export interface ModelOption {
  id: string;
  name: string;
  type: 'classification' | 'regression';
  description: string;
  estimatedAccuracy?: number;
  pros: string[];
  cons: string[];
  recommended: boolean;
}

export interface ModelSelectionResponse {
  success: boolean;
  models: ModelOption[];
  recommendedModelId: string;
  reasoning: string;
}

export interface TrainingStartRequest {
  datasetId: string;
  modelId: string;
  parameters?: Record<string, any>;
}

export interface TrainingStartResponse {
  success: boolean;
  trainingId: string;
  message: string;
}

export interface TrainingStatus {
  trainingId: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'stopped';
  progress: number; // 0-100
  currentStep?: string;
  elapsedTime?: number; // in seconds
  estimatedTimeRemaining?: number; // in seconds
  message?: string;
}

export interface TrainingStopResponse {
  success: boolean;
  message: string;
}

export interface ModelMetrics {
  accuracy?: number;
  precision?: number;
  recall?: number;
  f1Score?: number;
  mse?: number;
  mae?: number;
  r2Score?: number;
  confusionMatrix?: number[][];
  featureImportance?: Array<{ feature: string; importance: number }>;
}

export interface TrainingResults {
  trainingId: string;
  modelId: string;
  status: 'completed' | 'failed';
  metrics: ModelMetrics;
  modelSummary: string;
  trainingDuration: number; // in seconds
  trainingDate: string;
  downloadUrl?: string;
  apiEndpoint?: string;
}

export interface ApiError {
  message: string;
  code?: string;
  details?: any;
}

