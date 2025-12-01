/**
 * Pipeline Service - Manages pipeline execution state
 * Can be easily switched from mock to real backend/WebSocket
 */

import {
  PipelineState,
  PipelineMilestone,
  PipelineEvent,
  PipelineStageStatus,
  PIPELINE_MILESTONES,
} from "./pipelineTypes";

export type PipelineEventCallback = (event: PipelineEvent) => void;

class PipelineService {
  private state: PipelineState | null = null;
  private eventCallbacks: PipelineEventCallback[] = [];
  private milestoneTimers: Map<string, NodeJS.Timeout> = new Map();

  /**
   * Initialize a new pipeline
   */
  initializePipeline(pipelineId: string): PipelineState {
    const milestones: PipelineMilestone[] = PIPELINE_MILESTONES.map((m) => ({
      ...m,
      status: "pending",
    }));

    this.state = {
      pipelineId,
      milestones,
      overallProgress: 0,
      currentStage: null,
      status: "idle",
      startedAt: new Date().toISOString(),
    };

    return this.state;
  }

  /**
   * Get current pipeline state
   */
  getState(): PipelineState | null {
    return this.state;
  }

  /**
   * Start the pipeline execution (mock)
   */
  startPipeline(): void {
    if (!this.state) return;

    this.state.status = "running";
    this.emitEvent({
      type: "pipeline_started",
      timestamp: new Date().toISOString(),
    });

    // Mark first milestone (dataset_uploaded) as completed immediately
    // since upload already happened before pipeline starts
    if (this.state.milestones.length > 0 && this.state.milestones[0].id === "dataset_uploaded") {
      this.updateMilestoneStatus("dataset_uploaded", "completed");
    }

    // Start simulating milestones (will skip first one if already completed)
    this.simulateMilestones();
  }

  /**
   * Simulate milestone progression (mock)
   */
  private simulateMilestones(): void {
    if (!this.state) return;

    const milestones = [...this.state.milestones];
    
    // Find first pending milestone (skip already completed ones)
    let currentIndex = milestones.findIndex((m) => m.status === "pending");
    
    if (currentIndex === -1) {
      // All milestones already completed or running
      const allCompleted = milestones.every((m) => m.status === "completed");
      if (allCompleted && this.state) {
        this.state.status = "completed";
        this.state.overallProgress = 100;
      }
      return;
    }

    const processNextMilestone = () => {
      if (currentIndex >= milestones.length) {
        // All milestones complete
        if (this.state) {
          this.state.status = "completed";
          this.state.completedAt = new Date().toISOString();
          this.state.overallProgress = 100;
        }
        this.emitEvent({
          type: "pipeline_completed",
          timestamp: new Date().toISOString(),
        });
        return;
      }

      const milestone = milestones[currentIndex];
      
      // Skip if already completed
      if (milestone.status === "completed") {
        currentIndex++;
        setTimeout(processNextMilestone, 100);
        return;
      }
      
      // Mark as running
      this.updateMilestoneStatus(milestone.id, "running");
      
      // Determine delay based on milestone type
      const delay = this.getMilestoneDelay(milestone.id);
      
      // After delay, mark as completed
      const timer = setTimeout(() => {
        this.updateMilestoneStatus(milestone.id, "completed");
        this.updateProgress();
        
        // Process next milestone after a short delay
        currentIndex++;
        setTimeout(processNextMilestone, 500);
        
        this.milestoneTimers.delete(milestone.id);
      }, delay);
      
      this.milestoneTimers.set(milestone.id, timer);
    };

    // Start processing first milestone
    processNextMilestone();
  }

  /**
   * Get delay for milestone (in milliseconds)
   */
  private getMilestoneDelay(milestoneId: string): number {
    const delays: Record<string, number> = {
      dataset_uploaded: 1000,
      schema_profiling: 2000,
      preprocessing_complete: 2500,
      model_suggestions_ready: 3000,
      code_generation: 2000,
      training_in_progress: 8000, // Longer for training
      metrics_returned: 1000,
      improvement_iteration: 3000,
      final_model_trained: 5000,
      model_deployed: 2000,
    };

    return delays[milestoneId] || 2000;
  }

  /**
   * Update milestone status
   */
  updateMilestoneStatus(
    milestoneId: string,
    status: PipelineStageStatus
  ): void {
    if (!this.state) return;

    const milestone = this.state.milestones.find((m) => m.id === milestoneId);
    if (!milestone) return;

    milestone.status = status;
    
    if (status === "running") {
      milestone.startedAt = new Date().toISOString();
      this.state.currentStage = milestoneId;
      this.emitEvent({
        type: "milestone_started",
        milestoneId,
        timestamp: new Date().toISOString(),
      });
    } else if (status === "completed") {
      milestone.completedAt = new Date().toISOString();
      this.state.currentStage = null;
      this.updateProgress(); // Update overall progress
      this.emitEvent({
        type: "milestone_completed",
        milestoneId,
        timestamp: new Date().toISOString(),
      });
    } else if (status === "failed") {
      this.emitEvent({
        type: "milestone_failed",
        milestoneId,
        timestamp: new Date().toISOString(),
      });
    }
  }

  /**
   * Update overall progress
   */
  private updateProgress(): void {
    if (!this.state) return;

    const completedCount = this.state.milestones.filter(
      (m) => m.status === "completed"
    ).length;
    const totalCount = this.state.milestones.length;
    
    this.state.overallProgress = Math.round((completedCount / totalCount) * 100);
  }

  /**
   * Subscribe to pipeline events
   */
  onEvent(callback: PipelineEventCallback): () => void {
    this.eventCallbacks.push(callback);
    
    // Return unsubscribe function
    return () => {
      this.eventCallbacks = this.eventCallbacks.filter((cb) => cb !== callback);
    };
  }

  /**
   * Emit event to all subscribers
   */
  private emitEvent(event: PipelineEvent): void {
    this.eventCallbacks.forEach((callback) => callback(event));
  }

  /**
   * Stop pipeline execution
   */
  stopPipeline(): void {
    // Clear all timers
    this.milestoneTimers.forEach((timer) => clearTimeout(timer));
    this.milestoneTimers.clear();

    if (this.state) {
      this.state.status = "idle";
    }
  }

  /**
   * Reset pipeline
   */
  reset(): void {
    this.stopPipeline();
    this.state = null;
  }

  /**
   * Get milestone by ID
   */
  getMilestone(milestoneId: string): PipelineMilestone | undefined {
    return this.state?.milestones.find((m) => m.id === milestoneId);
  }
}

// Singleton instance
export const pipelineService = new PipelineService();

// For future WebSocket integration:
// export const connectPipelineWebSocket = (url: string, pipelineId: string) => {
//   const ws = new WebSocket(`${url}/pipeline/${pipelineId}`);
//   ws.onmessage = (event) => {
//     const pipelineEvent: PipelineEvent = JSON.parse(event.data);
//     pipelineService.handleEvent(pipelineEvent);
//   };
// };

