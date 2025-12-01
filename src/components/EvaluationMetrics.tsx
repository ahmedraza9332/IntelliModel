import React from "react";
import { cn } from "@/lib/utils";
import { Separator } from "@/components/ui/separator";
import type { ModelMetrics } from "@/api/iterativeTypes";

export interface EvaluationMetricsProps {
  metrics: ModelMetrics;
  className?: string;
}

const EvaluationMetrics: React.FC<EvaluationMetricsProps> = ({
  metrics,
  className,
}) => {
  const formatTime = (seconds: number): string => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}m ${secs}s`;
  };

  return (
    <div className={cn("space-y-4", className)}>
      {/* Primary Metrics Grid */}
      <div className="grid grid-cols-2 gap-4">
        <MetricItem
          label="Accuracy"
          value={metrics.accuracy}
          format="percentage"
        />
        <MetricItem
          label="Precision"
          value={metrics.precision}
          format="percentage"
        />
        <MetricItem
          label="Recall"
          value={metrics.recall}
          format="percentage"
        />
        <MetricItem
          label="F1 Score"
          value={metrics.f1Score}
          format="percentage"
        />
      </div>

      <Separator />

      {/* Execution Time */}
      <div className="flex items-center justify-between py-2">
        <span className="text-sm font-medium text-gray-700">
          Execution Time
        </span>
        <span className="text-base font-semibold text-gray-900">
          {formatTime(metrics.executionTime)}
        </span>
      </div>

      {/* Loss and Validation Metrics */}
      {metrics.metadata && (
        <>
          <Separator />
          <div className="space-y-2">
            {metrics.metadata.loss !== undefined && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600">Loss:</span>
                <span className="font-medium text-gray-900">
                  {metrics.metadata.loss.toFixed(4)}
                </span>
              </div>
            )}
            {metrics.metadata.validationLoss !== undefined && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600">Validation Loss:</span>
                <span className="font-medium text-gray-900">
                  {metrics.metadata.validationLoss.toFixed(4)}
                </span>
              </div>
            )}
            {metrics.metadata.validationAccuracy !== undefined && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600">Validation Accuracy:</span>
                <span className="font-medium text-gray-900">
                  {(metrics.metadata.validationAccuracy * 100).toFixed(2)}%
                </span>
              </div>
            )}
            {metrics.metadata.epochs !== undefined && (
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-600">Epochs:</span>
                <span className="font-medium text-gray-900">
                  {metrics.metadata.epochs}
                </span>
              </div>
            )}
          </div>
        </>
      )}

      {/* Confusion Matrix */}
      {metrics.confusionMatrix && metrics.confusionMatrix.length > 0 && (
        <>
          <Separator />
          <div>
            <h4 className="text-sm font-semibold text-gray-900 mb-2">
              Confusion Matrix
            </h4>
            <div className="inline-block rounded-md border border-slate-200 overflow-hidden">
              <table className="text-xs">
                <tbody>
                  {metrics.confusionMatrix.map((row, rowIdx) => (
                    <tr key={rowIdx}>
                      {row.map((cell, colIdx) => (
                        <td
                          key={colIdx}
                          className={cn(
                            "border border-slate-200 px-3 py-2 text-center font-medium",
                            rowIdx === colIdx
                              ? "bg-emerald-50 text-emerald-900"
                              : "bg-white text-gray-900"
                          )}
                        >
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Additional Metadata */}
      {metrics.metadata && Object.keys(metrics.metadata).length > 0 && (
        <>
          {Object.keys(metrics.metadata).some(
            (key) =>
              !["loss", "validationLoss", "validationAccuracy", "epochs"].includes(key)
          ) && (
            <>
              <Separator />
              <div>
                <h4 className="text-sm font-semibold text-gray-900 mb-2">
                  Additional Metadata
                </h4>
                <div className="space-y-1">
                  {Object.entries(metrics.metadata)
                    .filter(
                      ([key]) =>
                        !["loss", "validationLoss", "validationAccuracy", "epochs"].includes(key)
                    )
                    .map(([key, value]) => (
                      <div
                        key={key}
                        className="flex items-center justify-between text-sm"
                      >
                        <span className="text-gray-600 capitalize">
                          {key.replace(/([A-Z])/g, " $1").trim()}:
                        </span>
                        <span className="font-medium text-gray-900">
                          {typeof value === "number"
                            ? value.toFixed(4)
                            : String(value)}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
};

interface MetricItemProps {
  label: string;
  value: number;
  format?: "percentage" | "number";
}

const MetricItem: React.FC<MetricItemProps> = ({
  label,
  value,
  format = "number",
}) => {
  const formatValue = (val: number) => {
    if (format === "percentage") {
      return `${(val * 100).toFixed(2)}%`;
    }
    return val.toFixed(4);
  };

  return (
    <div className="space-y-1">
      <div className="text-xs font-medium text-gray-500">{label}</div>
      <div className="text-lg font-bold text-gray-900">{formatValue(value)}</div>
    </div>
  );
};

export default EvaluationMetrics;

