import React from "react";
import { cn } from "@/lib/utils";
import { Progress } from "@/components/ui/progress";

export interface PipelineProgressBarProps {
  progress: number; // 0-100
  className?: string;
  showPercentage?: boolean;
}

const PipelineProgressBar: React.FC<PipelineProgressBarProps> = ({
  progress,
  className,
  showPercentage = true,
}) => {
  const clampedProgress = Math.max(0, Math.min(100, progress));

  return (
    <div className={cn("w-full space-y-2", className)}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-900">
          Pipeline Progress
        </span>
        {showPercentage && (
          <span className="text-sm font-medium text-pulse-600">
            {Math.round(clampedProgress)}%
          </span>
        )}
      </div>
      <Progress
        value={clampedProgress}
        className="h-3"
      />
    </div>
  );
};

export default PipelineProgressBar;

