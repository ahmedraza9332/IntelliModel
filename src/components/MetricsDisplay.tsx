import React from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { ModelMetrics } from "@/api/iterativeTypes";

export interface MetricsDisplayProps {
  metrics: ModelMetrics;
  beforeMetrics?: ModelMetrics;
  title?: string;
  showComparison?: boolean;
  className?: string;
}

const MetricsDisplay: React.FC<MetricsDisplayProps> = ({
  metrics,
  beforeMetrics,
  title = "Model Metrics",
  showComparison = false,
  className,
}) => {
  const calculateChange = (current: number, before: number): number => {
    if (before === 0) return 0;
    return ((current - before) / before) * 100;
  };

  const getChangeIcon = (change: number) => {
    if (change > 0) return <TrendingUp className="h-4 w-4 text-green-500" />;
    if (change < 0) return <TrendingDown className="h-4 w-4 text-red-500" />;
    return <Minus className="h-4 w-4 text-gray-400" />;
  };

  const getChangeColor = (change: number, isPositive: boolean) => {
    if (!showComparison) return "";
    if (change > 0 && isPositive) return "text-green-600";
    if (change < 0 && isPositive) return "text-red-600";
    if (change > 0 && !isPositive) return "text-red-600";
    if (change < 0 && !isPositive) return "text-green-600";
    return "text-gray-600";
  };

  return (
    <Card className={cn("border-slate-200", className)}>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Primary Metrics */}
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <MetricCard
            label="Accuracy"
            value={metrics.accuracy}
            beforeValue={beforeMetrics?.accuracy}
            showComparison={showComparison}
            format="percentage"
          />
          <MetricCard
            label="Precision"
            value={metrics.precision}
            beforeValue={beforeMetrics?.precision}
            showComparison={showComparison}
            format="percentage"
          />
          <MetricCard
            label="Recall"
            value={metrics.recall}
            beforeValue={beforeMetrics?.recall}
            showComparison={showComparison}
            format="percentage"
          />
          <MetricCard
            label="F1 Score"
            value={metrics.f1Score}
            beforeValue={beforeMetrics?.f1Score}
            showComparison={showComparison}
            format="percentage"
          />
        </div>

        {/* Execution Time */}
        <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-700">
              Execution Time
            </span>
            <span className="text-lg font-semibold text-gray-900">
              {formatTime(metrics.executionTime)}
            </span>
          </div>
        </div>

        {/* Confusion Matrix */}
        {metrics.confusionMatrix && (
          <div>
            <h4 className="text-sm font-semibold text-gray-900 mb-3">
              Confusion Matrix
            </h4>
            <div className="inline-block rounded-lg border border-slate-200 overflow-hidden">
              <table className="text-sm">
                <tbody>
                  {metrics.confusionMatrix.map((row, rowIdx) => (
                    <tr key={rowIdx}>
                      {row.map((cell, colIdx) => (
                        <td
                          key={colIdx}
                          className={cn(
                            "border border-slate-200 px-4 py-2 text-center font-medium",
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
        )}
      </CardContent>
    </Card>
  );
};

interface MetricCardProps {
  label: string;
  value: number;
  beforeValue?: number;
  showComparison?: boolean;
  format?: "percentage" | "number";
}

const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  beforeValue,
  showComparison = false,
  format = "number",
}) => {
  const change = beforeValue !== undefined
    ? ((value - beforeValue) / beforeValue) * 100
    : 0;

  const formatValue = (val: number) => {
    if (format === "percentage") {
      return `${(val * 100).toFixed(2)}%`;
    }
    return val.toFixed(4);
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="text-xs font-medium text-gray-500 mb-1">{label}</div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold text-gray-900">
          {formatValue(value)}
        </span>
        {showComparison && beforeValue !== undefined && (
          <span
            className={cn(
              "text-xs font-medium flex items-center gap-1",
              change > 0 ? "text-green-600" : change < 0 ? "text-red-600" : "text-gray-600"
            )}
          >
            {change > 0 && <TrendingUp className="h-3 w-3" />}
            {change < 0 && <TrendingDown className="h-3 w-3" />}
            {formatChange(change)}
          </span>
        )}
      </div>
    </div>
  );
};

const formatTime = (seconds: number): string => {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}m ${secs}s`;
};

const formatChange = (change: number): string => {
  const sign = change > 0 ? "+" : "";
  return `${sign}${change.toFixed(2)}%`;
};

export default MetricsDisplay;

