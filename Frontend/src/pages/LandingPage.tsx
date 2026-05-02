import { Link } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  Database,
  Brain,
  LineChart,
  Server,
} from "lucide-react";
import Navbar from "@/components/landing/Navbar";

// ─── Static data ─────────────────────────────────────────────────────────────

const FEATURES = [
  {
    icon: Database,
    title: "Smart Preprocessing",
    description:
      "AI agents automatically clean, transform, and engineer features from your data — handling missing values, outliers, and skewed distributions.",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/20",
  },
  {
    icon: Brain,
    title: "Model Intelligence",
    description:
      "An LLM agent benchmarks multiple algorithms and recommends the best match for your data and business goal using contextual reasoning.",
    color: "text-pulse-400",
    bg: "bg-pulse-500/10",
    border: "border-pulse-500/20",
  },
  {
    icon: LineChart,
    title: "Self-Improvement",
    description:
      "After training, an improvement agent iteratively refines the model through hyperparameter tuning and intelligent code rewriting.",
    color: "text-purple-400",
    bg: "bg-purple-500/10",
    border: "border-purple-500/20",
  },
  {
    icon: Server,
    title: "Instant Deployment",
    description:
      "Generates and serves a live FastAPI prediction endpoint — ready to integrate into any application immediately.",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/20",
  },
];

const WORKFLOW_STEPS = [
  {
    step: "01",
    title: "Upload Dataset",
    desc: "Drop a CSV file, specify the target column, and describe your prediction goal in plain English.",
  },
  {
    step: "02",
    title: "AI Preprocessing",
    desc: "The preprocessing agent profiles, cleans, and engineers features from your data automatically — no code needed.",
  },
  {
    step: "03",
    title: "Model Selection",
    desc: "An LLM agent analyses your dataset and recommends the most suitable ML algorithms with reasoning.",
  },
  {
    step: "04",
    title: "Validation",
    desc: "Selected models are evaluated with cross-validation metrics (MAE, MSE, R²) so you can make an informed choice.",
  },
  {
    step: "05",
    title: "Full Training",
    desc: "The chosen model is fully trained with production-ready, reproducible code generated on the fly.",
  },
  {
    step: "06",
    title: "Deploy & Predict",
    desc: "A live prediction endpoint is provisioned instantly — send a JSON payload and get back a prediction.",
  },
];

// ─── Scroll helper ────────────────────────────────────────────────────────────

function scrollTo(hash: string) {
  document.querySelector(hash)?.scrollIntoView({ behavior: "smooth" });
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#0a0a0a] text-white overflow-x-hidden">
      <Navbar />

      {/* ═══════════════════════════════════════════════════════════════════
          HERO
      ═══════════════════════════════════════════════════════════════════ */}
      <section
        id="hero"
        className="relative min-h-screen flex items-center justify-center overflow-hidden"
      >
        {/* Background image */}
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: "url('/Header-background.webp')",
            backgroundSize: "cover",
            backgroundPosition: "center top",
            opacity: 0.22,
          }}
        />
        {/* Gradient fade to black at bottom */}
        <div className="absolute inset-0 bg-gradient-to-b from-[#0a0a0a]/50 via-transparent to-[#0a0a0a]" />
        {/* Orange ambient glow — top right */}
        <div
          className="absolute top-0 right-0 w-[700px] h-[700px] pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse at top right, rgba(249,115,22,0.2) 0%, transparent 65%)",
          }}
        />
        {/* Purple ambient glow — bottom left */}
        <div
          className="absolute bottom-0 left-0 w-[500px] h-[500px] pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse at bottom left, rgba(168,85,247,0.12) 0%, transparent 65%)",
          }}
        />
        {/* Dot grid */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage:
              "radial-gradient(rgba(255,255,255,0.035) 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }}
        />

        {/* Content */}
        <div className="relative z-10 text-center px-4 sm:px-6 max-w-5xl mx-auto pt-28 pb-20">
          {/* Logo */}
          <div className="flex justify-center mb-8 animate-fade-in">
            <img
              src="/intellimodel-logo.png"
              alt="IntelliModel"
              className="h-16 w-auto opacity-90"
            />
          </div>

          {/* Chip badge */}
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-pulse-500/10 border border-pulse-500/25 text-pulse-400 text-xs font-semibold tracking-wide mb-8 animate-fade-in">
            <span className="w-1.5 h-1.5 rounded-full bg-pulse-400 animate-pulse" />
            Automated ML Pipeline · Powered by Multi-Agent AI
          </div>

          {/* Heading */}
          <h1 className="text-5xl sm:text-6xl md:text-7xl font-display font-bold leading-[1.06] tracking-tight mb-6 animate-fade-in">
            From dataset to{" "}
            <span className="bg-gradient-to-r from-pulse-400 via-orange-400 to-pulse-300 bg-clip-text text-transparent">
              deployed model
            </span>
            ,<br />
            <span className="text-white/75">automatically.</span>
          </h1>

          {/* Subtitle */}
          <p className="text-lg md:text-xl text-gray-400 max-w-2xl mx-auto leading-relaxed mb-10 animate-fade-in">
            IntelliModel uses collaborative AI agents to handle every stage of
            your ML workflow — preprocessing, model selection, training, and
            deployment — without writing a single line of code.
          </p>

          {/* CTA buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16 animate-fade-in">
            <Link
              to="/try-now"
              className="inline-flex items-center gap-2.5 px-8 py-4 rounded-full
                         bg-pulse-500 hover:bg-pulse-600
                         text-white font-semibold text-lg
                         shadow-[0_0_40px_rgba(249,115,22,0.45)] hover:shadow-[0_0_60px_rgba(249,115,22,0.65)]
                         transition-all duration-300 group"
            >
              Try Now
              <ArrowRight
                size={20}
                className="group-hover:translate-x-1 transition-transform"
              />
            </Link>
            <button
              type="button"
              onClick={() => scrollTo("#workflow")}
              className="inline-flex items-center gap-2 px-6 py-4 rounded-full
                         border border-white/[0.12] text-gray-400 hover:text-white hover:border-white/25
                         font-medium text-base transition-all duration-200"
            >
              See how it works
            </button>
          </div>

          {/* Hero image */}
          <div className="relative max-w-2xl mx-auto animate-fade-in">
            <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-[#0a0a0a] to-transparent z-10 rounded-b-3xl" />
            <img
              src="/hero-image.jpg"
              alt="IntelliModel pipeline dashboard"
              className="w-full rounded-3xl border border-white/[0.07] shadow-[0_0_100px_rgba(0,0,0,0.8)] opacity-65"
            />
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          ABOUT
      ═══════════════════════════════════════════════════════════════════ */}
      <section id="about" className="relative py-28 px-4 sm:px-6">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: "url('/background-section1.png')",
            backgroundSize: "cover",
            backgroundPosition: "center",
            opacity: 0.04,
          }}
        />
        <div className="relative z-10 max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-14 items-center">
          <div>
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/[0.05] border border-white/[0.1] text-gray-400 text-xs font-semibold uppercase tracking-wider mb-6">
              About IntelliModel
            </div>
            <h2 className="text-4xl md:text-5xl font-display font-bold leading-tight mb-6">
              ML made{" "}
              <span className="bg-gradient-to-r from-pulse-400 to-orange-400 bg-clip-text text-transparent">
                accessible
              </span>{" "}
              to everyone
            </h2>
            <p className="text-gray-400 text-lg leading-relaxed mb-8">
              IntelliModel removes the barrier between raw data and
              production-ready ML models. Instead of months of expert work, it
              takes minutes — guided by a team of specialised AI agents that
              collaborate and reason at every step.
            </p>
            <ul className="space-y-3.5">
              {[
                "No machine learning expertise required",
                "Transparent AI decisions with full reasoning",
                "Production-ready code generated automatically",
                "Iterative improvement loop built in",
              ].map((item) => (
                <li
                  key={item}
                  className="flex items-start gap-3 text-gray-300 text-sm"
                >
                  <CheckCircle2
                    size={16}
                    className="text-pulse-400 flex-shrink-0 mt-0.5"
                  />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-3xl overflow-hidden border border-white/[0.07] bg-white/[0.02]">
            <img
              src="/hero-image.jpg"
              alt="IntelliModel in action"
              className="w-full opacity-75"
            />
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          FEATURES
      ═══════════════════════════════════════════════════════════════════ */}
      <section id="features" className="relative py-28 px-4 sm:px-6">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/[0.05] border border-white/[0.1] text-gray-400 text-xs font-semibold uppercase tracking-wider mb-6">
              Features
            </div>
            <h2 className="text-4xl md:text-5xl font-display font-bold">
              Everything you need,{" "}
              <span className="bg-gradient-to-r from-pulse-400 to-orange-400 bg-clip-text text-transparent">
                nothing you don&rsquo;t
              </span>
            </h2>
            <p className="mt-4 text-gray-400 text-lg max-w-xl mx-auto">
              A complete end-to-end ML automation platform powered by
              multi-agent AI.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            {FEATURES.map(({ icon: Icon, title, description, color, bg, border }) => (
              <div
                key={title}
                className={`rounded-2xl border ${border} ${bg} p-7 hover:scale-[1.015] transition-transform duration-200`}
              >
                <div
                  className={`w-11 h-11 rounded-xl ${bg} border ${border} flex items-center justify-center mb-5`}
                >
                  <Icon size={20} className={color} />
                </div>
                <h3 className="text-white font-semibold text-lg mb-2">
                  {title}
                </h3>
                <p className="text-gray-500 text-sm leading-relaxed">
                  {description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          WORKFLOW
      ═══════════════════════════════════════════════════════════════════ */}
      <section id="workflow" className="relative py-28 px-4 sm:px-6">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: "url('/background-section2.png')",
            backgroundSize: "cover",
            backgroundPosition: "center",
            opacity: 0.04,
          }}
        />
        <div className="relative z-10 max-w-4xl mx-auto">
          <div className="text-center mb-16">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/[0.05] border border-white/[0.1] text-gray-400 text-xs font-semibold uppercase tracking-wider mb-6">
              How It Works
            </div>
            <h2 className="text-4xl md:text-5xl font-display font-bold">
              Six steps.{" "}
              <span className="bg-gradient-to-r from-pulse-400 to-orange-400 bg-clip-text text-transparent">
                Fully automated.
              </span>
            </h2>
          </div>

          <div className="relative">
            {/* Vertical connector line */}
            <div className="absolute left-[21px] top-8 bottom-8 w-px bg-gradient-to-b from-pulse-500/40 via-pulse-500/15 to-transparent hidden sm:block" />

            <div className="space-y-6">
              {WORKFLOW_STEPS.map(({ step, title, desc }) => (
                <div key={step} className="flex items-start gap-6">
                  <div className="flex-shrink-0 w-11 h-11 rounded-full border border-pulse-500/30 bg-pulse-500/10 flex items-center justify-center text-pulse-400 font-display font-bold text-sm z-10">
                    {step}
                  </div>
                  <div className="flex-1 pb-2">
                    <h3 className="text-white font-semibold text-lg mb-1">
                      {title}
                    </h3>
                    <p className="text-gray-500 text-sm leading-relaxed">
                      {desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          DEMO / TRY NOW
      ═══════════════════════════════════════════════════════════════════ */}
      <section id="demo" className="relative py-28 px-4 sm:px-6">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage: "url('/background-section3.png')",
            backgroundSize: "cover",
            backgroundPosition: "center",
            opacity: 0.04,
          }}
        />
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse at center, rgba(249,115,22,0.08) 0%, transparent 65%)",
          }}
        />
        <div className="relative z-10 max-w-3xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/[0.05] border border-white/[0.1] text-gray-400 text-xs font-semibold uppercase tracking-wider mb-6">
            Try Now
          </div>
          <h2 className="text-4xl md:text-5xl font-display font-bold mb-6">
            Ready to turn your{" "}
            <span className="bg-gradient-to-r from-pulse-400 to-orange-400 bg-clip-text text-transparent">
              data into a model?
            </span>
          </h2>
          <p className="text-gray-400 text-lg mb-10 leading-relaxed">
            Upload your CSV, describe your goal, and IntelliModel handles the
            rest. The whole pipeline — preprocessing, training, and deployment —
            takes just a few minutes.
          </p>
          <Link
            to="/try-now"
            className="inline-flex items-center gap-2.5 px-10 py-4 rounded-full
                       bg-pulse-500 hover:bg-pulse-600
                       text-white font-semibold text-xl
                       shadow-[0_0_50px_rgba(249,115,22,0.5)] hover:shadow-[0_0_70px_rgba(249,115,22,0.7)]
                       transition-all duration-300 group"
          >
            Launch Pipeline
            <ArrowRight
              size={22}
              className="group-hover:translate-x-1 transition-transform"
            />
          </Link>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════
          CONTACT / FOOTER
      ═══════════════════════════════════════════════════════════════════ */}
      <footer id="contact" className="py-16 px-4 sm:px-6 border-t border-white/[0.07]">
        <div className="max-w-5xl mx-auto">
          <div className="flex flex-col md:flex-row items-start justify-between gap-10">
            <div>
              <img
                src="/intellimodel-logo.png"
                alt="IntelliModel"
                className="h-10 mb-3 opacity-80"
              />
              <p className="text-gray-600 text-sm max-w-xs leading-relaxed">
                Automated end-to-end ML pipeline powered by multi-agent AI.
              </p>
            </div>
            <div className="flex flex-col sm:flex-row gap-10 text-sm text-gray-500">
              <div>
                <p className="text-gray-400 font-semibold mb-3">Project</p>
                <ul className="space-y-2">
                  <li>
                    <a
                      href="https://github.com/ahmedraza9332/IntelliModel"
                      target="_blank"
                      rel="noreferrer"
                      className="hover:text-pulse-400 transition-colors"
                    >
                      GitHub
                    </a>
                  </li>
                  <li>
                    <Link
                      to="/try-now"
                      className="hover:text-pulse-400 transition-colors"
                    >
                      Try Now
                    </Link>
                  </li>
                </ul>
              </div>
              <div>
                <p className="text-gray-400 font-semibold mb-3">Sections</p>
                <ul className="space-y-2">
                  {[
                    { label: "About", hash: "#about" },
                    { label: "Features", hash: "#features" },
                    { label: "Workflow", hash: "#workflow" },
                  ].map(({ label, hash }) => (
                    <li key={hash}>
                      <button
                        type="button"
                        onClick={() => scrollTo(hash)}
                        className="hover:text-pulse-400 transition-colors"
                      >
                        {label}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
          <div className="mt-10 pt-6 border-t border-white/[0.05] text-center text-gray-700 text-xs">
            © {new Date().getFullYear()} IntelliModel. Built with AI.
          </div>
        </div>
      </footer>
    </div>
  );
}
