import React from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { CheckCircle2, Loader2, Circle, XCircle } from "lucide-react";
import type { ModelTrainingState } from "@/api/iterativeTypes";

export interface MultiModelProgressProps {
  models: ModelTrainingState[];
  className?: string;
}

const MultiModelProgress: React.FC<MultiModelProgressProps> = ({
  models,
  className,
}) => {
  const getStatusIcon = (status: ModelTrainingState['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-5 w-5 text-emerald-500" />;
      case 'training':
        return <Loader2 className="h-5 w-5 text-pulse-500 animate-spin" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-500" />;
      case 'pending':
      default:
        return <Circle className="h-5 w-5 text-gray-300" />;
    }
  };

  const getStatusColor = (status: ModelTrainingState['status']) => {
    switch (status) {
      case 'completed':
        return 'border-emerald-200 bg-emerald-50/50';
      case 'training':
        return 'border-pulse-200 bg-pulse-50/50';
      case 'failed':
        return 'border-red-200 bg-red-50/50';
      case 'pending':
      default:
        return 'border-gray-200 bg-white';
    }
  };

  return (
    <div className={cn("space-y-4", className)}>
      {models.map((model) => (
        <Card
          key={model.modelId}
          className={cn("border-2 transition-all", getStatusColor(model.status))}
        >
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-3 text-lg">
                {getStatusIcon(model.status)}
                {model.modelName}
              </CardTitle>
              <span className="text-sm font-medium text-gray-600">
                {model.status === 'training' && `${model.progress}%`}
                {model.status === 'completed' && 'Complete'}
                {model.status === 'pending' && 'Pending'}
                {model.status === 'failed' && 'Failed'}
              </span>
            </div>
          </CardHeader>
          <CardContent>
            {model.status === 'training' && (
              <div className="space-y-2">
                <Progress value={model.progress} className="h-2" />
                {model.executionTime !== undefined && (
                  <p className="text-xs text-gray-500">
                    Execution time: {formatTime(model.executionTime)}
                  </p>
                )}
              </div>
            )}
            {model.status === 'completed' && model.metrics && (
              <div className="mt-2 grid grid-cols-4 gap-2 text-xs">
                <div>
                  <span className="text-gray-500">Accuracy:</span>
                  <span className="ml-1 font-semibold text-gray-900">
                    {(model.metrics.accuracy * 100).toFixed(1)}%
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">F1:</span>
                  <span className="ml-1 font-semibold text-gray-900">
                    {(model.metrics.f1Score * 100).toFixed(1)}%
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Precision:</span>
                  <span className="ml-1 font-semibold text-gray-900">
                    {(model.metrics.precision * 100).toFixed(1)}%
                  </span>
                </div>
                <div>
                  <span className="text-gray-500">Recall:</span>
                  <span className="ml-1 font-semibold text-gray-900">
                    {(model.metrics.recall * 100).toFixed(1)}%
                  </span>
                </div>
              </div>
            )}
            {model.improvementIterations > 0 && (
              <div className="mt-2 text-xs text-pulse-600">
                Improvement iterations: {model.improvementIterations}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
};

const formatTime = (seconds: number): string => {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
};

export default MultiModelProgress;

