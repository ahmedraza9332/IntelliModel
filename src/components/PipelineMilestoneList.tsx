import React from "react";
import { cn } from "@/lib/utils";
import PipelineStep, { StepStatus } from "./PipelineStep";

export interface Milestone {
  id: string;
  title: string;
  description?: string;
  status: StepStatus;
}

export interface PipelineMilestoneListProps {
  milestones: Milestone[];
  className?: string;
}

const PipelineMilestoneList: React.FC<PipelineMilestoneListProps> = ({
  milestones,
  className,
}) => {
  // Find the currently active (running) milestone
  const activeIndex = milestones.findIndex((m) => m.status === "running");

  return (
    <div className={cn("space-y-3", className)}>
      {milestones.map((milestone, index) => (
        <PipelineStep
          key={milestone.id}
          title={milestone.title}
          description={milestone.description}
          status={milestone.status}
          isActive={index === activeIndex}
        />
      ))}
    </div>
  );
};

export default PipelineMilestoneList;

