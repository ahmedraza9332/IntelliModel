import React, { useCallback, useRef, useState } from "react";
import { Upload, FileText, X, AlertCircle, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { uploadDataset } from "@/api/client";

export interface UploadInfo {
  filename: string;
  targetColumn: string;
  goal: string;
}

interface UploadStepProps {
  onSuccess: (jobId: string, info: UploadInfo) => void;
}

const ACCEPTED_TYPES = ["text/csv", "application/vnd.ms-excel"];
const ACCEPTED_EXT = [".csv"];

function isAcceptedFile(file: File): boolean {
  const extOk = ACCEPTED_EXT.some((ext) =>
    file.name.toLowerCase().endsWith(ext)
  );
  const mimeOk = ACCEPTED_TYPES.includes(file.type) || file.type === "";
  return extOk || mimeOk;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function UploadStep({ onSuccess }: UploadStepProps) {
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [targetColumn, setTargetColumn] = useState("");
  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const acceptFile = useCallback((candidate: File) => {
    if (!isAcceptedFile(candidate)) {
      setError(`"${candidate.name}" is not a CSV file.`);
      return;
    }
    setFile(candidate);
    setError(null);
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const picked = e.target.files?.[0];
    if (picked) acceptFile(picked);
    e.target.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) acceptFile(dropped);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => setDragOver(false);

  const removeFile = (e: React.MouseEvent) => {
    e.stopPropagation();
    setFile(null);
    setError(null);
  };

  const canSubmit =
    file !== null &&
    targetColumn.trim().length > 0 &&
    goal.trim().length > 0 &&
    !loading;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setError(null);
    setLoading(true);
    try {
      const res = await uploadDataset(file!, targetColumn.trim(), goal.trim());
      onSuccess(res.job_id, {
        filename: file!.name,
        targetColumn: targetColumn.trim(),
        goal: goal.trim(),
      });
    } catch (err) {
      const raw = err instanceof Error ? err.message : "Upload failed.";
      const friendly =
        raw === "Failed to fetch"
          ? "Cannot reach the backend (http://localhost:9000). " +
            "Make sure api_server.py is running: open a terminal in the backend folder and run  python api_server.py"
          : raw;
      setError(friendly);
      setLoading(false);
    }
  };

  return (
    <div className="pipeline-enter w-full max-w-2xl mx-auto">
      {/* Step badge */}
      <div className="pipeline-enter pipeline-enter-delay-1 flex items-center gap-3 mb-6">
        <span className="step-chip">
          <Sparkles size={11} />
          Step 1 of 6 — Upload Dataset
        </span>
      </div>

      {/* Heading */}
      <div className="pipeline-enter pipeline-enter-delay-1 mb-8">
        <h1 className="text-4xl md:text-5xl font-display font-bold text-slate-900 leading-tight">
          Upload your{" "}
          <span className="bg-gradient-to-r from-pulse-500 to-orange-500 bg-clip-text text-transparent">
            dataset
          </span>
        </h1>
        <p className="mt-3 text-slate-500 text-lg">
          IntelliModel will analyse, preprocess, and train the best ML model
          for your data — fully automated.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* ── Dropzone ── */}
        <div className="pipeline-enter pipeline-enter-delay-2">
          <label className="block text-sm font-medium text-slate-700 mb-2">
            CSV File <span className="text-pulse-500">*</span>
          </label>

          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleFileChange}
          />

          {file ? (
            <div
              className={cn(
                "flex items-center gap-4 p-4 rounded-2xl",
                "bg-pulse-500/[0.07] border border-pulse-500/30"
              )}
            >
              <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-pulse-500/15 flex items-center justify-center">
                <FileText size={20} className="text-pulse-600" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-slate-900 font-medium text-sm truncate">
                  {file.name}
                </p>
                <p className="text-slate-400 text-xs mt-0.5">
                  {formatBytes(file.size)}
                </p>
              </div>
              <button
                type="button"
                onClick={removeFile}
                className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 flex items-center justify-center text-slate-400 hover:text-slate-700 transition-colors"
                aria-label="Remove file"
              >
                <X size={14} />
              </button>
            </div>
          ) : (
            <div
              role="button"
              tabIndex={0}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) =>
                e.key === "Enter" && fileInputRef.current?.click()
              }
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              className={cn("dropzone group", dragOver && "drag-over")}
              aria-label="File upload area"
            >
              <div
                className={cn(
                  "absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300",
                  "bg-[radial-gradient(ellipse_at_center,rgba(249,115,22,0.05)_0%,transparent_70%)]"
                )}
              />
              <div className="relative flex flex-col items-center gap-3 py-6 px-4 text-center pointer-events-none">
                <div
                  className={cn(
                    "w-14 h-14 rounded-2xl flex items-center justify-center transition-colors duration-200",
                    dragOver
                      ? "bg-pulse-500/20 text-pulse-600"
                      : "bg-slate-200 text-slate-400 group-hover:bg-pulse-500/15 group-hover:text-pulse-600"
                  )}
                >
                  <Upload size={26} />
                </div>
                <div>
                  <p className="text-slate-800 font-medium text-sm">
                    {dragOver ? "Drop it here" : "Drop your CSV file here"}
                  </p>
                  <p className="text-slate-400 text-xs mt-1">
                    or{" "}
                    <span className="text-pulse-600 underline underline-offset-2">
                      click to browse
                    </span>
                  </p>
                </div>
                <p className="text-slate-400 text-xs">Supports: .csv</p>
              </div>
            </div>
          )}
        </div>

        {/* ── Target column ── */}
        <div className="pipeline-enter pipeline-enter-delay-2">
          <label
            htmlFor="target-column"
            className="block text-sm font-medium text-slate-700 mb-2"
          >
            Target Column <span className="text-pulse-500">*</span>
          </label>
          <input
            id="target-column"
            type="text"
            className="pipeline-input"
            placeholder="e.g. price, churn, diagnosis"
            value={targetColumn}
            onChange={(e) => setTargetColumn(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          <p className="mt-1.5 text-xs text-slate-400">
            The column your model should predict.
          </p>
        </div>

        {/* ── Goal ── */}
        <div className="pipeline-enter pipeline-enter-delay-3">
          <label
            htmlFor="goal"
            className="block text-sm font-medium text-slate-700 mb-2"
          >
            Dataset Goal <span className="text-pulse-500">*</span>
          </label>
          <textarea
            id="goal"
            rows={3}
            className="pipeline-input resize-none"
            placeholder="e.g. Predict house sale prices based on property features for the Seattle real estate market."
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
          <p className="mt-1.5 text-xs text-slate-400">
            Used by the AI to tailor model recommendations and improvement strategies.
          </p>
        </div>

        {/* ── Error banner ── */}
        {error && (
          <div className="flex items-start gap-3 px-4 py-3 rounded-xl bg-red-50 border border-red-200 text-red-600 text-sm">
            <AlertCircle size={16} className="mt-0.5 flex-shrink-0 text-red-500" />
            <span>{error}</span>
          </div>
        )}

        {/* ── Submit ── */}
        <div className="pipeline-enter pipeline-enter-delay-3 pt-2">
          <button
            type="submit"
            disabled={!canSubmit}
            className="pipeline-btn-primary w-full"
          >
            {loading ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                Uploading…
              </>
            ) : (
              <>
                <Upload size={18} />
                Start Pipeline
              </>
            )}
          </button>

          {(!file || !targetColumn.trim() || !goal.trim()) && !loading && (
            <p className="mt-2.5 text-center text-xs text-slate-400">
              {!file
                ? "Upload a CSV file to continue"
                : !targetColumn.trim()
                ? "Enter the target column name"
                : "Describe your dataset goal"}
            </p>
          )}
        </div>
      </form>
    </div>
  );
}
