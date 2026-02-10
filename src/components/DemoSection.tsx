import React, { useEffect, useRef } from "react";
import { Download } from "lucide-react";

const DemoSection = () => {
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

  const downloads = [
    { title: "Profiling Report", description: "Comprehensive dataset analysis", filename: "profiling_report.pdf" },
    { title: "Cleaned Dataset", description: "Feature-engineered data", filename: "cleaned_dataset.csv" },
    { title: "Validation Results", description: "Model performance metrics and analysis", filename: "validation_results.pdf" }
  ];

  return (
    <section 
      ref={sectionRef}
      className="w-full py-16 md:py-24 bg-gradient-to-b from-gray-50 to-white" 
      id="demo"
    >
      <div className="section-container">
        <div className="flex items-center gap-4 mb-12">
          <div className="pulse-chip opacity-0 fade-in-element">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-pulse-500 text-white mr-2">05</span>
            <span>Demo</span>
          </div>
          <div className="flex-1 h-[1px] bg-gray-300"></div>
        </div>

        <h2 className="section-title text-center mb-4 opacity-0 fade-in-element">
          Why IntelliModel
        </h2>
        <div className="max-w-5xl mx-auto">
          {/* Video */}
          <div className="aspect-video w-full bg-gradient-to-br from-gray-800 to-gray-900 rounded-3xl shadow-2xl mb-12 opacity-0 fade-in-element overflow-hidden">
            <iframe
              className="w-full h-full rounded-3xl"
              src="https://www.youtube.com/embed/EZqcT8idaY8?rel=0"
              title="IntelliModel Demo"
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
              allowFullScreen
            />
          </div>

          {/* Download section */}
          <div className="opacity-0 fade-in-element">
            <h3 className="text-2xl font-display font-bold mb-8 text-center">Sample Outputs</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {downloads.map((item, index) => (
                <div 
                  key={index}
                  className="glass-card p-6 hover:shadow-xl transition-all duration-300"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="w-12 h-12 rounded-lg bg-pulse-100 flex items-center justify-center">
                      <Download className="w-6 h-6 text-pulse-500" />
                    </div>
                  </div>
                  <h4 className="text-lg font-semibold text-gray-900 mb-2">{item.title}</h4>
                  <p className="text-gray-600 text-sm mb-4">{item.description}</p>
                  <button 
                    className="w-full py-2 px-4 bg-pulse-500 hover:bg-pulse-600 text-white rounded-lg transition-colors duration-200 text-sm font-medium"
                    onClick={() => {/* Download functionality will be implemented */}}
                  >
                    Download Sample
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default DemoSection;
