import React, { useEffect, useRef } from "react";

const WorkflowSection = () => {
  const sectionRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const elements = entry.target.querySelectorAll(".fade-in-element");
            elements.forEach((el, index) => {
              setTimeout(() => {
                el.classList.add("animate-fade-in");
              }, index * 100);
            });
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1 }
    );

    if (sectionRef.current) {
      observer.observe(sectionRef.current);
    }

    return () => {
      if (sectionRef.current) {
        observer.unobserve(sectionRef.current);
      }
    };
  }, []);

  const stages = [
    { id: 1, name: "Dataset Upload", icon: "📊" },
    { id: 2, name: "Profiling", icon: "🔍" },
    { id: 3, name: "Preprocessing", icon: "🧹" },
    { id: 4, name: "Model Suggestion", icon: "🤖" },
    { id: 5, name: "Training & Validation", icon: "🎯" },
    { id: 6, name: "Improvement Agent", icon: "⚡" },
    { id: 7, name: "User Approval", icon: "✓" },
    { id: 8, name: "Deployment", icon: "🚀" },
    { id: 9, name: "Integration", icon: "🔗" },
    { id: 10, name: "Feedback Loop", icon: "🔄" }
  ];

  return (
    <section 
      ref={sectionRef}
      className="w-full py-16 md:py-24 bg-white" 
      id="workflow"
    >
      <div className="section-container">
        <div className="flex items-center gap-4 mb-12">
          <div className="pulse-chip opacity-0 fade-in-element">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-pulse-500 text-white mr-2">04</span>
            <span>Workflow</span>
          </div>
          <div className="flex-1 h-[1px] bg-gray-300"></div>
        </div>

        <h2 className="section-title mb-4 opacity-0 fade-in-element">
          ML Pipeline Stages
        </h2>
        <p className="section-subtitle mb-16 opacity-0 fade-in-element">
          A comprehensive automated workflow from data ingestion to production deployment
        </p>

        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-5 gap-6 md:gap-8">
            {stages.map((stage, index) => (
              <div 
                key={stage.id}
                className="opacity-0 fade-in-element"
                style={{ animationDelay: `${index * 0.1}s` }}
              >
                <div className="glass-card p-6 text-center hover:shadow-xl transition-all duration-300">
                  <div className="text-4xl mb-4">{stage.icon}</div>
                  <div className="text-xs font-semibold text-pulse-500 mb-2">STAGE {stage.id}</div>
                  <h3 className="text-sm md:text-base font-semibold text-gray-800">{stage.name}</h3>
                </div>
                {index < stages.length - 1 && (
                  <div className="hidden md:flex justify-center items-center mt-4">
                    <svg className="w-6 h-6 text-pulse-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="mt-16 p-8 bg-gradient-to-br from-pulse-50 to-orange-50 rounded-3xl opacity-0 fade-in-element">
            <h3 className="text-2xl font-display font-bold mb-4 text-gray-900">
              Intelligent Automation at Every Stage
            </h3>
            <p className="text-lg text-gray-700 leading-relaxed">
              IntelliModel orchestrates the entire machine learning lifecycle through intelligent agents that handle 
              data profiling, preprocessing, model selection, training, validation, and deployment. The system continuously 
              monitors performance and automatically triggers optimization when needed, ensuring your models stay accurate 
              and relevant in production environments.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default WorkflowSection;
