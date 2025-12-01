/**
 * Main API service
 * Switches between mock and real backend based on configuration
 */

import { USE_MOCK_API } from './config';
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

// Import mock implementations
import {
  mockUploadDataset,
  mockGetModelSuggestions,
  mockStartTraining,
  mockGetTrainingStatus,
  mockStopTraining,
  mockGetResults,
} from './mockApi';

/**
 * Real API implementations (to be implemented when backend is ready)
 */
const realApi = {
  uploadDataset: async (request: DatasetUploadRequest): Promise<DatasetUploadResponse> => {
    const formData = new FormData();
    formData.append('file', request.file);

    const response = await fetch('/api/datasets/upload', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw error;
    }

    return response.json();
  },

  getModelSuggestions: async (datasetId: string): Promise<ModelSelectionResponse> => {
    const response = await fetch(`/api/models/suggest?datasetId=${datasetId}`);

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw error;
    }

    return response.json();
  },

  startTraining: async (request: TrainingStartRequest): Promise<TrainingStartResponse> => {
    const response = await fetch('/api/training/start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw error;
    }

    return response.json();
  },

  getTrainingStatus: async (trainingId: string): Promise<TrainingStatus> => {
    const response = await fetch(`/api/training/status?trainingId=${trainingId}`);

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw error;
    }

    return response.json();
  },

  stopTraining: async (trainingId: string): Promise<TrainingStopResponse> => {
    const response = await fetch('/api/training/stop', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ trainingId }),
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw error;
    }

    return response.json();
  },

  getResults: async (trainingId: string): Promise<TrainingResults> => {
    const response = await fetch(`/api/results?trainingId=${trainingId}`);

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw error;
    }

    return response.json();
  },
};

/**
 * API service that switches between mock and real based on configuration
 */
export const api = {
  /**
   * Upload a dataset file
   */
  uploadDataset: async (request: DatasetUploadRequest): Promise<DatasetUploadResponse> => {
    if (USE_MOCK_API) {
      return mockUploadDataset(request);
    }
    return realApi.uploadDataset(request);
  },

  /**
   * Get model suggestions for a dataset
   */
  getModelSuggestions: async (datasetId: string): Promise<ModelSelectionResponse> => {
    if (USE_MOCK_API) {
      return mockGetModelSuggestions(datasetId);
    }
    return realApi.getModelSuggestions(datasetId);
  },

  /**
   * Start model training
   */
  startTraining: async (request: TrainingStartRequest): Promise<TrainingStartResponse> => {
    if (USE_MOCK_API) {
      return mockStartTraining(request);
    }
    return realApi.startTraining(request);
  },

  /**
   * Get training status
   */
  getTrainingStatus: async (trainingId: string): Promise<TrainingStatus> => {
    if (USE_MOCK_API) {
      return mockGetTrainingStatus(trainingId);
    }
    return realApi.getTrainingStatus(trainingId);
  },

  /**
   * Stop training
   */
  stopTraining: async (trainingId: string): Promise<TrainingStopResponse> => {
    if (USE_MOCK_API) {
      return mockStopTraining(trainingId);
    }
    return realApi.stopTraining(trainingId);
  },

  /**
   * Get training results
   */
  getResults: async (trainingId: string): Promise<TrainingResults> => {
    if (USE_MOCK_API) {
      return mockGetResults(trainingId);
    }
    return realApi.getResults(trainingId);
  },
};

export default api;

