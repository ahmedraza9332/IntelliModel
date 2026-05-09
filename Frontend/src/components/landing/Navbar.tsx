
import React, { useState, useEffect, useCallback } from "react";
import { GoogleLogin } from "@react-oauth/google";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { Menu, X } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import type { AuthUser } from "@/api/client";
import { getAuthMe, logoutAuth, signInWithGoogle } from "@/api/client";

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? "";

const Navbar = () => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authChecked, setAuthChecked] = useState(!GOOGLE_CLIENT_ID);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID) return;
    let cancelled = false;
    getAuthMe()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .finally(() => {
        if (!cancelled) setAuthChecked(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogout = useCallback(async () => {
    try {
      await logoutAuth();
      setUser(null);
      navigate("/");
      toast.error("Google sign in required.");
    } catch {
      toast.error("Could not sign out");
    }
  }, [navigate]);

  const handleGoogleSuccess = useCallback(async (credential: string) => {
    try {
      const u = await signInWithGoogle(credential);
      setUser(u);
      toast.success("Signed in");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Sign-in failed";
      toast.error(msg);
    }
  }, []);

  const handleTryNowClick = useCallback(
    (event: React.MouseEvent) => {
      if (GOOGLE_CLIENT_ID && !user) {
        event.preventDefault();
        navigate("/");
        toast.error("Google sign in required.");
        closeMenu();
      }
    },
    [navigate, user]
  );

  const renderAuth = (variant: "desktop" | "mobile") => {
    if (!GOOGLE_CLIENT_ID) return null;

    if (!authChecked) {
      return (
        <span
          className={cn(
            "text-sm text-muted-foreground",
            variant === "mobile" && "py-2"
          )}
        >
          ...
        </span>
      );
    }

    if (user) {
      const initial =
        user.name?.trim()?.charAt(0)?.toUpperCase() ??
        user.email?.trim()?.charAt(0)?.toUpperCase() ??
        "?";
      return (
        <div
          className={cn(
            "flex items-center gap-2",
            variant === "mobile" && "flex-col w-full gap-3 py-2"
          )}
        >
          <div className="flex items-center gap-2 min-w-0">
            <Avatar className="h-8 w-8 shrink-0">
              {user.picture_url ? (
                <AvatarImage src={user.picture_url} alt="" />
              ) : null}
              <AvatarFallback className="text-xs bg-slate-200 text-slate-700">
                {initial}
              </AvatarFallback>
            </Avatar>
            <span
              className={cn(
                "text-sm text-slate-700 dark:text-gray-200 truncate max-w-[140px]",
                variant === "mobile" && "max-w-none text-center"
              )}
              title={user.email ?? user.name ?? undefined}
            >
              {user.name ?? user.email ?? "Account"}
            </span>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className={cn(variant === "mobile" && "w-full")}
            onClick={() => {
              void handleLogout();
              closeMenu();
            }}
          >
            Sign out
          </Button>
        </div>
      );
    }

    return (
      <div
        className={cn(
          "flex items-center [&_iframe]:!shadow-none",
          variant === "mobile" && "justify-center py-2"
        )}
      >
        <GoogleLogin
          onSuccess={(res) => {
            if (res.credential) void handleGoogleSuccess(res.credential);
          }}
          onError={() => toast.error("Google Sign-In error")}
          useOneTap={false}
          size="medium"
          theme="outline"
          text="signin_with"
          shape="pill"
        />
      </div>
    );
  };

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
          ? "bg-white/80 dark:bg-dark-900/90 backdrop-blur-md shadow-sm dark:shadow-black/40"
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
          <span className="text-xl sm:text-2xl font-bold text-foreground dark:text-white">
            IntelliModel
          </span>
        </Link>

        {/* Desktop Navigation */}
        <nav className="hidden md:flex space-x-8">
          <Link
            to="/"
            className="nav-link dark:text-gray-300 dark:hover:text-pulse-400 dark:after:bg-pulse-400"
            onClick={handleHomeClick}
          >
            Home
          </Link>
          <Link
            to={{ pathname: "/", hash: "#about" }}
            className="nav-link dark:text-gray-300 dark:hover:text-pulse-400 dark:after:bg-pulse-400"
            onClick={(event) => handleSectionNavigation(event, "#about")}
          >
            About
          </Link>
          <Link
            to={{ pathname: "/", hash: "#features" }}
            className="nav-link dark:text-gray-300 dark:hover:text-pulse-400 dark:after:bg-pulse-400"
            onClick={(event) => handleSectionNavigation(event, "#features")}
          >
            Features
          </Link>
          <Link
            to={{ pathname: "/", hash: "#workflow" }}
            className="nav-link dark:text-gray-300 dark:hover:text-pulse-400 dark:after:bg-pulse-400"
            onClick={(event) => handleSectionNavigation(event, "#workflow")}
          >
            Workflow
          </Link>
          <Link
            to={{ pathname: "/", hash: "#demo" }}
            className="nav-link dark:text-gray-300 dark:hover:text-pulse-400 dark:after:bg-pulse-400"
            onClick={(event) => handleSectionNavigation(event, "#demo")}
          >
            Demo
          </Link>
          <Link
            to={{ pathname: "/", hash: "#contact" }}
            className="nav-link dark:text-gray-300 dark:hover:text-pulse-400 dark:after:bg-pulse-400"
            onClick={(event) => handleSectionNavigation(event, "#contact")}
          >
            Contact
          </Link>
          {renderAuth("desktop")}
          <Link
            to="/try-now"
            className="inline-flex items-center justify-center rounded-full bg-gradient-to-r from-pulse-500 via-orange-500 to-purple-600 px-5 py-2 font-medium text-white shadow-lg transition-all duration-300 hover:shadow-xl hover:from-pulse-600 hover:via-orange-600 hover:to-purple-700 focus:outline-none focus:ring-2 focus:ring-pulse-300"
            onClick={(event) => {
              handleTryNowClick(event);
              closeMenu();
            }}
          >
            Try Now
          </Link>
        </nav>

        {/* Mobile menu button */}
        <button
          className="md:hidden text-gray-700 dark:text-gray-300 p-3 focus:outline-none"
          onClick={toggleMenu}
          aria-label={isMenuOpen ? "Close menu" : "Open menu"}
        >
          {isMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Mobile full-screen menu */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-white dark:bg-dark-900 flex flex-col pt-16 px-6 md:hidden transition-all duration-300 ease-in-out",
          isMenuOpen
            ? "opacity-100 translate-x-0"
            : "opacity-0 translate-x-full pointer-events-none"
        )}
      >
        <nav className="flex flex-col space-y-8 items-center mt-8">
          <Link
            to="/"
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
            onClick={(event) => handleHomeClick(event)}
          >
            Home
          </Link>
          <Link
            to={{ pathname: "/", hash: "#about" }}
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
            onClick={(event) => handleSectionNavigation(event, "#about")}
          >
            About
          </Link>
          <Link
            to={{ pathname: "/", hash: "#features" }}
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
            onClick={(event) => handleSectionNavigation(event, "#features")}
          >
            Features
          </Link>
          <Link
            to={{ pathname: "/", hash: "#workflow" }}
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
            onClick={(event) => handleSectionNavigation(event, "#workflow")}
          >
            Workflow
          </Link>
          <Link
            to={{ pathname: "/", hash: "#demo" }}
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
            onClick={(event) => handleSectionNavigation(event, "#demo")}
          >
            Demo
          </Link>
          <Link
            to={{ pathname: "/", hash: "#contact" }}
            className="text-xl font-medium py-3 px-6 w-full text-center rounded-lg hover:bg-gray-100 dark:text-gray-200 dark:hover:bg-white/5"
            onClick={(event) => handleSectionNavigation(event, "#contact")}
          >
            Contact
          </Link>
          {renderAuth("mobile")}
          <Link
            to="/try-now"
            className="text-xl font-semibold py-3 px-6 w-full text-center rounded-full bg-gradient-to-r from-pulse-500 via-orange-500 to-purple-600 text-white shadow-lg hover:shadow-xl transition-all duration-300"
            onClick={(event) => {
              handleTryNowClick(event);
              closeMenu();
            }}
          >
            Try Now
          </Link>
        </nav>
      </div>
    </header>
  );
};

export default Navbar;
