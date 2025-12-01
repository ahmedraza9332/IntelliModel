/**
 * API Configuration
 * 
 * Set USE_MOCK_API to true to use mock data, false to use real backend.
 * Can also be controlled via environment variable VITE_USE_MOCK_API
 */

// Check environment variable first, then fallback to default
const envMockApi = import.meta.env.VITE_USE_MOCK_API;
const defaultMockApi = true; // Default to mock for now

export const USE_MOCK_API = envMockApi === 'true' || (envMockApi === undefined && defaultMockApi);

// Real backend API base URL (only used when USE_MOCK_API is false)
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

// API endpoints
export const API_ENDPOINTS = {
  UPLOAD_DATASET: '/datasets/upload',
  GET_MODELS: '/models/suggest',
  START_TRAINING: '/training/start',
  STOP_TRAINING: '/training/stop',
  GET_TRAINING_STATUS: '/training/status',
  GET_RESULTS: '/results',
} as const;

