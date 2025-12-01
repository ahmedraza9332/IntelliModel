/**
 * Types for iterative ML workflow
 */

export interface ModelTrainingState {
  modelId: string;
  modelName: string;
  status: 'pending' | 'training' | 'completed' | 'failed';
  progress: number;
  metrics?: ModelMetrics;
  improvementIterations: number; // 0-3
  improvementHistory: ImprovementIteration[];
  executionTime?: number;
}

export interface ModelMetrics {
  accuracy: number;
  precision: number;
  recall: number;
  f1Score: number;
  confusionMatrix: number[][];
  executionTime: number; // in seconds
  metadata?: Record<string, any>;
}

export interface ImprovementIteration {
  iterationNumber: number;
  techniques: OptimizationTechnique[];
  beforeMetrics: ModelMetrics;
  afterMetrics: ModelMetrics;
  improvements: MetricImprovement[];
}

export interface OptimizationTechnique {
  name: string;
  description: string;
  status: 'pending' | 'running' | 'completed';
}

export interface MetricImprovement {
  metric: string;
  before: number;
  after: number;
  change: number; // percentage change
  improved: boolean;
}

export interface UserDecision {
  type: 'proceed_to_deployment' | 'send_to_improvement' | 'reject_and_reselect';
  modelId?: string;
}

export const OPTIMIZATION_TECHNIQUES = [
  { name: 'Hyperparameter Tuning', description: 'Optimizing learning rate, batch size, and regularization parameters' },
  { name: 'Dropout Tuning', description: 'Adjusting dropout rates to prevent overfitting' },
  { name: 'Regularization', description: 'Applying L1/L2 regularization techniques' },
  { name: 'Early Stopping', description: 'Implementing early stopping to prevent overfitting' },
  { name: 'Learning Rate Scheduling', description: 'Adaptive learning rate optimization' },
  { name: 'Feature Engineering', description: 'Creating and selecting optimal features' },
  { name: 'Cross-Validation', description: 'K-fold cross-validation for robust evaluation' },
] as const;

