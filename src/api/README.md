# API Integration Guide

This directory contains the API layer for IntelliModel, with built-in support for switching between mock and real backend APIs.

## Configuration

The API automatically switches between mock and real backend based on configuration. By default, the mock API is enabled for UI testing.

### Configuration File

The configuration is in `src/api/config.ts`:

```typescript
export const USE_MOCK_API = envMockApi === 'true' || (envMockApi === undefined && defaultMockApi);
```

### Environment Variables

You can control the API mode using environment variables:

- `VITE_USE_MOCK_API`: Set to `'true'` to use mock API, `'false'` for real backend
- `VITE_API_BASE_URL`: Base URL for the real backend (only used when mock is disabled)

### Switching to Real Backend

To switch from mock to real backend:

1. **Option 1: Environment Variable** (Recommended)
   - Create a `.env` file in the project root
   - Add: `VITE_USE_MOCK_API=false`
   - Add: `VITE_API_BASE_URL=http://your-backend-url/api`

2. **Option 2: Code Configuration**
   - Edit `src/api/config.ts`
   - Set `defaultMockApi = false`

## API Structure

### Files

- `config.ts`: Configuration for switching between mock and real APIs
- `types.ts`: TypeScript type definitions for all API requests and responses
- `mockApi.ts`: Mock implementations that simulate backend responses
- `api.ts`: Main API service that routes to mock or real implementations

### API Endpoints

The API service provides the following methods:

1. **Dataset Upload**
   - `api.uploadDataset(request: DatasetUploadRequest)`
   - Uploads a dataset file and returns profile information

2. **Model Selection**
   - `api.getModelSuggestions(datasetId: string)`
   - Returns recommended models based on dataset analysis

3. **Training**
   - `api.startTraining(request: TrainingStartRequest)`: Start model training
   - `api.getTrainingStatus(trainingId: string)`: Get current training status
   - `api.stopTraining(trainingId: string)`: Stop ongoing training

4. **Results**
   - `api.getResults(trainingId: string)`: Get training results and metrics

## Mock API Features

The mock API simulates:

- ✅ Dataset upload with validation and profiling
- ✅ Model suggestions with multiple options
- ✅ Training progress with realistic step-by-step updates
- ✅ Training status polling
- ✅ Final results with metrics and model information

### Mock Response Delays

The mock API includes realistic delays to simulate network requests:
- Dataset upload: ~1.5 seconds
- Model suggestions: ~2 seconds
- Training start: ~1 second
- Status polling: ~300ms (simulated)

## Usage Example

```typescript
import api from '@/api/api';

// Upload dataset
const response = await api.uploadDataset({ file: myFile });
console.log('Dataset ID:', response.datasetId);

// Get model suggestions
const models = await api.getModelSuggestions(response.datasetId);
console.log('Recommended model:', models.recommendedModelId);

// Start training
const training = await api.startTraining({
  datasetId: response.datasetId,
  modelId: models.recommendedModelId
});

// Poll for status
const status = await api.getTrainingStatus(training.trainingId);
console.log('Progress:', status.progress);
```

## Real Backend Integration

When switching to the real backend, implement the API endpoints in `api.ts` under the `realApi` object. The structure is already set up - you just need to implement the fetch calls with your actual backend endpoints.

The real API implementations should match the mock API response structures defined in `types.ts`.

