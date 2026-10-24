import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  ArrowDown,
  Eye,
  Users,
  Rocket,
  Layers,
  Clock,
  AlertTriangle,
  Network,
  BarChart3,
  Sparkles,
  Box,
  Database,
  Cpu,
  FileCode,
  GitFork,
  Folder,
  Code2,
  Terminal,
  Share2,
  Server,
  Workflow,
  Search,
  CheckCircle2
} from 'lucide-react';
import { RingedPlanetLogo } from './Landing.jsx';
import '../styles/about.css';

export default function About() {
  const navigate = useNavigate();

  const scrollToMission = () => {
    const el = document.getElementById('mission-section');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <div className="about-page">
      {/* Background Atmosphere */}
      <div className="about-backdrop">
        <div className="about-planet-horizon" />
        <div className="about-planet-horizon-secondary" />
        <div className="about-bottom-horizon" />
      </div>

      {/* Top Header Navbar */}
      <header className="landing-nav">
        <div 
          className="landing-brand cursor-pointer" 
          onClick={() => navigate('/')}
          role="button"
          tabIndex={0}
        >
          <RingedPlanetLogo />
          <span className="brand-title">A S T R O G R A P H</span>
        </div>

        <nav className="nav-links">
          <Link to="/" className="nav-link">Home</Link>
          <Link to="/features" className="nav-link">Features</Link>
          <span className="nav-link nav-link--active cursor-default">About</span>
        </nav>

        <div className="nav-pill-words">
          <span>Visualize</span>
          <span>·</span>
          <span>Understand</span>
          <span>·</span>
          <span>Build Better</span>
        </div>
      </header>

      {/* Main Container with generous, unclustered spacing */}
      <main className="about-container">
        
        {/* ==========================================================================
            HERO SECTION
            ========================================================================== */}
        <section className="about-hero">
          <div className="about-hero-left">
            <span className="about-eyebrow">[ ABOUT ASTROGRAPH ]</span>

            <h1 className="about-hero-title">
              More than code.
              <em>A universe of understanding.</em>
            </h1>

            <p className="about-hero-sub">
              Astrograph is a next-generation developer tool that transforms complex GitHub repositories into interactive, 3D knowledge galaxies. Built with the belief that software architecture should be visual, intuitive, and accessible to everyone.
            </p>

            <div className="about-hero-actions">
              <button
                type="button"
                onClick={scrollToMission}
                className="btn-primary-orange"
              >
                <span>Our Mission</span>
                <ArrowDown size={16} />
              </button>

              <Link to="/features" className="btn-secondary-glass">
                <span>Explore Features</span>
                <ArrowRight size={16} />
              </Link>
            </div>
          </div>

          {/* Hero Right: Interactive 3-Pane Mini Preview Window */}
          <div className="about-hero-preview">
            <div className="about-preview-topbar">
              <div className="flex items-center gap-1.5 text-gray-400">
                <Folder size={12} className="text-[#FB923C]" />
                <span className="text-white font-bold">my-repo</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 rounded bg-[#FB923C]/10 border border-[#FB923C]/30 text-[#FB923C] text-[9px] font-semibold">Graph</span>
                <span className="text-gray-500 text-[9px]">Explorer</span>
                <span className="text-gray-500 text-[9px]">Insights</span>
              </div>
            </div>

            <div className="about-preview-grid">
              {/* Left: Mini File Tree */}
              <div className="preview-pane space-y-1 text-gray-400">
                <div className="text-gray-500 text-[9px] uppercase font-bold mb-1">Explorer</div>
                <div className="flex items-center gap-1 text-white font-medium"><span>📁</span> src</div>
                <div className="pl-2 space-y-0.5 text-[9px]">
                  <div>📁 components</div>
                  <div>📁 pages</div>
                  <div className="text-[#FB923C] font-semibold">📁 services</div>
                  <div>📁 utils</div>
                  <div>📄 App.jsx</div>
                  <div>📄 index.js</div>
                </div>
                <div className="pt-1 text-[9px] text-gray-500">📄 package.json</div>
                <div className="text-[9px] text-gray-500">📄 README.md</div>
              </div>

              {/* Center: Constellation Canvas */}
              <div className="preview-pane bg-[#070b14] flex items-center justify-center p-1 relative overflow-hidden">
                <svg className="w-full h-full" viewBox="0 0 160 140">
                  <defs>
                    <radialGradient id="aboutSun" cx="50%" cy="50%" r="50%">
                      <stop offset="0%" stopColor="#FB923C" stopOpacity="0.8" />
                      <stop offset="60%" stopColor="#F59E0B" stopOpacity="0.25" />
                      <stop offset="100%" stopColor="#FB923C" stopOpacity="0" />
                    </radialGradient>
                  </defs>
                  
                  {/* Edges */}
                  <line x1="80" y1="70" x2="30" y2="35" stroke="#FB923C" strokeWidth="0.8" strokeOpacity="0.5" />
                  <line x1="80" y1="70" x2="130" y2="40" stroke="#FB923C" strokeWidth="0.8" strokeOpacity="0.5" />
                  <line x1="80" y1="70" x2="40" y2="105" stroke="#FB923C" strokeWidth="0.8" strokeOpacity="0.5" />
                  <line x1="80" y1="70" x2="125" y2="100" stroke="#FB923C" strokeWidth="0.8" strokeOpacity="0.5" />
                  <line x1="80" y1="70" x2="80" y2="20" stroke="#FB923C" strokeWidth="0.8" strokeOpacity="0.5" />
                  
                  {/* Satellites */}
                  <circle cx="30" cy="35" r="4.5" fill="#38BDF8" />
                  <circle cx="130" cy="40" r="4.5" fill="#10B981" />
                  <circle cx="40" cy="105" r="4.5" fill="#A855F7" />
                  <circle cx="125" cy="100" r="4.5" fill="#F59E0B" />
                  <circle cx="80" cy="20" r="4" fill="#EC4899" />
                  
                  {/* Center Node */}
                  <circle cx="80" cy="70" r="16" fill="url(#aboutSun)" />
                  <circle cx="80" cy="70" r="7" fill="#FB923C" />
                  <circle cx="80" cy="70" r="3" fill="#FFF7ED" />
                  <text x="80" y="85" fill="#FFF7ED" fontSize="6.5" textAnchor="middle" fontFamily="monospace" fontWeight="bold">UserService</text>
                </svg>
              </div>

              {/* Right: Inspector */}
              <div className="preview-pane flex flex-col justify-between">
                <div>
                  <div className="flex justify-between items-center pb-1 border-b border-white/10">
                    <span className="text-white font-bold">UserService</span>
                    <span className="text-[8px] text-[#FB923C] bg-[#FB923C]/10 px-1 py-0.5 rounded">Class</span>
                  </div>
                  <div className="space-y-1 text-[9px] mt-1.5 text-gray-400">
                    <div className="flex justify-between"><span>Lines of Code</span><span className="text-white">320</span></div>
                    <div className="flex justify-between"><span>Complexity</span><span className="text-white">12</span></div>
                    <div className="flex justify-between"><span>PageRank</span><span className="text-[#FB923C]">0.18</span></div>
                    <div className="flex justify-between"><span>Cluster</span><span className="text-[#FDBA74]">3</span></div>
                  </div>
                </div>

                <div className="border-t border-white/10 pt-1 text-[8.5px]">
                  <div className="text-gray-400 uppercase font-semibold text-[8px] mb-0.5">Dependencies</div>
                  <div className="space-y-0.5 text-gray-300">
                    <div>• AuthService</div>
                    <div>• Database</div>
                    <div>• Logger</div>
                    <div>• Config</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ==========================================================================
            SECTION 01: OUR MISSION
            ========================================================================== */}
        <section id="mission-section" className="about-mission-section">
          <div className="mission-left">
            <span className="section-num-tag">01 / OUR MISSION</span>
            <h2 className="section-title">
              Make software systems easy to <em>see, understand,</em> and <em>explore.</em>
            </h2>
          </div>

          <div className="mission-mid">
            We believe that every codebase has a story — a structure, a flow, and a purpose. Our mission is to turn complex repositories into interactive experiences that help developers explore architecture, discover relationships, and build better software, faster.
          </div>

          <div className="mission-pillars">
            <div className="pillar-item">
              <div className="pillar-icon-box">
                <Eye size={18} />
              </div>
              <div>
                <h4 className="pillar-title">Visual by Default</h4>
                <p className="pillar-desc">Turn code into interactive galaxies.</p>
              </div>
            </div>

            <div className="pillar-item">
              <div className="pillar-icon-box">
                <Users size={18} />
              </div>
              <div>
                <h4 className="pillar-title">Accessible</h4>
                <p className="pillar-desc">Make architecture understandable for everyone.</p>
              </div>
            </div>

            <div className="pillar-item">
              <div className="pillar-icon-box">
                <Rocket size={18} />
              </div>
              <div>
                <h4 className="pillar-title">Empower Developers</h4>
                <p className="pillar-desc">Help you navigate, learn, and build with confidence.</p>
              </div>
            </div>
          </div>
        </section>

        {/* ==========================================================================
            SECTION 02: THE PROBLEM
            ========================================================================== */}
        <section className="about-problem-section">
          <div className="problem-left">
            <span className="section-num-tag">02 / THE PROBLEM</span>
            <h2 className="section-title">
              Large codebases are <em>hard to navigate.</em>
            </h2>
            <p className="problem-desc">
              Understanding unfamiliar repositories can be overwhelming. Traditional file trees and 2D diagrams fail to capture the bigger picture — dependencies, module relationships, and architectural flow.
            </p>
          </div>

          <div className="problem-cards-column">
            <div className="problem-card">
              <div className="problem-icon-circle">
                <Layers size={18} />
              </div>
              <div>
                <h4 className="problem-card-title">Complex Dependencies</h4>
                <p className="problem-card-desc">Hard to trace how components connect.</p>
              </div>
            </div>

            <div className="problem-card">
              <div className="problem-icon-circle">
                <Clock size={18} />
              </div>
              <div>
                <h4 className="problem-card-title">Steep Onboarding</h4>
                <p className="problem-card-desc">Takes weeks to understand large systems.</p>
              </div>
            </div>

            <div className="problem-card">
              <div className="problem-icon-circle">
                <AlertTriangle size={18} />
              </div>
              <div>
                <h4 className="problem-card-title">Impact Uncertainty</h4>
                <p className="problem-card-desc">Difficult to predict what might break before making changes.</p>
              </div>
            </div>
          </div>

          {/* Perspective 3D Mockup Right Visual */}
          <div className="problem-mockup-pane">
            <svg className="w-full h-44" viewBox="0 0 200 150">
              <defs>
                <linearGradient id="gridGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#FB923C" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="#38BDF8" stopOpacity="0.1" />
                </linearGradient>
              </defs>
              
              {/* Tilted Isometric Layer Stack */}
              <polygon points="30,40 170,25 170,110 30,125" fill="#0f172a" stroke="rgba(251,146,60,0.3)" strokeWidth="1" />
              <polygon points="20,55 160,40 160,125 20,140" fill="#090e1a" stroke="rgba(56,189,248,0.4)" strokeWidth="1" />
              
              {/* Glowing Lines & Nodes */}
              <line x1="45" y1="75" x2="135" y2="60" stroke="#FB923C" strokeWidth="1.5" strokeOpacity="0.8" />
              <line x1="135" y1="60" x2="100" y2="105" stroke="#38BDF8" strokeWidth="1.2" strokeOpacity="0.7" />
              <line x1="45" y1="75" x2="60" y2="115" stroke="#EC4899" strokeWidth="1" strokeOpacity="0.6" />

              <circle cx="45" cy="75" r="4.5" fill="#FB923C" />
              <circle cx="135" cy="60" r="5" fill="#38BDF8" />
              <circle cx="100" cy="105" r="4.5" fill="#10B981" />
              <circle cx="60" cy="115" r="3.5" fill="#EC4899" />
            </svg>
          </div>
        </section>

        {/* ==========================================================================
            SECTION 03: OUR APPROACH
            ========================================================================== */}
        <section className="about-approach-section">
          <div className="approach-left">
            <span className="section-num-tag">03 / OUR APPROACH</span>
            <h2 className="section-title">
              A 3D galaxy for your codebase.
            </h2>
            <p className="about-hero-sub">
              Astrograph combines advanced code analysis, graph algorithms, and AI to create an interactive 3D visualization of your repository. Files, classes, functions, and directories become celestial nodes, connected by meaningful dependency relationships.
            </p>
          </div>

          <div className="approach-steps-grid">
            <div className="approach-step-card">
              <div className="approach-icon-circle">
                <Network size={22} />
              </div>
              <h4 className="approach-step-title">AST Parsing</h4>
              <p className="approach-step-desc">Extract structure and symbols using Tree-sitter.</p>
            </div>

            <div className="approach-step-card">
              <div className="approach-icon-circle">
                <BarChart3 size={22} />
              </div>
              <h4 className="approach-step-title">Graph Algorithms</h4>
              <p className="approach-step-desc">Build intelligent dependency graphs with NetworkX.</p>
            </div>

            <div className="approach-step-card">
              <div className="approach-icon-circle">
                <Sparkles size={22} />
              </div>
              <h4 className="approach-step-title">AI Insights</h4>
              <p className="approach-step-desc">Get natural language explanations and summaries.</p>
            </div>

            <div className="approach-step-card">
              <div className="approach-icon-circle">
                <Box size={22} />
              </div>
              <h4 className="approach-step-title">3D Visualization</h4>
              <p className="approach-step-desc">Explore your codebase as an interactive galaxy with Three.js.</p>
            </div>
          </div>
        </section>

        {/* ==========================================================================
            SECTION 04: TECHNOLOGY STACK
            ========================================================================== */}
        <section className="about-tech-section">
          <div className="tech-left">
            <span className="section-num-tag">04 / TECHNOLOGY STACK</span>
            <h2 className="section-title">
              Built with modern tools.
            </h2>
            <p className="about-hero-sub">
              A combination of powerful technologies to parse, analyze, visualize, and understand codebases.
            </p>
          </div>

          {/* 10-Item Technology Grid (2 rows x 5 items) */}
          <div className="tech-grid">
            {/* 1. React */}
            <div className="tech-card">
              <div className="tech-icon-wrapper text-cyan-400">
                <Code2 size={24} />
              </div>
              <h5 className="tech-name">React</h5>
              <span className="tech-category">Frontend</span>
            </div>

            {/* 2. Three.js */}
            <div className="tech-card">
              <div className="tech-icon-wrapper text-white">
                <Box size={24} />
              </div>
              <h5 className="tech-name">Three.js</h5>
              <span className="tech-category">3D Visualization</span>
            </div>

            {/* 3. Node.js */}
            <div className="tech-card">
              <div className="tech-icon-wrapper text-emerald-400">
                <Server size={24} />
              </div>
              <h5 className="tech-name">Node.js</h5>
              <span className="tech-category">Backend</span>
            </div>

            {/* 4. Express.js */}
            <div className="tech-card">
              <div className="tech-icon-wrapper text-gray-300">
                <Terminal size={24} />
              </div>
              <h5 className="tech-name">Express.js</h5>
              <span className="tech-category">API Layer</span>
            </div>

            {/* 5. PostgreSQL */}
            <div className="tech-card">
              <div className="tech-icon-wrapper text-sky-400">
                <Database size={24} />
              </div>
              <h5 className="tech-name">PostgreSQL</h5>
              <span className="tech-category">Database</span>
            </div>

            {/* 6. Tree-sitter */}
            <div className="tech-card">
              <div className="tech-icon-wrapper text-amber-400">
                <GitFork size={24} />
              </div>
              <h5 className="tech-name">Tree-sitter</h5>
              <span className="tech-category">AST Parsing</span>
            </div>

            {/* 7. Python */}
            <div className="tech-card">
              <div className="tech-icon-wrapper text-blue-400">
                <FileCode size={24} />
              </div>
              <h5 className="tech-name">Python</h5>
              <span className="tech-category">Analysis Scripts</span>
            </div>

            {/* 8. NetworkX */}
            <div className="tech-card">
              <div className="tech-icon-wrapper text-[#FB923C]">
                <Network size={24} />
              </div>
              <h5 className="tech-name">NetworkX</h5>
              <span className="tech-category">Graph Construction</span>
            </div>

            {/* 9. PageRank */}
            <div className="tech-card">
              <div className="tech-icon-wrapper text-[#F59E0B]">
                <BarChart3 size={24} />
              </div>
              <h5 className="tech-name">PageRank</h5>
              <span className="tech-category">Centrality Analysis</span>
            </div>

            {/* 10. Louvain */}
            <div className="tech-card">
              <div className="tech-icon-wrapper text-[#FDBA74]">
                <Share2 size={24} />
              </div>
              <h5 className="tech-name">Louvain</h5>
              <span className="tech-category">Community Detection</span>
            </div>
          </div>
        </section>

        {/* ==========================================================================
            SECTION 05: OUR TEAM
            ========================================================================== */}
        <section className="about-team-section">
          <div className="team-header-block">
            <span className="section-num-tag">05 / OUR TEAM</span>
            <h2 className="section-title">Teen Magloo</h2>
            <p className="about-hero-sub">
              A passionate group of developers building the next generation of codebase intelligence.
            </p>
          </div>

          <div className="team-cards-grid">
            {/* Namish Gupta */}
            <div className="team-member-card">
              <div className="celestial-orb orb-namish" />
              <div className="member-info">
                <h4 className="member-name">Namish Gupta</h4>
                <span className="member-reg">Reg. No: 20253168</span>
                <span className="member-role">Frontend & Visualization</span>
              </div>
              <div className="member-tags">
                <span className="member-tag">UI/UX</span>
                <span className="member-tag">3D Visualization</span>
                <span className="member-tag">Frontend</span>
              </div>
            </div>

            {/* Shashwat Agarwal */}
            <div className="team-member-card">
              <div className="celestial-orb orb-shashwat" />
              <div className="member-info">
                <h4 className="member-name">Shashwat Agarwal</h4>
                <span className="member-reg">Reg. No: 20253260</span>
                <span className="member-role">Backend + AI</span>
              </div>
              <div className="member-tags">
                <span className="member-tag">Backend</span>
                <span className="member-tag">AI Integration</span>
                <span className="member-tag">API Development</span>
              </div>
            </div>

            {/* Harsh Navlakha */}
            <div className="team-member-card">
              <div className="celestial-orb orb-harsh" />
              <div className="member-info">
                <h4 className="member-name">Harsh Navlakha</h4>
                <span className="member-reg">Reg. No: 20253113</span>
                <span className="member-role">Backend + Graph Making + Database</span>
              </div>
              <div className="member-tags">
                <span className="member-tag">Graph Algorithms</span>
                <span className="member-tag">Backend</span>
                <span className="member-tag">Database</span>
              </div>
            </div>
          </div>
        </section>

        {/* ==========================================================================
            SECTION 06: HACKATHON
            ========================================================================== */}
        <section className="about-hackathon-section">
          <div className="hackathon-left">
            <span className="section-num-tag">06 / HACKATHON</span>
            <h2 className="section-title">Built for Code Sangam</h2>
            <p className="about-hero-sub">
              Astrograph is our submission for Code Sangam, a hackathon that brings together innovative minds to build for a better, more connected developer ecosystem.
            </p>
          </div>

          {/* Center Brand Emblem Card */}
          <div className="hackathon-logo-card">
            <div className="code-sangam-brand">
              <svg className="cs-symbol" viewBox="0 0 100 100" fill="none">
                <defs>
                  <linearGradient id="csGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#FFFFFF" />
                    <stop offset="45%" stopColor="#FB923C" />
                    <stop offset="100%" stopColor="#EA580C" />
                  </linearGradient>
                </defs>
                {/* Interlocking geometric CS infinity emblem */}
                <path
                  d="M50 20 C32 20, 18 34, 18 50 C18 66, 32 80, 50 80 C68 80, 82 66, 82 50 C82 42, 78 36, 72 32"
                  stroke="url(#csGrad)"
                  strokeWidth="11"
                  strokeLinecap="round"
                />
                <path
                  d="M38 38 C42 34, 46 32, 50 32 C60 32, 68 40, 68 50 C68 60, 60 68, 50 68 C40 68, 32 60, 32 50"
                  stroke="#FB923C"
                  strokeWidth="7"
                  strokeLinecap="round"
                />
              </svg>
              <div className="cs-text-group">
                <span className="cs-word-code">Code</span>
                <span className="cs-word-sangam">Sangam</span>
              </div>
            </div>
          </div>

          <div className="hackathon-right">
            A hackathon celebrating creativity, collaboration, and technology. We are excited to be part of this community and showcase Astrograph.
          </div>
        </section>

        {/* ==========================================================================
            BOTTOM CALLOUT SECTION (Only Back to Home per instruction)
            ========================================================================== */}
        <section className="about-bottom-callout">
          <h2 className="callout-title">
            Let's explore a more connected developer universe.
          </h2>
          <p className="callout-sub">
            Turn any repository into an interactive knowledge galaxy.
          </p>

          <button
            type="button"
            onClick={() => {
              window.scrollTo({ top: 0, behavior: 'smooth' });
              navigate('/');
            }}
            className="btn-secondary-home"
            style={{ padding: '0.95rem 2.5rem', fontSize: '0.95rem' }}
          >
            <ArrowLeft size={16} />
            <span>Back to Home</span>
          </button>
        </section>

      </main>
    </div>
  );
}

