# Pipeline Progress Components

This directory contains reusable components for displaying ML pipeline execution progress.

## Components

### PipelineStep
Individual step/milestone component with visual states:
- **Pending**: Gray circle icon
- **Running**: Spinning pulse-colored icon
- **Completed**: Green checkmark icon
- **Failed**: Red X icon

Props:
- `title`: Step title
- `description`: Optional step description
- `status`: One of "pending" | "running" | "completed" | "failed"
- `isActive`: Highlight the step as currently active

### PipelineProgressBar
Overall progress bar showing 0-100% completion.

Props:
- `progress`: Number from 0-100
- `showPercentage`: Whether to show percentage text (default: true)

### PipelineMilestoneList
List of milestones with automatic active state highlighting.

Props:
- `milestones`: Array of milestone objects with id, title, description, and status

## Usage Example

```tsx
import PipelineProgressBar from "@/components/PipelineProgressBar";
import PipelineMilestoneList from "@/components/PipelineMilestoneList";
import type { Milestone } from "@/components/PipelineMilestoneList";

const milestones: Milestone[] = [
  {
    id: "step1",
    title: "Dataset Uploaded",
    description: "File validated and received",
    status: "completed",
  },
  {
    id: "step2",
    title: "Processing",
    status: "running",
  },
];

<PipelineProgressBar progress={45} />
<PipelineMilestoneList milestones={milestones} />
```

## Integration with Pipeline Service

The components work seamlessly with the `pipelineService` from `@/api/pipelineService`. Use the `usePipeline` hook to get state:

```tsx
import { usePipeline } from "@/hooks/usePipeline";

const { state, startPipeline } = usePipeline(pipelineId);

// Convert to component format
const milestones = state?.milestones.map(m => ({
  id: m.id,
  title: m.title,
  description: m.description,
  status: m.status,
})) || [];

<PipelineProgressBar progress={state?.overallProgress || 0} />
<PipelineMilestoneList milestones={milestones} />
```

## Styling

Components use Tailwind CSS and are consistent with the existing IntelliModel design system:
- Pulse color scheme for active/running states
- Emerald for completed states
- Red for failed states
- Consistent spacing and typography

