import React from "react";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { TrendingUp, Sparkles } from "lucide-react";
import type { ModelOption } from "@/api/types";

export interface ModelSelectionProps {
  models: ModelOption[];
  selectedModelIds: string[];
  onSelectionChange: (modelIds: string[]) => void;
  recommendedModelId?: string;
  reasoning?: string;
  className?: string;
}

const ModelSelection: React.FC<ModelSelectionProps> = ({
  models,
  selectedModelIds,
  onSelectionChange,
  recommendedModelId,
  reasoning,
  className,
}) => {
  const handleToggle = (modelId: string) => {
    if (selectedModelIds.includes(modelId)) {
      onSelectionChange(selectedModelIds.filter((id) => id !== modelId));
    } else {
      onSelectionChange([...selectedModelIds, modelId]);
    }
  };

  return (
    <div className={cn("space-y-6", className)}>
      {reasoning && (
        <Card className="border-pulse-200 bg-pulse-50/50">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4 text-pulse-600" />
              AI Recommendation
            </CardTitle>
            <CardDescription className="text-sm">{reasoning}</CardDescription>
          </CardHeader>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        {models.map((model) => {
          const isSelected = selectedModelIds.includes(model.id);
          const isRecommended = model.id === recommendedModelId;

          return (
            <Card
              key={model.id}
              className={cn(
                "cursor-pointer transition-all hover:shadow-lg",
                isSelected
                  ? "border-pulse-500 bg-pulse-50/50 shadow-md ring-2 ring-pulse-300"
                  : "border-slate-200 hover:border-pulse-300"
              )}
              onClick={() => handleToggle(model.id)}
            >
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-3 flex-1">
                    <Checkbox
                      checked={isSelected}
                      onCheckedChange={() => handleToggle(model.id)}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-1"
                    />
                    <div className="flex-1">
                      <CardTitle className="flex items-center gap-2 text-lg">
                        {model.name}
                        {isRecommended && (
                          <Badge className="bg-pulse-500 text-white">
                            Recommended
                          </Badge>
                        )}
                      </CardTitle>
                      <CardDescription className="mt-1 text-sm">
                        {model.description}
                      </CardDescription>
                    </div>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                {model.estimatedAccuracy && (
                  <div className="mb-4 flex items-center gap-2">
                    <TrendingUp className="h-4 w-4 text-green-500" />
                    <span className="text-sm font-semibold text-gray-900">
                      Estimated Accuracy: {(model.estimatedAccuracy * 100).toFixed(1)}%
                    </span>
                  </div>
                )}
                <div className="space-y-3">
                  <div>
                    <p className="text-xs font-semibold uppercase text-green-700 mb-2">
                      Pros:
                    </p>
                    <ul className="space-y-1">
                      {model.pros.slice(0, 2).map((pro, idx) => (
                        <li
                          key={idx}
                          className="flex items-start gap-2 text-xs text-gray-600"
                        >
                          <span className="text-green-500 mt-0.5">•</span>
                          {pro}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {selectedModelIds.length > 0 && (
        <div className="rounded-lg border border-pulse-200 bg-pulse-50/50 p-4">
          <p className="text-sm font-medium text-pulse-900">
            {selectedModelIds.length} model{selectedModelIds.length > 1 ? "s" : ""} selected
          </p>
          <p className="text-xs text-pulse-700 mt-1">
            You can select multiple models to compare their performance
          </p>
        </div>
      )}
    </div>
  );
};

export default ModelSelection;

