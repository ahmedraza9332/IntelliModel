
import React, { useEffect } from "react";
import { useLocation } from "react-router-dom";
import Navbar from "@/components/Navbar";
import Hero from "@/components/Hero";
import AboutSection from "@/components/AboutSection";
import Features from "@/components/Features";
import WorkflowSection from "@/components/WorkflowSection";
import DemoSection from "@/components/DemoSection";
import Newsletter from "@/components/Newsletter";
import Footer from "@/components/Footer";

const Index = () => {
  const location = useLocation();
  // Initialize intersection observer to detect when elements enter viewport
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("animate-fade-in");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1 }
    );
    
    const elements = document.querySelectorAll(".animate-on-scroll");
    elements.forEach((el) => observer.observe(el));
    
    return () => {
      elements.forEach((el) => observer.unobserve(el));
    };
  }, []);

  useEffect(() => {
    // This helps ensure smooth scrolling for the anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
      anchor.addEventListener('click', function (e) {
        e.preventDefault();
        
        const targetId = this.getAttribute('href')?.substring(1);
        if (!targetId) return;
        
        const targetElement = document.getElementById(targetId);
        if (!targetElement) return;
        
        // Increased offset to account for mobile nav
        const offset = window.innerWidth < 768 ? 100 : 80;
        
        window.scrollTo({
          top: targetElement.offsetTop - offset,
          behavior: 'smooth'
        });
      });
    });
  }, []);

  useEffect(() => {
    if (!location.hash) {
      return;
    }

    const handleHashNavigation = () => {
      const targetElement = document.querySelector(location.hash);
      if (!targetElement) {
        return;
      }

      const offset = window.innerWidth < 768 ? 100 : 80;
      const elementPosition =
        (targetElement as HTMLElement).getBoundingClientRect().top +
        window.scrollY -
        offset;

      window.scrollTo({
        top: elementPosition,
        behavior: "smooth"
      });
    };

    const timeout = window.setTimeout(handleHashNavigation, 150);

    return () => window.clearTimeout(timeout);
  }, [location]);

  return (
    <div className="min-h-screen">
      <Navbar />
      <main className="space-y-4 sm:space-y-8">
        <Hero />
        <AboutSection />
        <Features />
        <WorkflowSection />
        <DemoSection />
        <Newsletter />
      </main>
      <Footer />
    </div>
  );
};

export default Index;
