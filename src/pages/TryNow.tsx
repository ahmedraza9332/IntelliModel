import React, { useRef, useState } from "react";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";
import { cn } from "@/lib/utils";
import {
  UploadCloud,
  ShieldCheck,
  Workflow,
  Sparkles,
  LineChart,
  RefreshCw,
  Settings2,
  CheckCircle2
} from "lucide-react";

const acceptedFileTypes = ".csv,.xlsx,.xls";

const pipelineHighlights = [
  {
    title: "Data Processing Agent",
    description:
      "Automatically profiles your dataset, cleans missing values, encodes categories, and engineers new features for optimal performance.",
    icon: Workflow
  },
  {
    title: "AI Orchestration Agent",
    description:
      "Selects the most promising ML models, generates tailored training code, and executes it locally to keep your data private.",
    icon: Sparkles
  },
  {
    title: "Improvement Agent",
    description:
      "Tunes hyperparameters, runs cross-validation, and iterates until the best-performing model is ready for deployment.",
    icon: Settings2
  }
];

const assurancePoints = [
  "Your data never leaves your workspace—everything runs locally.",
  "Automated validation ensures data integrity before training begins.",
  "You review every model report before deployment to production.",
  "Each finalized model is stored with metadata and version history."
];

const TryNow = () => {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [activeDrag, setActiveDrag] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
  };

  const isSupportedFile = (file: File) => {
    const extension = file.name.split(".").pop()?.toLowerCase();
    return extension ? ["csv", "xlsx", "xls"].includes(extension) : false;
  };

  const handleFileSelect = (files: FileList | null) => {
    if (!files || files.length === 0) {
      return;
    }

    const file = files[0];

    if (!isSupportedFile(file)) {
      setSelectedFile(null);
      setUploadError("Unsupported file type. Please upload a CSV or Excel file.");
      return;
    }

    setUploadError(null);
    setSelectedFile(file);
  };

  const triggerFileDialog = () => {
    fileInputRef.current?.click();
  };

  const handleDragEvents = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();

    if (event.type === "dragenter" || event.type === "dragover") {
      setActiveDrag(true);
    } else if (event.type === "dragleave") {
      setActiveDrag(false);
    }
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setActiveDrag(false);

    const files = event.dataTransfer?.files;
    handleFileSelect(files ?? null);
  };

  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <Navbar />
      <main className="flex-1">
        <section className="relative overflow-hidden bg-gradient-to-b from-white via-white/90 to-slate-100 pt-32 pb-24">
          <div className="pointer-events-none absolute inset-0 -z-10">
            <img
              src="/background-section2.png"
              alt=""
              className="absolute right-0 top-0 hidden h-full w-auto opacity-50 lg:block"
              loading="lazy"
            />
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,#fde5c7,transparent_55%)] opacity-80" />
          </div>

          <div className="container relative z-10 px-4 sm:px-6 lg:px-8">
            <div className="grid gap-12 lg:grid-cols-[1.05fr_1fr] lg:items-center">
              <div className="space-y-8 text-center lg:text-left">
                <span className="inline-flex items-center rounded-full bg-pulse-100 px-4 py-1 text-sm font-medium text-pulse-600 shadow-sm">
                  Upload your data · Launch intelligent models
                </span>
                <h1 className="text-4xl font-bold tracking-tight text-gray-900 md:text-5xl">
                  Transform datasets into production-ready intelligence
                </h1>
                <p className="mx-auto max-w-xl text-lg text-gray-600 lg:mx-0">
                  IntelliModel orchestrates your entire machine learning lifecycle.
                  Upload a CSV or Excel file and let our agents profile, train, and
                  deploy the best model while keeping you in full control.
                </p>
                <div className="grid gap-4 rounded-2xl border border-white/80 bg-white/80 p-6 shadow-elegant backdrop-blur">
                  <div
                    className={cn(
                      "relative flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-10 transition-all duration-300",
                      activeDrag
                        ? "border-pulse-500 bg-pulse-50 shadow-lg"
                        : "border-slate-200 bg-white shadow-sm hover:border-pulse-300 hover:shadow-md"
                    )}
                    onDragEnter={handleDragEvents}
                    onDragOver={handleDragEvents}
                    onDragLeave={handleDragEvents}
                    onDrop={handleDrop}
                  >
                    <UploadCloud className="mb-4 h-12 w-12 text-pulse-500" />
                    <p className="text-lg font-semibold text-gray-900">
                      Drag & drop your dataset here
                    </p>
                    <p className="mt-2 text-sm text-gray-500">
                      or
                      <button
                        type="button"
                        className="ml-2 font-medium text-pulse-600 hover:text-pulse-500 focus:outline-none"
                        onClick={triggerFileDialog}
                      >
                        browse files
                      </button>
                    </p>
                    <p className="mt-4 text-xs uppercase tracking-[0.2em] text-gray-400">
                      Supported formats: CSV, XLSX
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept={acceptedFileTypes}
                      className="hidden"
                      onChange={(event) => handleFileSelect(event.target.files)}
                    />
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm">
                      <div className="flex items-center gap-3">
                        <ShieldCheck className="h-6 w-6 text-green-500" />
                        <div>
                          <p className="text-sm font-semibold text-gray-900">
                            Private by design
                          </p>
                          <p className="text-xs text-gray-500">
                            Processing runs on your machine — never in the cloud.
                          </p>
                        </div>
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm">
                      <div className="flex items-center gap-3">
                        <LineChart className="h-6 w-6 text-pulse-500" />
                        <div>
                          <p className="text-sm font-semibold text-gray-900">
                            Deployable APIs in minutes
                          </p>
                          <p className="text-xs text-gray-500">
                            Best model is packaged with full metadata & endpoints.
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                  {uploadError && (
                    <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-left text-sm text-red-600">
                      {uploadError}
                    </div>
                  )}
                  {selectedFile && !uploadError && (
                    <div className="rounded-xl border border-slate-200 bg-white p-5 text-left shadow-sm">
                      <div className="flex flex-wrap items-center justify-between gap-4">
                        <div>
                          <p className="text-sm font-semibold text-gray-900">
                            {selectedFile.name}
                          </p>
                          <p className="text-xs text-gray-500">
                            {formatFileSize(selectedFile.size)} · Ready for validation
                          </p>
                        </div>
                        <button
                          type="button"
                          className="inline-flex items-center rounded-full bg-pulse-500 px-5 py-2 text-sm font-medium text-white shadow-md transition-all duration-200 hover:bg-pulse-600 focus:outline-none focus:ring-2 focus:ring-pulse-300"
                        >
                          Process dataset
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="relative mx-auto w-full max-w-md">
                <div className="absolute -top-16 -right-10 hidden h-56 w-56 rounded-full bg-orange-200/40 blur-3xl lg:block" />
                <div className="glass-card relative overflow-hidden rounded-3xl border border-white/20 bg-white/80 p-6 shadow-elegant">
                  <div className="absolute -right-24 -top-24 h-48 w-48 rounded-full bg-pulse-200/50 blur-3xl" />
                  <img
                    src="/hero-image.jpg"
                    alt="Workflow preview"
                    className="relative z-10 rounded-2xl object-cover shadow-lg"
                  />
                  <div className="relative z-10 mt-6 space-y-4">
                    <div className="flex items-center gap-3 rounded-2xl bg-white/90 p-4 shadow-inner">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-pulse-100 text-pulse-600">
                        <RefreshCw className="h-5 w-5" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">
                          Continuous retraining
                        </p>
                        <p className="text-xs text-gray-500">
                          Monitor drift, auto-trigger improvement agent, and deploy updates safely.
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 rounded-2xl bg-white/90 p-4 shadow-inner">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                        <ShieldCheck className="h-5 w-5" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-gray-900">
                          Audit-ready reports
                        </p>
                        <p className="text-xs text-gray-500">
                          Every experiment logged with metrics, lineage, and governance checks.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="relative py-24">
          <div className="absolute inset-0 -z-10 bg-gradient-to-b from-white via-slate-50 to-white" />
          <div className="container px-4 sm:px-6 lg:px-8">
            <div className="mx-auto max-w-3xl text-center">
              <h2 className="section-title">Three agents working in harmony</h2>
              <p className="section-subtitle">
                IntelliModel choreographs specialized agents to transform raw datasets
                into deployable intelligence. Sit back while each step is handled with
                transparency and human oversight.
              </p>
            </div>
            <div className="mt-16 grid gap-8 lg:grid-cols-3">
              {pipelineHighlights.map(({ title, description, icon: Icon }) => (
                <div
                  key={title}
                  className="feature-card glass-card h-full p-8 text-left"
                >
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-pulse-100 text-pulse-600">
                    <Icon className="h-6 w-6" />
                  </div>
                  <h3 className="mt-6 text-xl font-semibold text-gray-900">
                    {title}
                  </h3>
                  <p className="mt-4 text-sm text-gray-600">
                    {description}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="relative overflow-hidden py-24">
          <div className="absolute inset-0 -z-10">
            <img
              src="/background-section3.png"
              alt=""
              className="h-full w-full object-cover opacity-60"
              loading="lazy"
            />
            <div className="absolute inset-0 bg-gradient-to-r from-white via-white/90 to-white/70" />
          </div>
          <div className="container relative z-10 px-4 sm:px-6 lg:px-8">
            <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
              <div className="space-y-6">
                <h2 className="section-title">
                  What happens after you upload your dataset?
                </h2>
                <div className="space-y-4">
                  <div className="rounded-2xl border border-white/70 bg-white/80 p-6 shadow-elegant">
                    <h3 className="text-lg font-semibold text-gray-900">
                      Step-by-step orchestration
                    </h3>
                    <ul className="mt-4 space-y-3 text-sm text-gray-600">
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-emerald-500" />
                        Dataset validation, schema detection, and intelligent profile summary.
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-emerald-500" />
                        Automated model selection with cross-validation and explainability reports.
                      </li>
                      <li className="flex items-start gap-3">
                        <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-emerald-500" />
                        Human approval gate before retraining the winning model for production.
                      </li>
                    </ul>
                  </div>
                  <div className="rounded-2xl border border-white/70 bg-white/80 p-6 shadow-elegant">
                    <h3 className="text-lg font-semibold text-gray-900">
                      Governance & deployment
                    </h3>
                    <p className="mt-4 text-sm text-gray-600">
                      Once approved, IntelliModel retrains with your latest dataset, packages
                      the model with metadata, and exposes a secure REST API ready to plug into
                      BI dashboards like Power BI or Tableau. Continuous monitoring ensures your
                      models stay performant.
                    </p>
                  </div>
                </div>
              </div>
              <div className="glass-card relative rounded-3xl border border-white/20 bg-white/80 p-8 shadow-elegant">
                <h3 className="text-lg font-semibold text-gray-900">
                  Built-in safeguards you can trust
                </h3>
                <ul className="mt-6 space-y-4 text-sm text-gray-600">
                  {assurancePoints.map((point) => (
                    <li key={point} className="flex items-start gap-3">
                      <ShieldCheck className="mt-0.5 h-5 w-5 flex-shrink-0 text-pulse-500" />
                      {point}
                    </li>
                  ))}
                </ul>
                <div className="mt-8 flex flex-col gap-4 rounded-2xl bg-white/90 p-6 shadow-inner">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-pulse-100 text-pulse-600">
                      <LineChart className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-900">
                        Monitoring made effortless
                      </p>
                      <p className="text-xs text-gray-500">
                        Drift detection and alerting keep your stakeholders informed in real time.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-emerald-600">
                      <RefreshCw className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-900">
                        Continuous improvement loop
                      </p>
                      <p className="text-xs text-gray-500">
                        Automated retraining ensures your deployed models stay accurate and reliable.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
};

export default TryNow;

