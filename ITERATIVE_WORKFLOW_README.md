# Iterative ML Workflow Implementation

This document describes the interactive iterative ML workflow features that have been integrated into IntelliModel.

## Features Implemented

### 1. Multi-Model Selection
- Users can select **multiple models** using checkboxes
- Each model card shows:
  - Estimated accuracy
  - Pros and cons
  - Recommended badge (if applicable)
- Visual feedback for selected models

### 2. Multi-Model Training
- Parallel training of multiple selected models
- Individual progress bars for each model
- Real-time status updates (pending → training → completed)
- Separate metrics displayed for each model

### 3. Metrics Display
- Comprehensive metrics visualization:
  - Accuracy
  - Precision
  - Recall
  - F1 Score
  - Confusion Matrix
  - Execution Time
- BEFORE vs AFTER comparison (when improvements are applied)
- Color-coded improvements (green for positive, red for negative)

### 4. Improvement Agent
- Visual display of optimization techniques being applied:
  - Hyperparameter Tuning
  - Dropout Tuning
  - Regularization
  - Early Stopping
  - Learning Rate Scheduling
  - Feature Engineering
  - Cross-Validation
- Progress tracking for each technique
- Automatic improvement iteration simulation

### 5. User Decision Dialogs
Two types of interactive dialogs:

**A) Metrics Decision Dialog** (after initial training)
- "Proceed to Full Training & Deployment"
- "Send to Improvement Agent"

**B) Improvement Satisfaction Dialog** (after improvement)
- "Yes, Proceed to Full Training & Deployment"
- "Improve Again" (up to 3 iterations)
- "Reject & Select Different Model" (after 3 iterations)

### 6. Iteration Loop
- Maximum 3 improvement iterations per model
- After 3 iterations, user must either:
  - Accept and deploy
  - Reject and return to model selection
- Each iteration shows BEFORE/AFTER metrics comparison

### 7. Deployment
- Mock deployment simulation
- Success message with API endpoint
- Final results display

## Components Created

### `/src/components/`
1. **ModelSelection.tsx** - Multi-select model picker with checkboxes
2. **MetricsDisplay.tsx** - Comprehensive metrics visualization with comparison
3. **ImprovementAgentDisplay.tsx** - Shows optimization techniques in progress
4. **IterationDialog.tsx** - User decision dialogs (MetricsDecisionDialog, ImprovementSatisfactionDialog)
5. **MultiModelProgress.tsx** - Progress tracking for multiple models

### `/src/api/`
1. **iterativeTypes.ts** - TypeScript types for iterative workflow
2. **iterativeService.ts** - Mock services for:
   - Model training
   - Improvement agent execution
   - Metrics generation
   - Deployment simulation

## Workflow Stages

The workflow now supports these stages:
1. `upload` - Dataset upload
2. `model-selection` - Multi-model selection
3. `multi-training` - Parallel model training
4. `metrics-review` - Review training metrics
5. `improvement` - Improvement agent optimization
6. `deployment` - Model deployment
7. `results` - Final results

## State Management

The workflow uses React state to track:
- Selected model IDs (array)
- Training states for each model (Map)
- Current model being reviewed
- Improvement iterations count
- Dialog visibility states
- Improvement techniques status

## Mock Data

All features use mock data that simulates:
- Realistic training delays
- Realistic metrics values
- Improvement techniques execution
- BEFORE/AFTER metric changes
- Deployment process

## Future Backend Integration

The architecture is designed for easy backend integration:

1. **Replace mock services** in `iterativeService.ts` with real API calls
2. **Update state management** to use WebSocket events or polling
3. **Replace mock timers** with real backend status updates
4. **Connect dialogs** to real backend decision endpoints

The component structure and state management remain the same - only the data source changes.

## Usage Example

```tsx
// User selects multiple models
setSelectedModelIds(['model1', 'model2']);

// Start training
handleStartMultiModelTraining();

// Training progresses in parallel
// User reviews metrics
// User decides: improve or deploy

// If improve:
handleStartImprovement(modelId);
// Improvement agent runs
// User reviews improved metrics
// User decides: improve again, deploy, or reject

// If deploy:
handleDeployment(modelId);
```

## UI/UX Features

- ✅ Consistent styling with existing UI
- ✅ Reusable components
- ✅ Clear visual feedback
- ✅ Progress indicators
- ✅ Error handling
- ✅ Responsive design
- ✅ Accessibility considerations

