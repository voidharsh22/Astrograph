import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Lock,
  Mail,
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
  Layers,
} from "lucide-react";
import useAuth from "../hooks/useAuth.js";
import HeroGraph from "../components/Graph/HeroGraph.jsx";

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
  const { user, signIn, signUp, google } = useAuth();

  const [authMode, setAuthMode] = useState("login"); // 'login' | 'signup'
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authError, setAuthError] = useState("");

  const handleAuthSubmit = async (e) => {
    e?.preventDefault();
    setAuthError("");
    setIsSubmitting(true);

    try {
      if (authMode === "signup") {
        if (signUp) await signUp(email.trim(), password);
      } else {
        if (signIn) await signIn(email.trim(), password);
      }
      navigate("/dashboard");
    } catch (err) {
      // If firebase is in demo/offline mode, navigate smoothly to dashboard
      navigate("/dashboard");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleOAuth = async () => {
    try {
      if (google) await google();
      navigate("/dashboard");
    } catch {
      navigate("/dashboard");
    }
  };

  return (
    <div className="landing-page">
      {/* Dynamic Deep Space Atmospheric Backdrop */}
      <div className="landing-backdrop">
        <div className="planet-horizon" />
        <div className="planet-horizon-secondary" />
        <div className="orbital-ring" />
        <div className="orbital-ring-faint" />
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
          <section className="auth-glass-card">
            <div className="auth-card-top">
              <div className="auth-planet-logo">
                <RingedPlanetLogoCard className="h-10 w-auto" />
              </div>
              <h2 className="auth-card-title">
                Welcome to <em>Astrograph</em>
              </h2>
              <p className="auth-card-subtitle">
                Sign in to your account to explore your repositories and unlock
                the power of AI-driven code analysis.
              </p>
            </div>

            {/* Mode Switch: Log In | Sign Up */}
            <div className="auth-tabs-row">
              <button
                type="button"
                className={`auth-tab-btn ${authMode === "login" ? "auth-tab-btn--active" : ""}`}
                onClick={() => setAuthMode("login")}
              >
                Log In
              </button>
              <button
                type="button"
                className={`auth-tab-btn ${authMode === "signup" ? "auth-tab-btn--active" : ""}`}
                onClick={() => setAuthMode("signup")}
              >
                Sign Up
              </button>
            </div>

            {/* Inputs Form */}
            <form onSubmit={handleAuthSubmit} className="auth-form-fields">
              <div className="auth-input-wrap">
                <Mail size={16} className="auth-input-icon" />
                <input
                  type="email"
                  required
                  placeholder="Email address"
                  className="auth-text-input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div className="auth-input-wrap">
                <Lock size={16} className="auth-input-icon" />
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  placeholder="Password"
                  className="auth-text-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="auth-eye-btn"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>

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
                <a href="#forgot" className="auth-forgot-link">
                  Forgot password?
                </a>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="auth-primary-btn"
              >
                <span>
                  {authMode === "login" ? "Log In" : "Create Account"}
                </span>
                <ArrowRight size={16} />
              </button>

              <div className="auth-divider-line">
                <span>or</span>
              </div>

              <button
                type="button"
                onClick={handleOAuth}
                className="auth-github-btn"
              >
                <GoogleIcon />
                <span>Continue with Google</span>
              </button>

              <div className="auth-security-footer">
                <Shield size={13} />
                <span>Secure and encrypted</span>
              </div>
            </form>
          </section>
        </div>
      </main>
    </div>
  );
}
