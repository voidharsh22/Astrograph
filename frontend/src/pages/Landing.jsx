import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Lock,
  Mail,
  User,
  Eye,
  EyeOff,
  Folder,
  FileCode,
  Network,
  Search,
  Sparkles,
  Zap,
  ArrowRight,
  Shield,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  Info,
  Loader2,
  Layers,
} from "lucide-react";
import useAuth, { friendlyError, messageForAuthError } from "../hooks/useAuth.js";
import HeroGraph from "../components/Graph/HeroGraph.jsx";
import SiteFooter from "../components/SiteFooter.jsx";

// Official Astrograph Team Ringed Planet Logo (Exact pixel match to the official artwork)
export function RingedPlanetLogo({ className = "h-7 w-auto" }) {
  return (
    <img
      src="/team_logo_transparent.png"
      alt="Astrograph Logo"
      className={`${className} object-contain select-none`}
      draggable="false"
    />
  );
}

// Larger Card Logo version for high-DPI glass card header
export function RingedPlanetLogoCard({ className = "h-11 w-auto" }) {
  return (
    <img
      src="/team_logo_card_transparent.png"
      alt="Astrograph Logo"
      className={`${className} object-contain select-none filter drop-shadow-[0_0_16px_rgba(251,146,60,0.5)]`}
      draggable="false"
    />
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M24 9.5c3.5 0 6.6 1.2 9 3.5l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.8 6.1C12.3 13.5 17.7 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.4-4.1 7-10.1 7-17.6z"
      />
      <path
        fill="#FBBC05"
        d="M10.4 28.7A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.2.8-4.7l-7.8-6.1A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.8l7.8-6.1z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.2 0 11.5-2 15.3-5.600l-7.600-5.900c-2.100 1.400-4.800 2.300-7.700 2.300-6.300 0-11.700-4-13.600-9.800l-7.800 6.100C6.500 42.600 14.600 48 24 48z"
      />
    </svg>
  );
}

export default function Landing() {
  const navigate = useNavigate();
  const {
    user,
    ready,
    signIn,
    signUp,
    google,
  } = useAuth();

  const [authMode, setAuthMode] = useState("login"); // 'login' | 'signup'
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authError, setAuthError] = useState("");
  const [authSuccess, setAuthSuccess] = useState("");
  const [authHint, setAuthHint] = useState(""); // "" | "exists" | "invalid"

  // Show the outcome of a Google redirect (?auth_error=...) once, then clean the URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("auth_error");
    if (code) {
      setAuthError(messageForAuthError(code));
      if (code === "google_email_in_use") setAuthHint("exists");
      params.delete("auth_error");
      const qs = params.toString();
      window.history.replaceState({}, "", window.location.pathname + (qs ? `?${qs}` : ""));
    }
  }, []);

  // Automatically forward authenticated users to the dashboard (prevents redirect loops)
  useEffect(() => {
    if (user && ready) {
      navigate("/dashboard", { replace: true });
    }
  }, [user, ready, navigate]);

  const handleAuthSubmit = async (e) => {
    e?.preventDefault();
    setAuthError("");
    setAuthSuccess("");
    setAuthHint("");
    setIsSubmitting(true);

    try {
      if (authMode === "signup") {
        const trimmedName = name.trim();
        if (!trimmedName || trimmedName.length < 2) {
          throw new Error("Please enter your full name (at least 2 characters).");
        }
        if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
          throw new Error("Please enter a valid email address (e.g., developer@domain.com).");
        }
        if (!password || password.length < 6) {
          throw new Error("Password must be at least 6 characters.");
        }
        if (password !== confirmPassword) {
          throw new Error("Passwords do not match. Please verify both passwords.");
        }

        await signUp(email.trim(), password, trimmedName);
        // The backend created the account but did not sign anyone in: continue to the login form.
        setAuthMode("login");
        setPassword("");
        setConfirmPassword("");
        setAuthSuccess("Account created. Please log in.");
        return;
      } else {
        if (!email.trim()) {
          throw new Error("Please enter your email address.");
        }
        if (!password) {
          throw new Error("Please enter your password.");
        }

        await signIn(email.trim(), password);
        setAuthSuccess("Signed in successfully! Redirecting...");
      }
      navigate("/dashboard");
    } catch (err) {
      setAuthError(friendlyError(err));
      if (err.code === "email_exists") setAuthHint("exists");
      else if (err.code === "invalid_credentials") setAuthHint("invalid");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOAuth = async () => {
    setAuthError("");
    setAuthSuccess("");
    setAuthHint("");
    setIsSubmitting(true);
    try {
      // Navigates the page to Google's account chooser; the user is only signed in after the
      // backend validates Google's response and redirects back to the dashboard.
      await google();
    } catch (err) {
      setAuthError(friendlyError(err));
      setIsSubmitting(false);
    }
  };

  return (
    <div className="landing-page">
      {/* Cinematic Deep Space Planetary Backdrop */}
      <div className="landing-backdrop" aria-hidden="true">
        <div className="landing-planet-image" />
        <div className="landing-ambient-corona" />
        <div className="landing-vignette-overlay" />
      </div>

      {/* Top Navigation Bar - Matching Reference Image */}
      <header className="landing-nav">
        <div className="landing-brand">
          <RingedPlanetLogo />
          <span className="brand-title">A S T R O G R A P H</span>
        </div>

        <nav className="nav-links">
          <Link to="/" className="nav-link nav-link--active">
            Home
          </Link>
          <Link to="/features" className="nav-link">
            Features
          </Link>
          <Link to="/about" className="nav-link">
            About
          </Link>
        </nav>

        <div className="nav-pill-words">
          <span>Visualize</span>
          <span>·</span>
          <span>Understand</span>
          <span>·</span>
          <span>Build Better</span>
        </div>
      </header>

      {/* Main 12-Column Split Screen Hero Layout */}
      <main className="landing-main-grid">
        {/* Left Column (7 cols): Value Prop & Mini Preview */}
        <div className="hero-left-col">
          <div className="hero-eyebrow">
            <span>—</span> AI-POWERED CODEBASE INTELLIGENCE
          </div>

          <h1 className="hero-headline">
            Turn any repository into an
            <em>interactive knowledge graph.</em>
          </h1>

          <p className="hero-subheadline">
            Astrograph helps you explore, understand and navigate codebases with
            the power of AI — from structure and dependencies to symbols and
            smart insights.
          </p>

          {/* 4-Item Horizontal Feature Row */}
          <div className="hero-feature-row">
            <div className="hero-feature-item">
              <div className="hero-feature-icon">
                <Network size={20} />
              </div>
              <h4 className="hero-feature-title">Visualize</h4>
              <p className="hero-feature-desc">
                See your codebase as an interactive graph
              </p>
            </div>

            <div className="hero-feature-item">
              <div className="hero-feature-icon">
                <Search size={18} />
              </div>
              <h4 className="hero-feature-title">Explore</h4>
              <p className="hero-feature-desc">
                Find files, symbols and dependencies
              </p>
            </div>

            <div className="hero-feature-item">
              <div className="hero-feature-icon">
                <Sparkles size={18} />
              </div>
              <h4 className="hero-feature-title">Analyze</h4>
              <p className="hero-feature-desc">
                Get AI-powered insights and summaries
              </p>
            </div>

            <div className="hero-feature-item">
              <div className="hero-feature-icon">
                <Zap size={18} />
              </div>
              <h4 className="hero-feature-title">Build Faster</h4>
              <p className="hero-feature-desc">
                Understand. Debug. Ship with confidence.
              </p>
            </div>
          </div>

          {/* Mini Interactive Astrograph Workspace Preview Window */}
          <div className="hero-mock-window">
            <div className="mock-window-header">
              <div className="mock-window-brand">
                <RingedPlanetLogo className="w-4 h-4 text-[#FB923C]" />
                <span>ASTROGRAPH</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-white/20" />
                <div className="w-2.5 h-2.5 rounded-full bg-white/20" />
                <div className="w-2.5 h-2.5 rounded-full bg-white/20" />
              </div>
            </div>

            <div className="mock-window-body">
              {/* Left Tree */}
              <div className="mock-pane-tree">
                <div className="text-[10px] text-[#9CA3AF] mb-1 font-bold">
                  my-repo
                </div>
                <div className="mock-tree-item">
                  <Folder size={11} className="text-[#FB923C]" /> src
                </div>
                <div className="mock-tree-item pl-3">
                  <Folder size={10} /> components
                </div>
                <div className="mock-tree-item pl-3">
                  <Folder size={10} /> pages
                </div>
                <div className="mock-tree-item pl-3 mock-tree-item--active">
                  <Folder size={10} className="text-[#FB923C]" /> services
                </div>
                <div className="mock-tree-item pl-3">
                  <Folder size={10} /> utils
                </div>
                <div className="mock-tree-item">
                  <FileCode size={11} /> package.json
                </div>
                <div className="mock-tree-item">
                  <FileCode size={11} /> README.md
                </div>
              </div>

              {/* Center Graph Preview */}
              <div className="mock-pane-graph">
                <div className="mock-graph-tabs">
                  <span className="mock-tab mock-tab--active">Graph</span>
                  <span className="mock-tab">Explorer</span>
                  <span className="mock-tab">Details</span>
                </div>
                {/* SVG Visual Constellation Diagram */}
                <svg className="mock-graph-canvas" viewBox="0 0 260 160">
                  {/* Directed Edges */}
                  <line
                    x1="130"
                    y1="80"
                    x2="60"
                    y2="40"
                    stroke="#FB923C"
                    strokeWidth="1"
                    strokeOpacity="0.4"
                  />
                  <line
                    x1="130"
                    y1="80"
                    x2="200"
                    y2="45"
                    stroke="#FB923C"
                    strokeWidth="1"
                    strokeOpacity="0.4"
                  />
                  <line
                    x1="130"
                    y1="80"
                    x2="70"
                    y2="120"
                    stroke="#FB923C"
                    strokeWidth="1"
                    strokeOpacity="0.4"
                  />
                  <line
                    x1="130"
                    y1="80"
                    x2="190"
                    y2="115"
                    stroke="#FB923C"
                    strokeWidth="1"
                    strokeOpacity="0.4"
                  />
                  <line
                    x1="130"
                    y1="80"
                    x2="130"
                    y2="25"
                    stroke="#FB923C"
                    strokeWidth="1"
                    strokeOpacity="0.4"
                  />
                  <line
                    x1="60"
                    y1="40"
                    x2="30"
                    y2="70"
                    stroke="#FDBA74"
                    strokeWidth="0.8"
                    strokeOpacity="0.3"
                  />
                  <line
                    x1="200"
                    y1="45"
                    x2="230"
                    y2="85"
                    stroke="#FDBA74"
                    strokeWidth="0.8"
                    strokeOpacity="0.3"
                  />

                  {/* Satellites */}
                  <circle cx="60" cy="40" r="4.5" fill="#3B82F6" />
                  <circle cx="200" cy="45" r="5" fill="#10B981" />
                  <circle cx="70" cy="120" r="4" fill="#A855F7" />
                  <circle cx="190" cy="115" r="4.5" fill="#F59E0B" />
                  <circle cx="130" cy="25" r="3.5" fill="#EC4899" />
                  <circle cx="30" cy="70" r="3" fill="#60A5FA" />
                  <circle cx="230" cy="85" r="3" fill="#34D399" />

                  {/* Pulsing Central Hub Node (UserService) */}
                  <circle
                    cx="130"
                    cy="80"
                    r="9"
                    fill="#FB923C"
                    fillOpacity="0.25"
                  />
                  <circle cx="130" cy="80" r="5.5" fill="#FB923C" />
                </svg>
              </div>

              {/* Right Inspector */}
              <div className="mock-pane-inspector">
                <div>
                  <div className="mock-inspector-title">UserService</div>
                  <div className="text-[10px] text-[#9CA3AF]">Class</div>
                </div>

                <div>
                  <div className="text-[9px] uppercase font-bold text-[#FB923C] mb-1">
                    Dependencies
                  </div>
                  <span className="mock-chip">AuthService</span>
                  <span className="mock-chip">Database</span>
                  <span className="mock-chip">Logger</span>
                </div>

                <div>
                  <div className="text-[9px] uppercase font-bold text-[#9CA3AF] mb-1">
                    Methods
                  </div>
                  <div className="text-[10px] font-mono text-[#D1D5DB] space-y-0.5">
                    <div>• getUser()</div>
                    <div>• updateUser()</div>
                    <div>• deleteUser()</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="hero-tagline-footer">
            <span className="text-[#FB923C] text-sm">∞</span>
            <span>Better code understanding. A smarter tomorrow.</span>
          </div>
        </div>

        {/* Right Column (5 cols): Glassmorphic Auth Card */}
        <div>
          <section className="auth-glass-card" aria-labelledby="auth-header-title">
            <div className="auth-card-top">
              <div className="auth-planet-logo">
                <RingedPlanetLogoCard className="h-10 w-auto" />
              </div>
              <h2 id="auth-header-title" className="auth-card-title">
                {authMode === "login" ? (
                  <>Welcome to <em>Astrograph</em></>
                ) : (
                  <>Create Your <em>Account</em></>
                )}
              </h2>
              <p className="auth-card-subtitle">
                {authMode === "login"
                  ? "Sign in to explore your repositories and unlock the power of AI-driven code analysis."
                  : "Join Astrograph to construct 2D/3D code graphs, extract AST dependencies, and trace architectures."}
              </p>

            </div>

            {/* Mode Switch Tabs: Log In | Sign Up */}
            <div className="auth-tabs-row" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={authMode === "login"}
                className={`auth-tab-btn ${authMode === "login" ? "auth-tab-btn--active" : ""}`}
                onClick={() => {
                  setAuthMode("login");
                  setAuthError("");
                  setAuthSuccess("");
                }}
              >
                Log In
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={authMode === "signup"}
                className={`auth-tab-btn ${authMode === "signup" ? "auth-tab-btn--active" : ""}`}
                onClick={() => {
                  setAuthMode("signup");
                  setAuthError("");
                  setAuthSuccess("");
                }}
              >
                Sign Up
              </button>
            </div>

            {/* Form Fields */}
            <form onSubmit={handleAuthSubmit} className="auth-form-fields" noValidate>
              {authError && (
                <div className="auth-error-badge" role="alert">
                  <AlertCircle size={16} className="shrink-0" />
                  <span>{authError}</span>
                </div>
              )}

              {authHint === "exists" && (
                <button
                  type="button"
                  className="auth-switch-link-btn"
                  onClick={() => {
                    setAuthMode("login");
                    setAuthError("");
                    setAuthHint("");
                  }}
                >
                  Go to Log In
                </button>
              )}
              {authHint === "invalid" && (
                <span style={{ fontSize: "0.75rem", color: "#9CA3AF" }}>
                  Signed up with Google? Use “Continue with Google” below.
                </span>
              )}

              {authSuccess && (
                <div className="auth-success-badge" role="status">
                  <CheckCircle2 size={16} className="shrink-0" />
                  <span>{authSuccess}</span>
                </div>
              )}

              {/* Name Field (Sign Up Only) */}
              {authMode === "signup" && (
                <div className="auth-input-wrap">
                  <User size={16} className="auth-input-icon" />
                  <input
                    type="text"
                    required
                    placeholder="Full Name (e.g. Alex Morgan)"
                    className="auth-text-input"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    disabled={isSubmitting}
                  />
                </div>
              )}

              {/* Email Field */}
              <div className="auth-input-wrap">
                <Mail size={16} className="auth-input-icon" />
                <input
                  type="email"
                  required
                  placeholder="Email address"
                  className="auth-text-input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={isSubmitting}
                  autoComplete="email"
                />
              </div>

              {/* Password Field */}
              <div className="auth-input-wrap">
                <Lock size={16} className="auth-input-icon" />
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  placeholder={authMode === "signup" ? "Password (min. 6 chars)" : "Password"}
                  className="auth-text-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={isSubmitting}
                  autoComplete={authMode === "signup" ? "new-password" : "current-password"}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="auth-eye-btn"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>

              {/* Confirm Password Field (Sign Up Only) */}
              {authMode === "signup" && (
                <div className="auth-input-wrap">
                  <ShieldCheck size={16} className="auth-input-icon" />
                  <input
                    type={showConfirmPassword ? "text" : "password"}
                    required
                    placeholder="Confirm Password"
                    className="auth-text-input"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    disabled={isSubmitting}
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="auth-eye-btn"
                    aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}
                  >
                    {showConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              )}

              {/* Remember Me & Forgot Password (Login Only) */}
              {authMode === "login" && (
                <div className="auth-row-remember">
                  <label className="auth-remember-label">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                      className="accent-[#FB923C] rounded"
                    />
                    <span>Remember me</span>
                  </label>
                </div>
              )}

              {/* Submit Button */}
              <button
                type="submit"
                disabled={isSubmitting}
                className="auth-primary-btn"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <span>
                      {authMode === "login" ? "Log In" : "Create Account"}
                    </span>
                    <ArrowRight size={16} />
                  </>
                )}
              </button>

              <div className="auth-divider-line">
                <span>or</span>
              </div>

              {/* Google OAuth Option */}
              <button
                type="button"
                onClick={handleOAuth}
                className="auth-github-btn"
                disabled={isSubmitting}
              >
                <GoogleIcon />
                <span>Continue with Google</span>
              </button>

              {/* Switch Mode Footer Link */}
              <div className="auth-form-footer-switch">
                {authMode === "login" ? (
                  <span>
                    Don't have an account?{" "}
                    <button
                      type="button"
                      onClick={() => {
                        setAuthMode("signup");
                        setAuthError("");
                        setAuthSuccess("");
                      }}
                      className="auth-switch-link-btn"
                    >
                      Sign Up
                    </button>
                  </span>
                ) : (
                  <span>
                    Already have an account?{" "}
                    <button
                      type="button"
                      onClick={() => {
                        setAuthMode("login");
                        setAuthError("");
                        setAuthSuccess("");
                      }}
                      className="auth-switch-link-btn"
                    >
                      Log In
                    </button>
                  </span>
                )}
              </div>

              <div className="auth-security-footer">
                <Shield size={13} />
                <span>
                  Server-verified sign-in • Salted scrypt password hashing
                </span>
              </div>
            </form>
          </section>
        </div>
      </main>

      {/* Shared Global Site Footer */}
      <SiteFooter />
    </div>
  );
}
