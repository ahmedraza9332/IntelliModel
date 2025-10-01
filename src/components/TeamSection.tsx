import React, { useEffect, useRef } from "react";

const TeamSection = () => {
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

  const teamMembers = [
    {
      name: "Team Member 1",
      role: "Project Lead & ML Engineer",
      image: "/lovable-uploads/22d31f51-c174-40a7-bd95-00e4ad00eaf3.png"
    },
    {
      name: "Team Member 2",
      role: "Backend Developer",
      image: "/lovable-uploads/5663820f-6c97-4492-9210-9eaa1a8dc415.png"
    },
    {
      name: "Team Member 3",
      role: "Frontend Developer",
      image: "/lovable-uploads/af412c03-21e4-4856-82ff-d1a975dc84a9.png"
    },
    {
      name: "Team Member 4",
      role: "Data Scientist",
      image: "/lovable-uploads/c3d5522b-6886-4b75-8ffc-d020016bb9c2.png"
    }
  ];

  return (
    <section 
      ref={sectionRef}
      className="w-full py-16 md:py-24 bg-white" 
      id="team"
    >
      <div className="section-container">
        <div className="text-center mb-16">
          <div className="pulse-chip mx-auto mb-6 opacity-0 fade-in-element inline-block">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-pulse-500 text-white mr-2">06</span>
            <span>Team</span>
          </div>
          
          <h2 className="section-title mb-4 opacity-0 fade-in-element">
            Meet Our Team
          </h2>
          <p className="section-subtitle mx-auto opacity-0 fade-in-element">
            The minds behind IntelliModel's intelligent automation
          </p>
        </div>

        <div className="max-w-6xl mx-auto">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
            {teamMembers.map((member, index) => (
              <div 
                key={index}
                className="opacity-0 fade-in-element"
                style={{ animationDelay: `${index * 0.1}s` }}
              >
                <div className="glass-card p-6 text-center hover:shadow-xl transition-all duration-300 group">
                  <div className="mb-6 overflow-hidden rounded-2xl">
                    <img 
                      src={member.image} 
                      alt={member.name}
                      className="w-full h-64 object-cover transition-transform duration-500 group-hover:scale-110"
                    />
                  </div>
                  <h3 className="text-xl font-semibold text-gray-900 mb-2">{member.name}</h3>
                  <p className="text-pulse-500 font-medium text-sm">{member.role}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default TeamSection;
