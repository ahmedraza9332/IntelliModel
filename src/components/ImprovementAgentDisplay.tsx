import React, { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { CheckCircle2, Loader2, Circle, Settings2 } from "lucide-react";
import type { OptimizationTechnique } from "@/api/iterativeTypes";

export interface ImprovementAgentDisplayProps {
  techniques: OptimizationTechnique[];
  onComplete?: () => void;
  className?: string;
}

const ImprovementAgentDisplay: React.FC<ImprovementAgentDisplayProps> = ({
  techniques,
  onComplete,
  className,
}) => {
  const [activeTechniques, setActiveTechniques] = useState<OptimizationTechnique[]>(techniques);

  useEffect(() => {
    setActiveTechniques(techniques);
    
    // Simulate technique execution
    let currentIndex = 0;
    const executeTechnique = () => {
      if (currentIndex >= activeTechniques.length) {
        if (onComplete) {
          setTimeout(onComplete, 500);
        }
        return;
      }

      const updated = [...activeTechniques];
      updated[currentIndex] = { ...updated[currentIndex], status: 'running' };
      setActiveTechniques(updated);

      // Simulate completion after delay
      setTimeout(() => {
        const completed = [...activeTechniques];
        completed[currentIndex] = { ...completed[currentIndex], status: 'completed' };
        setActiveTechniques(completed);
        currentIndex++;
        setTimeout(executeTechnique, 800);
      }, 1500 + Math.random() * 1000);
    };

    executeTechnique();
  }, []);

  const completedCount = activeTechniques.filter((t) => t.status === 'completed').length;
  const progress = (completedCount / activeTechniques.length) * 100;

  const getStatusIcon = (status: OptimizationTechnique['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="h-5 w-5 text-emerald-500" />;
      case 'running':
        return <Loader2 className="h-5 w-5 text-pulse-500 animate-spin" />;
      case 'pending':
      default:
        return <Circle className="h-5 w-5 text-gray-300" />;
    }
  };

  return (
    <Card className={cn("border-pulse-200 bg-pulse-50/30", className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Settings2 className="h-5 w-5 text-pulse-600" />
          Improvement Agent
        </CardTitle>
        <CardDescription>
          Optimizing model performance through various techniques
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-gray-900">Overall Progress</span>
            <span className="text-sm font-medium text-pulse-600">
              {completedCount} / {activeTechniques.length}
            </span>
          </div>
          <Progress value={progress} className="h-3" />
        </div>

        <div className="space-y-3">
          {activeTechniques.map((technique, index) => (
            <div
              key={index}
              className={cn(
                "flex items-start gap-4 rounded-lg border p-4 transition-all",
                technique.status === 'completed' && "border-emerald-200 bg-emerald-50/50",
                technique.status === 'running' && "border-pulse-200 bg-pulse-50/50",
                technique.status === 'pending' && "border-gray-200 bg-white"
              )}
            >
              <div className="mt-0.5">{getStatusIcon(technique.status)}</div>
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-gray-900">
                    {technique.name}
                  </h4>
                  {technique.status === 'completed' && (
                    <span className="text-xs font-medium text-emerald-700">
                      Complete
                    </span>
                  )}
                  {technique.status === 'running' && (
                    <span className="text-xs font-medium text-pulse-700">
                      Running...
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-gray-600">
                  {technique.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default ImprovementAgentDisplay;

