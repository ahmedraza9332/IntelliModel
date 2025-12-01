import { useState, useEffect, useCallback, useRef } from "react";
import { pipelineService } from "@/api/pipelineService";
import type { PipelineState, PipelineEvent, PipelineMilestone } from "@/api/pipelineTypes";

export const usePipeline = (pipelineId: string | null) => {
  const [state, setState] = useState<PipelineState | null>(null);
  const initializedRef = useRef<string | null>(null);

  // Initialize pipeline
  useEffect(() => {
    if (!pipelineId || initializedRef.current === pipelineId) return;

    // Reset if pipeline ID changed
    if (initializedRef.current && initializedRef.current !== pipelineId) {
      pipelineService.reset();
    }

    const initialState = pipelineService.initializePipeline(pipelineId);
    setState(initialState);
    initializedRef.current = pipelineId;

    // Subscribe to pipeline events
    const unsubscribe = pipelineService.onEvent((event: PipelineEvent) => {
      // Refresh state when event occurs
      const newState = pipelineService.getState();
      if (newState) {
        setState({ ...newState });
      }
    });

    return () => {
      unsubscribe();
      // Only reset if this was the active pipeline
      if (initializedRef.current === pipelineId) {
        pipelineService.reset();
        initializedRef.current = null;
      }
    };
  }, [pipelineId]);

  // Start pipeline
  const startPipeline = useCallback(() => {
    pipelineService.startPipeline();
  }, []);

  // Stop pipeline
  const stopPipeline = useCallback(() => {
    pipelineService.stopPipeline();
  }, []);

  // Reset pipeline
  const resetPipeline = useCallback(() => {
    pipelineService.reset();
    setState(null);
    initializedRef.current = null;
  }, []);

  // Get milestone by ID
  const getMilestone = useCallback((milestoneId: string): PipelineMilestone | undefined => {
    return pipelineService.getMilestone(milestoneId);
  }, []);

  return {
    state,
    startPipeline,
    stopPipeline,
    resetPipeline,
    getMilestone,
    isInitialized: initializedRef.current !== null,
  };
};

