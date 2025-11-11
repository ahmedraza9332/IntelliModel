
import React, { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import { Menu, X } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

const Navbar = () => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };
    
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const toggleMenu = () => {
    setIsMenuOpen(!isMenuOpen);
    // Prevent background scrolling when menu is open
    document.body.style.overflow = !isMenuOpen ? 'hidden' : '';
  };

  const closeMenu = () => {
    setIsMenuOpen(false);
    document.body.style.overflow = '';
  };

  const scrollToSection = (hash: string) => {
    const targetElement = document.querySelector(hash);

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
      behavior: 'smooth'
    });

    if (window.history.replaceState) {
      window.history.replaceState(null, "", hash);
    }
  };

  const handleHomeClick = (event?: React.MouseEvent) => {
    if (location.pathname === "/") {
      event?.preventDefault();
      scrollToTop();
    }
    closeMenu();

    if (location.pathname !== "/") {
      navigate("/");
    }
  };

  const handleSectionNavigation = (
    event: React.MouseEvent,
    hash: string
  ) => {
    if (location.pathname === "/") {
      event.preventDefault();
      scrollToSection(hash);
      closeMenu();
      return;
    }

    closeMenu();
    navigate({
      pathname: "/",
      hash
    });
  };

  const scrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: 'smooth'
    });
    
    // Close mobile menu if open
    if (isMenuOpen) {
      setIsMenuOpen(false);
      document.body.style.overflow = '';
    }
  };

  return (
    <header
      className={cn(
        "fixed top-0 left-0 right-0 z-50 py-2 sm:py-3 md:py-4 transition-all duration-300",
        isScrolled 
          ? "bg-white/80 backdrop-blur-md shadow-sm" 
          : "bg-transparent"
      )}
    >
      <div className="container flex items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link 
          to="/" 
          className="flex items-center space-x-2"
          onClick={handleHomeClick}
          aria-label="IntelliModel"
        >
          <span className="text-xl sm:text-2xl font-bold text-foreground">
            IntelliModel
          </span>
        </Link>

        {/* Desktop Navigation */}
        <nav className="hidden md:flex space-x-8">
          <Link 
            to="/" 
            className="nav-link"
            onClick={handleHomeClick}
          >
            Home
          </Link>
          <Link 
            to={{ pathname: "/", hash: "#about" }} 
            className="nav-link"
            onClick={(event) => handleSectionNavigation(event, "#about")}
          >
            About
          </Link>
          <Link 
            to={{ pathname: "/", hash: "#features" }} 
            className="nav-link"
            onClick={(event) => handleSectionNavigation(event, "#features")}
          >
            Features
          </Link>
          <Link 
            to={{ pathname: "/", hash: "#workflow" }} 
            className="nav-link"
            onClick={(event) => handleSectionNavigation(event, "#workflow")}
          >
            Workflow
          </Link>
          <Link 
            to={{ pathname: "/", hash: "#demo" }} 
            className="nav-link"
            onClick={(event) => handleSectionNavigation(event, "#demo")}
          >
            Demo
          </Link>
          <Link 
            to={{ pathname: "/", hash: "#contact" }} 
            className="nav-link"
            onClick={(event) => handleSectionNavigation(event, "#contact")}
          >
            Contact
          </Link>
          <Link
            to="/try-now"
            className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-pulse-500 via-orange-500 to-purple-600 px-5 py-2 font-medium text-white shadow-lg transition-all duration-300 hover:shadow-xl hover:from-pulse-600 hover:via-orange-600 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-pulse-300"
            onClick={closeMenu}
          >
            Try Now
          </Link>
        </nav>

        {/* Mobile menu button - increased touch target */}
        <button 
          className="md:hidden text-gray-700 p-3 focus:outline-none" 
          onClick={toggleMenu}
          aria-label={isMenuOpen ? "Close menu" : "Open menu"}
        >
          {isMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      <div className={cn(
        "fixed inset-0 z-40 bg-white flex flex-col pt-16 px-6 md:hidden transition-all duration-300 ease-in-out",
        isMenuOpen ? "opacity-100 translate-x-0" : "opacity-0 translate-x-full pointer-events-none"
      )}>
        <nav className="flex flex-col space-y-8 items-center mt-8">
          <Link 
            to="/" 
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100" 
            onClick={(event) => handleHomeClick(event)}
          >
            Home
          </Link>
          <Link 
            to={{ pathname: "/", hash: "#about" }} 
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100" 
            onClick={(event) => handleSectionNavigation(event, "#about")}
          >
            About
          </Link>
          <Link 
            to={{ pathname: "/", hash: "#features" }} 
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100" 
            onClick={(event) => handleSectionNavigation(event, "#features")}
          >
            Features
          </Link>
          <Link 
            to={{ pathname: "/", hash: "#workflow" }} 
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100" 
            onClick={(event) => handleSectionNavigation(event, "#workflow")}
          >
            Workflow
          </Link>
          <Link 
            to={{ pathname: "/", hash: "#demo" }} 
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100" 
            onClick={(event) => handleSectionNavigation(event, "#demo")}
          >
            Demo
          </Link>
          <Link 
            to={{ pathname: "/", hash: "#contact" }} 
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100" 
            onClick={(event) => handleSectionNavigation(event, "#contact")}
          >
            Contact
          </Link>
          <Link
            to="/try-now"
            className="text-xl font-semibold py-3 px-6 w-full text-center rounded-full bg-gradient-to-r from-pulse-500 via-orange-500 to-purple-600 text-white shadow-lg hover:shadow-xl transition-all duration-300"
            onClick={closeMenu}
          >
            Try Now
          </Link>
        </nav>
      </div>
    </header>
  );
};

export default Navbar;
