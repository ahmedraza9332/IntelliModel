import React from "react";
import { cn } from "@/lib/utils";
import { CheckCircle2, XCircle, Loader2, Circle } from "lucide-react";

export type StepStatus = "pending" | "running" | "completed" | "failed";

export interface PipelineStepProps {
  title: string;
  description?: string;
  status: StepStatus;
  isActive?: boolean;
  className?: string;
}

const PipelineStep: React.FC<PipelineStepProps> = ({
  title,
  description,
  status,
  isActive = false,
  className,
}) => {
  const getStatusIcon = () => {
    switch (status) {
      case "completed":
        return (
          <CheckCircle2 className="h-5 w-5 text-emerald-500 flex-shrink-0" />
        );
      case "failed":
        return <XCircle className="h-5 w-5 text-red-500 flex-shrink-0" />;
      case "running":
        return (
          <Loader2 className="h-5 w-5 text-pulse-500 flex-shrink-0 animate-spin" />
        );
      case "pending":
      default:
        return (
          <Circle className="h-5 w-5 text-gray-300 flex-shrink-0" />
        );
    }
  };

  const getStatusText = () => {
    switch (status) {
      case "completed":
        return "Completed";
      case "failed":
        return "Failed";
      case "running":
        return "In Progress";
      case "pending":
      default:
        return "Pending";
    }
  };

  const getStatusColor = () => {
    switch (status) {
      case "completed":
        return "border-emerald-200 bg-emerald-50";
      case "failed":
        return "border-red-200 bg-red-50";
      case "running":
        return "border-pulse-200 bg-pulse-50";
      case "pending":
      default:
        return "border-gray-200 bg-white";
    }
  };

  return (
    <div
      className={cn(
        "flex items-start gap-4 rounded-lg border-2 p-4 transition-all duration-300",
        getStatusColor(),
        isActive && "ring-2 ring-pulse-300 ring-offset-2",
        className
      )}
    >
      <div className="mt-0.5">{getStatusIcon()}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <h3
            className={cn(
              "text-sm font-semibold",
              status === "completed" && "text-emerald-900",
              status === "failed" && "text-red-900",
              status === "running" && "text-pulse-900",
              status === "pending" && "text-gray-600"
            )}
          >
            {title}
          </h3>
          <span
            className={cn(
              "text-xs font-medium",
              status === "completed" && "text-emerald-700",
              status === "failed" && "text-red-700",
              status === "running" && "text-pulse-700",
              status === "pending" && "text-gray-400"
            )}
          >
            {getStatusText()}
          </span>
        </div>
        {description && (
          <p
            className={cn(
              "mt-1 text-xs",
              status === "pending" ? "text-gray-400" : "text-gray-600"
            )}
          >
            {description}
          </p>
        )}
      </div>
    </div>
  );
};

export default PipelineStep;

