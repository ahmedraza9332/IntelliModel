/**
 * Mock API implementations
 * Simulates backend responses for testing UI without a real backend
 */

import {
  DatasetUploadRequest,
  DatasetUploadResponse,
  ModelSelectionResponse,
  TrainingStartRequest,
  TrainingStartResponse,
  TrainingStatus,
  TrainingStopResponse,
  TrainingResults,
  ApiError,
} from './types';

// Simulate network delay
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

// Storage for mock data (simulates backend state)
const mockStorage = {
  datasets: new Map<string, any>(),
  trainings: new Map<string, TrainingStatus>(),
  results: new Map<string, TrainingResults>(),
};

/**
 * Mock dataset upload
 */
export const mockUploadDataset = async (
  request: DatasetUploadRequest
): Promise<DatasetUploadResponse> => {
  await delay(1500); // Simulate upload time

  // Validate file
  const fileExtension = request.file.name.split('.').pop()?.toLowerCase();
  if (!fileExtension || !['csv', 'xlsx', 'xls'].includes(fileExtension)) {
    throw {
      message: 'Unsupported file type. Please upload a CSV or Excel file.',
      code: 'INVALID_FILE_TYPE',
    } as ApiError;
  }

  // Generate mock dataset ID
  const datasetId = `dataset_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  // Mock profile data
  const mockProfile = {
    rowCount: Math.floor(Math.random() * 9000) + 1000,
    columnCount: Math.floor(Math.random() * 15) + 5,
    columns: [
      { name: 'feature1', type: 'numeric', nullable: false, sampleValues: [1.2, 3.4, 5.6] },
      { name: 'feature2', type: 'categorical', nullable: true, sampleValues: ['A', 'B', 'C'] },
      { name: 'target', type: 'numeric', nullable: false, sampleValues: [0, 1, 0] },
    ],
    dataTypes: {
      feature1: 'float64',
      feature2: 'object',
      target: 'int64',
    },
    missingValues: {
      feature2: 5,
    },
    summary: `Dataset contains ${Math.floor(Math.random() * 9000) + 1000} rows with ${Math.floor(Math.random() * 15) + 5} columns. Data appears to be suitable for machine learning.`,
  };

  // Store dataset info
  mockStorage.datasets.set(datasetId, {
    id: datasetId,
    fileName: request.file.name,
    fileSize: request.file.size,
    profile: mockProfile,
    uploadedAt: new Date().toISOString(),
  });

  return {
    success: true,
    datasetId,
    message: 'Dataset uploaded and validated successfully',
    profile: mockProfile,
  };
};

/**
 * Mock model selection
 */
export const mockGetModelSuggestions = async (
  datasetId: string
): Promise<ModelSelectionResponse> => {
  await delay(2000); // Simulate processing time

  const mockModels: ModelSelectionResponse['models'] = [
    {
      id: 'model_random_forest',
      name: 'Random Forest',
      type: 'classification',
      description: 'An ensemble method that builds multiple decision trees and combines their predictions.',
      estimatedAccuracy: 0.92,
      pros: [
        'Handles non-linear relationships well',
        'Robust to overfitting',
        'Provides feature importance scores',
        'Works well with mixed data types',
      ],
      cons: [
        'Can be memory intensive',
        'Less interpretable than single trees',
      ],
      recommended: true,
    },
    {
      id: 'model_xgboost',
      name: 'XGBoost',
      type: 'classification',
      description: 'An optimized gradient boosting framework that achieves state-of-the-art results.',
      estimatedAccuracy: 0.94,
      pros: [
        'High performance and accuracy',
        'Built-in regularization',
        'Handles missing values',
        'Fast training time',
      ],
      cons: [
        'Requires hyperparameter tuning',
        'Less interpretable',
      ],
      recommended: false,
    },
    {
      id: 'model_logistic_regression',
      name: 'Logistic Regression',
      type: 'classification',
      description: 'A linear model for classification that is fast and interpretable.',
      estimatedAccuracy: 0.85,
      pros: [
        'Fast training and prediction',
        'Highly interpretable',
        'No hyperparameter tuning needed',
        'Works well with linear relationships',
      ],
      cons: [
        'Assumes linear relationship',
        'Lower accuracy for complex patterns',
      ],
      recommended: false,
    },
    {
      id: 'model_neural_network',
      name: 'Neural Network',
      type: 'classification',
      description: 'A deep learning model that can learn complex patterns in the data.',
      estimatedAccuracy: 0.91,
      pros: [
        'Can learn complex non-linear patterns',
        'Flexible architecture',
        'Good for large datasets',
      ],
      cons: [
        'Requires large amounts of data',
        'Long training time',
        'Black box model',
        'Requires significant hyperparameter tuning',
      ],
      recommended: false,
    },
  ];

  return {
    success: true,
    models: mockModels,
    recommendedModelId: 'model_random_forest',
    reasoning: 'Based on your dataset characteristics (mixed data types, moderate size), Random Forest is recommended for its balance of accuracy, interpretability, and robustness.',
  };
};

/**
 * Mock training start
 */
export const mockStartTraining = async (
  request: TrainingStartRequest
): Promise<TrainingStartResponse> => {
  await delay(1000);

  const trainingId = `training_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  // Initialize training status
  mockStorage.trainings.set(trainingId, {
    trainingId,
    status: 'pending',
    progress: 0,
    currentStep: 'Initializing training...',
    elapsedTime: 0,
  });

  // Simulate training progress (in real implementation, this would be polled)
  simulateTrainingProgress(trainingId);

  return {
    success: true,
    trainingId,
    message: 'Training started successfully',
  };
};

/**
 * Simulate training progress
 */
const simulateTrainingProgress = (trainingId: string) => {
  const steps = [
    { progress: 10, step: 'Loading and preprocessing data...', delay: 2000 },
    { progress: 25, step: 'Splitting data into train/test sets...', delay: 1500 },
    { progress: 40, step: 'Training model...', delay: 4000 },
    { progress: 60, step: 'Validating model performance...', delay: 2500 },
    { progress: 80, step: 'Cross-validation...', delay: 3000 },
    { progress: 95, step: 'Finalizing model...', delay: 2000 },
    { progress: 100, step: 'Training completed!', delay: 500 },
  ];

  let currentStepIndex = 0;
  const startTime = Date.now();

  const updateProgress = () => {
    if (currentStepIndex >= steps.length) {
      const status = mockStorage.trainings.get(trainingId);
      if (status) {
        status.status = 'completed';
        status.progress = 100;
        status.currentStep = 'Training completed!';
        status.elapsedTime = Math.floor((Date.now() - startTime) / 1000);
        mockStorage.trainings.set(trainingId, status);

        // Generate mock results
        generateMockResults(trainingId);
      }
      return;
    }

    const step = steps[currentStepIndex];
    const status = mockStorage.trainings.get(trainingId);

    if (status && status.status !== 'stopped') {
      status.progress = step.progress;
      status.currentStep = step.step;
      status.elapsedTime = Math.floor((Date.now() - startTime) / 1000);
      status.estimatedTimeRemaining = Math.max(
        0,
        Math.ceil((100 - step.progress) * (status.elapsedTime / step.progress))
      );
      status.status = step.progress < 100 ? 'running' : 'completed';
      mockStorage.trainings.set(trainingId, status);
    }

    currentStepIndex++;
    if (currentStepIndex < steps.length) {
      setTimeout(updateProgress, step.delay);
    }
  };

  updateProgress();
};

/**
 * Generate mock training results
 */
const generateMockResults = (trainingId: string) => {
  const status = mockStorage.trainings.get(trainingId);
  if (!status) return;

  const results: TrainingResults = {
    trainingId,
    modelId: 'model_random_forest', // Default, should come from request
    status: 'completed',
    metrics: {
      accuracy: 0.92 + Math.random() * 0.05,
      precision: 0.90 + Math.random() * 0.06,
      recall: 0.91 + Math.random() * 0.05,
      f1Score: 0.905 + Math.random() * 0.05,
      confusionMatrix: [
        [450, 25],
        [30, 495],
      ],
      featureImportance: [
        { feature: 'feature1', importance: 0.35 },
        { feature: 'feature2', importance: 0.28 },
        { feature: 'feature3', importance: 0.20 },
        { feature: 'feature4', importance: 0.12 },
        { feature: 'feature5', importance: 0.05 },
      ],
    },
    modelSummary: 'Random Forest model trained successfully with 92.5% accuracy. The model shows good performance across all metrics with balanced precision and recall.',
    trainingDuration: status.elapsedTime || 0,
    trainingDate: new Date().toISOString(),
    downloadUrl: `#/download/${trainingId}`,
    apiEndpoint: `https://api.intellimodel.com/models/${trainingId}`,
  };

  mockStorage.results.set(trainingId, results);
};

/**
 * Mock get training status
 */
export const mockGetTrainingStatus = async (trainingId: string): Promise<TrainingStatus> => {
  await delay(300); // Small delay to simulate network

  const status = mockStorage.trainings.get(trainingId);
  if (!status) {
    throw {
      message: 'Training not found',
      code: 'NOT_FOUND',
    } as ApiError;
  }

  return status;
};

/**
 * Mock stop training
 */
export const mockStopTraining = async (trainingId: string): Promise<TrainingStopResponse> => {
  await delay(500);

  const status = mockStorage.trainings.get(trainingId);
  if (!status) {
    throw {
      message: 'Training not found',
      code: 'NOT_FOUND',
    } as ApiError;
  }

  if (status.status === 'completed' || status.status === 'failed') {
    throw {
      message: 'Cannot stop training that is already completed or failed',
      code: 'INVALID_STATE',
    } as ApiError;
  }

  status.status = 'stopped';
  status.currentStep = 'Training stopped by user';
  mockStorage.trainings.set(trainingId, status);

  return {
    success: true,
    message: 'Training stopped successfully',
  };
};

/**
 * Mock get results
 */
export const mockGetResults = async (trainingId: string): Promise<TrainingResults> => {
  await delay(500);

  const results = mockStorage.results.get(trainingId);
  if (!results) {
    throw {
      message: 'Results not found. Training may still be in progress.',
      code: 'NOT_FOUND',
    } as ApiError;
  }

  return results;
};

/**
 * Clear mock storage (useful for testing)
 */
export const clearMockStorage = () => {
  mockStorage.datasets.clear();
  mockStorage.trainings.clear();
  mockStorage.results.clear();
};

