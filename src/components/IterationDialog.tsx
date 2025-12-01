import React, { useState } from "react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Rocket, Sparkles, RefreshCw } from "lucide-react";
import type { UserDecision, ModelMetrics } from "@/api/iterativeTypes";
import EvaluationMetrics from "./EvaluationMetrics";
import ConfirmationPopup from "./ConfirmationPopup";

export interface IterationDialogProps {
  open: boolean;
  title: string;
  description: string;
  options: {
    label: string;
    value: UserDecision['type'];
    icon?: React.ReactNode;
    variant?: "default" | "outline" | "destructive";
  }[];
  onSelect: (decision: UserDecision) => void;
  onCancel?: () => void;
  showThirdOption?: boolean;
}

const IterationDialog: React.FC<IterationDialogProps> = ({
  open,
  title,
  description,
  options,
  onSelect,
  onCancel,
  showThirdOption = false,
}) => {
  const handleSelect = (type: UserDecision['type']) => {
    onSelect({ type });
  };

  return (
    <AlertDialog open={open}>
      <AlertDialogContent className="max-w-2xl">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-xl">{title}</AlertDialogTitle>
          <AlertDialogDescription className="text-base pt-2">
            {description}
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="py-4 space-y-3">
          {options.map((option, index) => (
            <Button
              key={index}
              variant={option.variant || "outline"}
              className="w-full justify-start h-auto py-4 px-4 text-left"
              onClick={() => handleSelect(option.value)}
            >
              <div className="flex items-start gap-3 w-full">
                {option.icon && (
                  <div className="mt-0.5 flex-shrink-0">{option.icon}</div>
                )}
                <span className="font-medium">{option.label}</span>
              </div>
            </Button>
          ))}
        </div>

        <AlertDialogFooter>
          {onCancel && (
            <AlertDialogCancel onClick={onCancel}>Cancel</AlertDialogCancel>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
};

// Predefined dialog configurations
export const MetricsDecisionDialog: React.FC<{
  open: boolean;
  metrics?: ModelMetrics;
  onSelect: (decision: UserDecision) => void;
  onCancel?: () => void;
  onConfirmCancel?: () => void;
  iterationCount?: number;
}> = ({ open, metrics, onSelect, onCancel, onConfirmCancel, iterationCount = 0 }) => {
  const [showCancelConfirmation, setShowCancelConfirmation] = useState(false);

  const handleCancelClick = () => {
    setShowCancelConfirmation(true);
  };

  const handleConfirmCancel = () => {
    setShowCancelConfirmation(false);
    if (onConfirmCancel) {
      onConfirmCancel();
    } else if (onCancel) {
      onCancel();
    }
  };

  const handleCancelConfirmationCancel = () => {
    setShowCancelConfirmation(false);
  };

  return (
    <>
      <AlertDialog open={open && !showCancelConfirmation}>
        <AlertDialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-xl">Training Complete</AlertDialogTitle>
            <AlertDialogDescription className="text-base pt-2">
              The model has completed initial training. Review the metrics below and choose your next action.
            </AlertDialogDescription>
          </AlertDialogHeader>

          {/* Metrics Display - BEFORE decision buttons */}
          {metrics && (
            <div className="py-4">
              <EvaluationMetrics metrics={metrics} />
            </div>
          )}

          {/* Decision Buttons */}
          <div className="py-4 space-y-3">
            <Button
              variant="default"
              className="w-full justify-start h-auto py-4 px-4 text-left"
              onClick={() => onSelect({ type: "proceed_to_deployment" })}
            >
              <div className="flex items-start gap-3 w-full">
                <Rocket className="h-5 w-5 mt-0.5 flex-shrink-0" />
                <span className="font-medium">Proceed to Full Training & Deployment</span>
              </div>
            </Button>
            <Button
              variant="outline"
              className="w-full justify-start h-auto py-4 px-4 text-left"
              onClick={() => onSelect({ type: "send_to_improvement" })}
            >
              <div className="flex items-start gap-3 w-full">
                <Sparkles className="h-5 w-5 mt-0.5 flex-shrink-0" />
                <span className="font-medium">Send to Improvement Agent</span>
              </div>
            </Button>
          </div>

          <AlertDialogFooter>
            <AlertDialogCancel onClick={handleCancelClick}>Cancel</AlertDialogCancel>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Cancel Confirmation Dialog */}
      <ConfirmationPopup
        open={showCancelConfirmation}
        title="Warning: Cancel Workflow?"
        message="Cancelling now will stop the analysis and discard results. Are you sure you want to cancel?"
        confirmLabel="Yes, cancel workflow"
        cancelLabel="No, go back"
        onConfirm={handleConfirmCancel}
        onCancel={handleCancelConfirmationCancel}
        variant="destructive"
      />
    </>
  );
};

export const ImprovementSatisfactionDialog: React.FC<{
  open: boolean;
  onSelect: (decision: UserDecision) => void;
  onCancel?: () => void;
  iterationCount: number;
}> = ({ open, onSelect, onCancel, iterationCount }) => {
  const maxIterations = 3;
  const canImproveMore = iterationCount < maxIterations;

  return (
    <IterationDialog
      open={open}
      title="Improvement Complete"
      description={
        iterationCount >= maxIterations
          ? `You've reached the maximum number of improvement iterations (${maxIterations}). Please select an option:`
          : `Are you satisfied with the improved results? (Iteration ${iterationCount}/${maxIterations})`
      }
      options={[
        {
          label: "Yes, Proceed to Full Training & Deployment",
          value: "proceed_to_deployment",
          icon: <Rocket className="h-5 w-5" />,
          variant: "default",
        },
        ...(canImproveMore
          ? [
              {
                label: "Improve Again",
                value: "send_to_improvement" as const,
                icon: <RefreshCw className="h-5 w-5" />,
                variant: "outline" as const,
              },
            ]
          : []),
        {
          label: "Reject & Select Different Model",
          value: "reject_and_reselect",
          icon: <RefreshCw className="h-5 w-5" />,
          variant: "destructive",
        },
      ]}
      onSelect={onSelect}
      onCancel={onCancel}
    />
  );
};

export default IterationDialog;

