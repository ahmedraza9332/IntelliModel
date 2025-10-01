import React, { useEffect, useRef } from "react";

const AboutSection = () => {
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

  return (
    <section 
      ref={sectionRef}
      className="w-full py-16 md:py-24 bg-gradient-to-b from-gray-50 to-white" 
      id="about"
    >
      <div className="section-container">
        <div className="max-w-4xl mx-auto">
          <div className="pulse-chip mx-auto mb-6 opacity-0 fade-in-element inline-block">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-pulse-500 text-white mr-2">02</span>
            <span>About</span>
          </div>
          
          <h2 className="section-title text-center mb-8 opacity-0 fade-in-element">
            Intelligent ML Automation
          </h2>
          
          <div className="prose prose-lg max-w-none opacity-0 fade-in-element">
            <p className="text-lg md:text-xl text-gray-700 leading-relaxed mb-6">
              IntelliModel is an intelligent agent-based system that automates the entire machine learning lifecycle. 
              From dataset ingestion and profiling to preprocessing, feature engineering, and model training, 
              IntelliModel streamlines every step of the ML pipeline.
            </p>
            
            <p className="text-lg md:text-xl text-gray-700 leading-relaxed mb-6">
              Powered by LLM-guided model suggestion and validation, our system performs local training and 
              comprehensive performance metrics visualization. When models underperform, the Improvement Agent 
              automatically applies optimization techniques and retraining strategies.
            </p>
            
            <p className="text-lg md:text-xl text-gray-700 leading-relaxed">
              Once an optimal model is approved, IntelliModel deploys it as a secure API that seamlessly integrates 
              with popular BI tools like Power BI, Tableau, and Superset. A continuous feedback loop ensures 
              sustained performance and adaptability in production environments.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
};

export default AboutSection;
