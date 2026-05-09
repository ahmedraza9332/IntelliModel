
import React, { useEffect } from "react";
import { useLocation } from "react-router-dom";
import Navbar from "@/components/landing/Navbar";
import Hero from "@/components/landing/Hero";
import AboutSection from "@/components/landing/AboutSection";
import Features from "@/components/landing/Features";
import WorkflowSection from "@/components/landing/WorkflowSection";
import DemoSection from "@/components/landing/DemoSection";
import Newsletter from "@/components/landing/Newsletter";
import Footer from "@/components/landing/Footer";

const LandingPage = () => {
  const location = useLocation();

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
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
      anchor.addEventListener("click", function (this: HTMLAnchorElement, e) {
        e.preventDefault();
        const targetId = this.getAttribute("href")?.substring(1);
        if (!targetId) return;
        const targetElement = document.getElementById(targetId);
        if (!targetElement) return;
        const offset = window.innerWidth < 768 ? 100 : 80;
        window.scrollTo({
          top: targetElement.offsetTop - offset,
          behavior: "smooth",
        });
      });
    });
  }, []);

  useEffect(() => {
    if (!location.hash) return;

    const handleHashNavigation = () => {
      const targetElement = document.querySelector(location.hash);
      if (!targetElement) return;
      const offset = window.innerWidth < 768 ? 100 : 80;
      const elementPosition =
        (targetElement as HTMLElement).getBoundingClientRect().top +
        window.scrollY -
        offset;
      window.scrollTo({ top: elementPosition, behavior: "smooth" });
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

export default LandingPage;
