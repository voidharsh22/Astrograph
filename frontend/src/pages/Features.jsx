import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  Share2,
  GitFork,
  Bot,
  AlertTriangle,
  Search,
  FolderGit2,
  Layers,
  Cpu,
  Zap,
  Network,
  Activity,
  CheckCircle2,
  Terminal,
  Database,
  ArrowRight,
  Server,
  ShieldCheck,
  Sparkles,
  Send,
  ZoomIn,
  ZoomOut,
  Maximize2,
  GitBranch,
  X,
  Code2
} from 'lucide-react';
import { RingedPlanetLogo } from './Landing.jsx';
import '../styles/features.css';

export default function Features() {
  const navigate = useNavigate();

  return (
    <div className="features-page">
      
      {/* Background Atmosphere */}
      <div className="features-backdrop">
        <div className="features-planet-horizon" />
        <div className="features-planet-horizon-secondary" />
        <div className="features-bottom-horizon" />
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
          <span className="nav-link nav-link--active">Features</span>
          <Link to="/about" className="nav-link">About</Link>
        </nav>

        <div className="nav-pill-words">
          <span>Visualize</span>
          <span>·</span>
          <span>Understand</span>
          <span>·</span>
          <span>Build Better</span>
        </div>
      </header>

      {/* Main Content Container with generous, unclustered spacing */}
      <main className="features-container">
        
        {/* Top Hero Section */}
        <section className="features-hero">
          <div className="features-hero-left">
            <span className="hero-eyebrow">
              [ ASTROGRAPH CAPABILITIES ]
            </span>

            <h1 className="features-hero-title">
              Every codebase has a universe.
              <em>Discover how it connects.</em>
            </h1>

            <p className="features-hero-sub">
              From structural analysis to intelligent dependency exploration, Astrograph turns unfamiliar repositories into systems you can see, understand, and navigate.
            </p>

            {/* Actions: ONLY Back to Home (per user instruction) */}
            <div className="features-actions-row">
              <button
                type="button"
                onClick={() => navigate('/')}
                className="btn-secondary-home"
              >
                <ArrowLeft size={16} />
                <span>Back to Home</span>
              </button>
            </div>
          </div>

          {/* Top Hero Interactive Preview Mockup */}
          <div className="features-hero-preview">
            {/* Top Toolbar */}
            <div className="preview-top-bar">
              <div className="preview-legend-pills">
                <span className="pill-item"><span className="dot dot-cyan" /> Directory</span>
                <span className="pill-item"><span className="dot dot-gray" /> File</span>
                <span className="pill-item"><span className="dot dot-purple" /> Class</span>
                <span className="pill-item"><span className="dot dot-yellow" /> Function</span>
              </div>
              <div className="preview-actions">
                <Search size={13} className="text-gray-400 hover:text-white cursor-pointer" />
                <ZoomIn size={13} className="text-gray-400 hover:text-white cursor-pointer" />
                <Maximize2 size={13} className="text-gray-400 hover:text-white cursor-pointer" />
              </div>
            </div>

            {/* Split Preview: Graph Canvas on Left, Inspector on Right */}
            <div className="preview-body-grid">
              {/* Visual graph snippet */}
              <div className="preview-canvas-box">
                <svg className="w-full h-full" viewBox="0 0 240 180">
                  <defs>
                    <radialGradient id="sunGlowHero" cx="50%" cy="50%" r="50%">
                      <stop offset="0%" stopColor="#FB923C" stopOpacity="0.8" />
                      <stop offset="40%" stopColor="#F59E0B" stopOpacity="0.3" />
                      <stop offset="100%" stopColor="#FB923C" stopOpacity="0" />
                    </radialGradient>
                    <radialGradient id="nodeGlow" cx="50%" cy="50%" r="50%">
                      <stop offset="0%" stopColor="#38BDF8" stopOpacity="0.8" />
                      <stop offset="100%" stopColor="#38BDF8" stopOpacity="0" />
                    </radialGradient>
                  </defs>

                  {/* Edges */}
                  <line x1="120" y1="90" x2="45" y2="40" stroke="#FB923C" strokeWidth="1" strokeOpacity="0.45" />
                  <line x1="120" y1="90" x2="195" y2="45" stroke="#FB923C" strokeWidth="1" strokeOpacity="0.45" />
                  <line x1="120" y1="90" x2="60" y2="140" stroke="#FB923C" strokeWidth="1" strokeOpacity="0.45" />
                  <line x1="120" y1="90" x2="190" y2="135" stroke="#FB923C" strokeWidth="1" strokeOpacity="0.45" />
                  <line x1="120" y1="90" x2="120" y2="25" stroke="#FB923C" strokeWidth="1" strokeOpacity="0.45" />
                  <line x1="45" y1="40" x2="120" y2="25" stroke="#38BDF8" strokeWidth="0.8" strokeOpacity="0.3" />
                  <line x1="195" y1="45" x2="120" y2="25" stroke="#A855F7" strokeWidth="0.8" strokeOpacity="0.3" />

                  {/* Peripheral Nodes */}
                  <circle cx="45" cy="40" r="5" fill="#38BDF8" />
                  <circle cx="195" cy="45" r="5.5" fill="#10B981" />
                  <circle cx="60" cy="140" r="5" fill="#A855F7" />
                  <circle cx="190" cy="135" r="5.5" fill="#F59E0B" />
                  <circle cx="120" cy="25" r="4.5" fill="#EC4899" />
                  <circle cx="25" cy="90" r="3.5" fill="#94A3B8" />

                  {/* Central Pulsing Core Node */}
                  <circle cx="120" cy="90" r="22" fill="url(#sunGlowHero)" />
                  <circle cx="120" cy="90" r="9" fill="#FB923C" />
                  <circle cx="120" cy="90" r="4" fill="#FFF7ED" />
                  
                  {/* Central Label Pill */}
                  <rect x="85" y="105" width="70" height="15" rx="7.5" fill="#111827" stroke="#FB923C" strokeWidth="0.8" strokeOpacity="0.7" />
                  <text x="120" y="116" fill="#FFF7ED" fontSize="7.5" textAnchor="middle" fontFamily="monospace" fontWeight="bold">UserService</text>
                </svg>
              </div>

              {/* Inspector Snippet */}
              <div className="preview-inspector-card">
                <div>
                  <div className="flex items-center justify-between pb-1.5 border-b border-white/10">
                    <div className="flex items-center gap-1.5">
                      <Code2 size={13} className="text-[#FB923C]" />
                      <span className="text-white font-bold text-xs">UserService</span>
                    </div>
                    <span className="text-[9px] font-mono text-[#FB923C] bg-[#FB923C]/10 border border-[#FB923C]/30 px-1.5 py-0.5 rounded">Class</span>
                  </div>
                  
                  <div className="text-[10px] text-gray-400 font-mono mt-1.5 truncate">
                    src/services/UserService.ts
                  </div>

                  <div className="grid grid-cols-2 gap-x-2 gap-y-1.5 mt-2.5 font-mono text-[10px]">
                    <div className="text-gray-400">Lines of Code <span className="text-white font-medium block">320</span></div>
                    <div className="text-gray-400">Complexity <span className="text-white font-medium block">12</span></div>
                    <div className="text-gray-400">PageRank <span className="text-[#FB923C] font-semibold block">0.18</span></div>
                    <div className="text-gray-400">Cluster <span className="text-[#FDBA74] font-semibold block">3</span></div>
                  </div>
                </div>

                <div className="border-t border-white/10 pt-2 font-mono text-[10px]">
                  <div className="text-gray-400 mb-1 uppercase tracking-wider text-[9px] font-semibold">Dependencies</div>
                  <div className="space-y-0.5 text-gray-300">
                    <div className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> AuthService</div>
                    <div className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-blue-400" /> Database</div>
                    <div className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-amber-400" /> Logger</div>
                    <div className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 rounded-full bg-purple-400" /> Config</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 6-Item Capability Quick Bar */}
        <section className="features-quick-strip">
          <div className="quick-cap-item">
            <div className="quick-cap-icon"><Network size={18} /></div>
            <h4 className="quick-cap-title">3D Visualization</h4>
            <p className="quick-cap-desc">Explore your codebase as an interactive galaxy.</p>
          </div>
          <div className="quick-cap-item">
            <div className="quick-cap-icon"><GitFork size={18} /></div>
            <h4 className="quick-cap-title">Dependency Analysis</h4>
            <p className="quick-cap-desc">Understand relationships and architecture.</p>
          </div>
          <div className="quick-cap-item">
            <div className="quick-cap-icon"><Bot size={18} /></div>
            <h4 className="quick-cap-title">AI Assistant</h4>
            <p className="quick-cap-desc">Ask questions and get intelligent insights.</p>
          </div>
          <div className="quick-cap-item">
            <div className="quick-cap-icon"><AlertTriangle size={18} /></div>
            <h4 className="quick-cap-title">Impact Analysis</h4>
            <p className="quick-cap-desc">See what could break before you merge.</p>
          </div>
          <div className="quick-cap-item">
            <div className="quick-cap-icon"><Search size={18} /></div>
            <h4 className="quick-cap-title">Powerful Search</h4>
            <p className="quick-cap-desc">Find files, symbols and patterns instantly.</p>
          </div>
          <div className="quick-cap-item">
            <div className="quick-cap-icon"><FolderGit2 size={18} /></div>
            <h4 className="quick-cap-title">Repository Workspace</h4>
            <p className="quick-cap-desc">Everything you need in one place.</p>
          </div>
        </section>

        {/* 5 Stacked Feature Modules (Spacious & Unclustered) */}
        <section className="feature-showcase-stack">
          
          {/* Module 01: Spatial Code Intelligence */}
          <div className="feature-module-card">
            <div className="module-left-text">
              <span className="module-num-tag">01 / SPATIAL CODE INTELLIGENCE</span>
              <h3 className="module-title">Your architecture, mapped across the stars.</h3>
              <p className="module-desc">
                Files, classes, functions and directories become celestial nodes, spatially organized to reveal the true structure of your codebase. Node size shows importance, colors indicate type and communities, and edges show dependency relationships.
              </p>
              <div className="module-pill-chips">
                <span className="module-chip"><Layers size={13} /> Hierarchical exploration</span>
                <span className="module-chip"><Share2 size={13} /> Community detection</span>
                <span className="module-chip"><Zap size={13} /> Interactive navigation</span>
              </div>
            </div>

            <div className="module-right-visual">
              <div className="module-graph-container">
                {/* Header Tab & Legend */}
                <div className="graph-top-header">
                  <div className="graph-badge-tag">
                    <Network size={14} /> Code Graph (3D)
                  </div>
                  <div className="graph-legend-row">
                    <span className="graph-legend-item"><span className="dot dot-cyan" /> Directories</span>
                    <span className="graph-legend-item"><span className="dot dot-yellow" /> Files</span>
                    <span className="graph-legend-item"><span className="dot" style={{ backgroundColor: '#10B981' }} /> Classes</span>
                    <span className="graph-legend-item"><span className="dot dot-purple" /> Functions</span>
                    <span className="graph-legend-item"><span className="dot" style={{ backgroundColor: '#EC4899' }} /> External</span>
                  </div>
                </div>

                {/* Rich Constellation SVG */}
                <div style={{ position: 'relative', width: '100%', height: '210px', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0.5rem 0' }}>
                  <svg style={{ width: '100%', height: '100%' }} viewBox="0 0 460 190">
                    <defs>
                      <radialGradient id="nebulaCore" cx="50%" cy="50%" r="50%">
                        <stop offset="0%" stopColor="#FB923C" stopOpacity="0.4" />
                        <stop offset="60%" stopColor="#F59E0B" stopOpacity="0.1" />
                        <stop offset="100%" stopColor="#0B0F19" stopOpacity="0" />
                      </radialGradient>
                    </defs>

                    {/* Nebula background ring */}
                    <ellipse cx="230" cy="95" rx="160" ry="75" fill="url(#nebulaCore)" />

                    {/* Interconnected constellation edges */}
                    <g stroke="#FB923C" strokeOpacity="0.35" strokeWidth="0.9">
                      <line x1="230" y1="95" x2="110" y2="50" />
                      <line x1="230" y1="95" x2="350" y2="50" />
                      <line x1="230" y1="95" x2="120" y2="140" />
                      <line x1="230" y1="95" x2="340" y2="140" />
                      <line x1="230" y1="95" x2="230" y2="25" />
                      <line x1="230" y1="95" x2="230" y2="165" />
                      <line x1="110" y1="50" x2="50" y2="85" />
                      <line x1="110" y1="50" x2="70" y2="25" />
                      <line x1="350" y1="50" x2="410" y2="85" />
                      <line x1="350" y1="50" x2="390" y2="25" />
                      <line x1="120" y1="140" x2="60" y2="160" />
                      <line x1="340" y1="140" x2="400" y2="160" />
                      <line x1="110" y1="50" x2="230" y2="25" stroke="#38BDF8" strokeOpacity="0.4" />
                      <line x1="350" y1="50" x2="230" y2="25" stroke="#A855F7" strokeOpacity="0.4" />
                    </g>

                    {/* Node halos and circles */}
                    <circle cx="230" cy="95" r="16" fill="#FB923C" fillOpacity="0.25" />
                    <circle cx="230" cy="95" r="9" fill="#FB923C" />
                    <circle cx="230" cy="95" r="4" fill="#FFF7ED" />

                    {/* Clusters */}
                    <circle cx="110" cy="50" r="7" fill="#06B6D4" />
                    <circle cx="70" cy="25" r="5" fill="#38BDF8" />
                    <circle cx="50" cy="85" r="4.5" fill="#10B981" />
                    
                    <circle cx="350" cy="50" r="7.5" fill="#A855F7" />
                    <circle cx="390" cy="25" r="5" fill="#C084FC" />
                    <circle cx="410" cy="85" r="4.5" fill="#EC4899" />

                    <circle cx="120" cy="140" r="6.5" fill="#F59E0B" />
                    <circle cx="60" cy="160" r="4" fill="#FBBF24" />

                    <circle cx="340" cy="140" r="6.5" fill="#10B981" />
                    <circle cx="400" cy="160" r="4" fill="#34D399" />

                    <circle cx="230" cy="25" r="5" fill="#EC4899" />
                    <circle cx="230" cy="165" r="4.5" fill="#94A3B8" />

                    {/* Node labels */}
                    <text x="230" y="118" fill="#FFF7ED" fontSize="8" textAnchor="middle" fontFamily="monospace" fontWeight="600">CoreService</text>
                    <text x="110" y="38" fill="#94A3B8" fontSize="7" textAnchor="middle" fontFamily="monospace">routes/api</text>
                    <text x="350" y="38" fill="#94A3B8" fontSize="7" textAnchor="middle" fontFamily="monospace">models/user</text>
                  </svg>
                </div>
              </div>
            </div>
          </div>

          {/* Module 02: Flow Telemetry (Centered, Attractive Boxes) */}
          <div className="feature-module-card">
            <div className="module-left-text">
              <span className="module-num-tag">02 / FLOW TELEMETRY</span>
              <h3 className="module-title">Follow the flow. Find the bottleneck.</h3>
              <p className="module-desc">
                Visualize directed dependencies and trace execution paths through your application, from entry points to databases. Identify critical paths and potential performance bottlenecks.
              </p>
              <div className="module-pill-chips">
                <span className="module-chip"><Activity size={13} /> Directed edges</span>
                <span className="module-chip"><Zap size={13} /> Execution paths</span>
                <span className="module-chip"><Share2 size={13} /> Flow tracing</span>
              </div>
            </div>

            <div className="module-right-visual">
              <div className="module-flow-container">
                {/* Pipeline Sequence Nodes */}
                <div className="flow-pipeline-row">
                  <div className="flow-node-box">
                    <div className="flow-node-icon">
                      <Server size={19} color="#38BDF8" />
                    </div>
                    <div className="flow-node-title">HTTP Router</div>
                    <div className="flow-node-subtitle">Entrypoint</div>
                  </div>

                  <ArrowRight size={16} className="flow-arrow-icon" />

                  <div className="flow-node-box flow-node-box--active">
                    <div className="flow-node-icon">
                      <Cpu size={19} color="#FB923C" />
                    </div>
                    <div className="flow-node-title" style={{ color: '#FB923C' }}>Service Engine</div>
                    <div className="flow-node-subtitle flow-node-subtitle--active">Processing</div>
                  </div>

                  <ArrowRight size={16} className="flow-arrow-icon" />

                  <div className="flow-node-box">
                    <div className="flow-node-icon">
                      <Layers size={19} color="#FBBF24" />
                    </div>
                    <div className="flow-node-title">Data Schema</div>
                    <div className="flow-node-subtitle">Validation</div>
                  </div>

                  <ArrowRight size={16} className="flow-arrow-icon" />

                  <div className="flow-node-box">
                    <div className="flow-node-icon">
                      <Database size={19} color="#C084FC" />
                    </div>
                    <div className="flow-node-title">Database</div>
                    <div className="flow-node-subtitle">Storage</div>
                  </div>
                </div>

                {/* Execution Path Timing Metrics Card */}
                <div className="flow-metrics-card">
                  <div className="flow-metrics-header">
                    <span>Execution Path Telemetry</span>
                    <span className="flow-metrics-status">Normal · Optimal</span>
                  </div>
                  <div className="flow-metrics-list">
                    <div className="flow-metrics-row">
                      <span>1. HTTP Router → Middleware</span>
                      <span>2ms</span>
                    </div>
                    <div className="flow-metrics-row">
                      <span style={{ color: '#FFF7ED', fontWeight: 600 }}>2. UserService [Core Logic]</span>
                      <span>5ms</span>
                    </div>
                    <div className="flow-metrics-row">
                      <span>3. PostgreSQL Database Query</span>
                      <span>12ms</span>
                    </div>
                  </div>
                  <div className="flow-metrics-total">
                    <span>Total Latency</span>
                    <span>19ms</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Module 03: AI-Powered Understanding (Sunset Orange Button & Centered Chat) */}
          <div className="feature-module-card">
            <div className="module-left-text">
              <span className="module-num-tag">03 / AI-POWERED UNDERSTANDING</span>
              <h3 className="module-title">Ask questions. Understand the architecture.</h3>
              <p className="module-desc">
                Get natural language explanations, architectural insights, and guided exploration. The AI assistant can explain workflows, summarize modules, and highlight relevant nodes in the 3D visualization.
              </p>
              <div className="module-pill-chips">
                <span className="module-chip"><Bot size={13} /> Natural language Q&A</span>
                <span className="module-chip"><Sparkles size={13} /> Architecture insights</span>
                <span className="module-chip"><Share2 size={13} /> Camera navigation</span>
              </div>
            </div>

            <div className="module-right-visual">
              <div className="module-ai-container">
                {/* Left Sub-card: Interactive AI Chat */}
                <div className="ai-chat-column">
                  <div className="ai-header-badge">
                    <Bot size={17} />
                    <span>Astral AI Assistant</span>
                  </div>

                  {/* User Bubble */}
                  <div className="ai-bubble-user">
                    Which modules depend on UserService?
                  </div>

                  {/* AI Response Bubble */}
                  <div className="ai-bubble-response">
                    <div style={{ color: '#FFF7ED', fontWeight: 600, fontSize: '0.74rem' }}>
                      UserService is utilized by <span style={{ color: '#FB923C' }}>4 core modules</span>:
                    </div>
                    <ul className="ai-response-list">
                      <li>
                        <span>•</span>
                        <span className="mod-name">AuthService</span>
                        <span className="mod-path">(src/services/auth.ts)</span>
                      </li>
                      <li>
                        <span>•</span>
                        <span className="mod-name">ProfileController</span>
                        <span className="mod-path">(src/controllers/profile.ts)</span>
                      </li>
                      <li>
                        <span>•</span>
                        <span className="mod-name">NotificationService</span>
                        <span className="mod-path">(src/services/notification.ts)</span>
                      </li>
                      <li>
                        <span>•</span>
                        <span className="mod-name">AdminController</span>
                        <span className="mod-path">(src/controllers/admin.ts)</span>
                      </li>
                    </ul>

                    {/* MATCHING SUNSET ORANGE SCHEMA BUTTON */}
                    <button type="button" className="schema-btn-sunset" style={{ marginTop: '0.35rem' }}>
                      <span>Highlight in graph</span>
                      <ArrowRight size={13} />
                    </button>
                  </div>

                  {/* Mock Search Input Bar */}
                  <div className="ai-input-bar">
                    <input
                      type="text"
                      readOnly
                      placeholder="Ask about your codebase..."
                      className="ai-input-field"
                    />
                    <button type="button" className="ai-send-btn" aria-label="Send query">
                      <Send size={13} />
                    </button>
                  </div>
                </div>

                {/* Right Sub-card: Highlighted Satellite Constellation Preview */}
                <div className="ai-graph-preview-box">
                  <svg style={{ width: '100%', height: '140px' }} viewBox="0 0 140 140">
                    <circle cx="70" cy="70" r="18" fill="#FB923C" fillOpacity="0.25" />
                    <circle cx="70" cy="70" r="8" fill="#FB923C" />
                    <circle cx="70" cy="70" r="3.5" fill="#FFF7ED" />
                    
                    {/* Lines to 4 modules */}
                    <line x1="70" y1="70" x2="30" y2="35" stroke="#38BDF8" strokeWidth="1.2" strokeDasharray="3 3" />
                    <line x1="70" y1="70" x2="110" y2="35" stroke="#EC4899" strokeWidth="1.2" strokeDasharray="3 3" />
                    <line x1="70" y1="70" x2="30" y2="105" stroke="#10B981" strokeWidth="1.2" strokeDasharray="3 3" />
                    <line x1="70" y1="70" x2="110" y2="105" stroke="#F59E0B" strokeWidth="1.2" strokeDasharray="3 3" />

                    <circle cx="30" cy="35" r="5" fill="#38BDF8" />
                    <circle cx="110" cy="35" r="5" fill="#EC4899" />
                    <circle cx="30" cy="105" r="5" fill="#10B981" />
                    <circle cx="110" cy="105" r="5" fill="#F59E0B" />

                    <text x="70" y="94" fill="#FFF7ED" fontSize="7.5" textAnchor="middle" fontFamily="monospace" fontWeight="bold">UserService</text>
                  </svg>
                  <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.65rem', color: '#9CA3AF', marginTop: '0.25rem' }}>
                    Active Subgraph Focus
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Module 04: Change Impact Intelligence (Sunset Orange Button & Centered Blast) */}
          <div className="feature-module-card">
            <div className="module-left-text">
              <span className="module-num-tag">04 / CHANGE IMPACT INTELLIGENCE</span>
              <h3 className="module-title">Know what a change could affect.</h3>
              <p className="module-desc">
                Analyze incoming and outgoing dependencies to identify potentially affected files, functions, and services before making a change.
              </p>
              <div className="module-pill-chips">
                <span className="module-chip"><CheckCircle2 size={13} /> Direct dependents</span>
                <span className="module-chip"><Activity size={13} /> Transitive impact</span>
                <span className="module-chip"><ShieldCheck size={13} /> Risk analysis</span>
              </div>
            </div>

            <div className="module-right-visual">
              <div className="module-impact-container">
                {/* Center Radial Blast Graphic */}
                <div className="impact-visual-col">
                  <div className="impact-legend-row">
                    <span className="impact-legend-item"><span className="dot" style={{ backgroundColor: '#EF4444' }} /> Selected</span>
                    <span className="impact-legend-item"><span className="dot" style={{ backgroundColor: '#FB923C' }} /> Direct</span>
                    <span className="impact-legend-item"><span className="dot" style={{ backgroundColor: '#FBBF24' }} /> Transitive</span>
                    <span className="impact-legend-item"><span className="dot dot-gray" /> Affected</span>
                  </div>

                  <svg style={{ width: '100%', maxWidth: '240px', height: '140px' }} viewBox="0 0 200 130">
                    {/* Concentric blast rings */}
                    <circle cx="100" cy="65" r="48" fill="none" stroke="#EF4444" strokeWidth="0.8" strokeDasharray="3 3" opacity="0.35" />
                    <circle cx="100" cy="65" r="28" fill="none" stroke="#EF4444" strokeWidth="1" strokeDasharray="2 2" opacity="0.55" />
                    
                    {/* Radial Impact rays */}
                    <line x1="100" y1="65" x2="35" y2="35" stroke="#EF4444" strokeWidth="1" strokeDasharray="2 2" />
                    <line x1="100" y1="65" x2="165" y2="35" stroke="#EF4444" strokeWidth="1" strokeDasharray="2 2" />
                    <line x1="100" y1="65" x2="40" y2="95" stroke="#EF4444" strokeWidth="1" strokeDasharray="2 2" />
                    <line x1="100" y1="65" x2="160" y2="100" stroke="#EF4444" strokeWidth="1" strokeDasharray="2 2" />
                    <line x1="100" y1="65" x2="100" y2="15" stroke="#EF4444" strokeWidth="1" strokeDasharray="2 2" />

                    {/* Nodes */}
                    <circle cx="100" cy="65" r="18" fill="#EF4444" fillOpacity="0.25" />
                    <circle cx="100" cy="65" r="9" fill="#EF4444" />
                    <circle cx="100" cy="65" r="4" fill="#FFF" />

                    <circle cx="35" cy="35" r="5" fill="#FB923C" />
                    <circle cx="165" cy="35" r="5.5" fill="#FB923C" />
                    <circle cx="40" cy="95" r="4.5" fill="#FBBF24" />
                    <circle cx="160" cy="100" r="4.5" fill="#FBBF24" />
                    <circle cx="100" cy="15" r="4" fill="#94A3B8" />

                    <text x="100" y="88" fill="#FFF7ED" fontSize="7.5" textAnchor="middle" fontFamily="monospace" fontWeight="bold">updateUser()</text>
                  </svg>
                </div>

                {/* Impact stats card */}
                <div className="impact-card-box">
                  <div className="impact-card-header">
                    Impact Radius Summary
                  </div>
                  <div className="impact-stats-list">
                    <div className="impact-stats-row">
                      <span style={{ color: '#9CA3AF' }}>Direct dependents</span>
                      <span style={{ color: '#F87171' }}>12 files</span>
                    </div>
                    <div className="impact-stats-row">
                      <span style={{ color: '#9CA3AF' }}>Transitive dependents</span>
                      <span style={{ color: '#FB923C' }}>28 files</span>
                    </div>
                    <div className="impact-stats-row">
                      <span style={{ color: '#9CA3AF' }}>External modules</span>
                      <span style={{ color: '#FDBA74' }}>6 packages</span>
                    </div>
                  </div>

                  {/* MATCHING SUNSET ORANGE SCHEMA BUTTON */}
                  <button type="button" className="schema-btn-sunset impact-btn-full">
                    <span>View affected files</span>
                    <ArrowRight size={13} />
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Module 05: Indexing & Analysis Pipeline */}
          <div className="feature-module-card">
            <div className="module-left-text">
              <span className="module-num-tag">05 / INDEXING & ANALYSIS PIPELINE</span>
              <h3 className="module-title">From raw repository to architectural intelligence.</h3>
              <p className="module-desc">
                A powerful analysis pipeline that parses your code, extracts symbols and dependencies, computes graph metrics, and builds an interactive visualization.
              </p>
              <div className="module-pill-chips">
                <span className="module-chip"><Terminal size={13} /> Tree-sitter AST</span>
                <span className="module-chip"><Network size={13} /> NetworkX Graph</span>
                <span className="module-chip"><Database size={13} /> Louvain Communities</span>
              </div>
            </div>

            <div className="module-right-visual">
              <div className="module-pipeline-container">
                {/* Header Bar */}
                <div className="pipeline-header-bar">
                  <div className="pipeline-tabs">
                    <span className="pipeline-tab--active">Indexing Pipeline</span>
                    <span className="pipeline-tab">Live Logs</span>
                    <span className="pipeline-tab">Graph Telemetry</span>
                  </div>

                  <div className="pipeline-repo-pill">
                    <span>Target:</span>
                    <span className="pipeline-repo-name">vercel/next.js</span>
                    <span className="pipeline-branch-chip">
                      <GitBranch size={11} /> main
                    </span>
                  </div>
                </div>

                {/* Pipeline progress split */}
                <div className="pipeline-content-grid">
                  {/* 7-Step checklist */}
                  <div className="pipeline-checklist">
                    <div className="pipeline-check-item">
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <CheckCircle2 size={13} color="#34D399" />
                        <span>[1/7] Repository ingestion</span>
                      </span>
                      <span style={{ color: '#34D399', fontWeight: 600 }}>Completed (2.4s)</span>
                    </div>

                    <div className="pipeline-check-item">
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <CheckCircle2 size={13} color="#34D399" />
                        <span>[2/7] Parsing with Tree-sitter</span>
                      </span>
                      <span style={{ color: '#34D399', fontWeight: 600 }}>Completed (8.7s)</span>
                    </div>

                    <div className="pipeline-check-item">
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <CheckCircle2 size={13} color="#34D399" />
                        <span>[3/7] Extracting symbols & dependencies</span>
                      </span>
                      <span style={{ color: '#34D399', fontWeight: 600 }}>Completed (6.1s)</span>
                    </div>

                    <div className="pipeline-check-item">
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <CheckCircle2 size={13} color="#34D399" />
                        <span>[4/7] Graph construction (NetworkX)</span>
                      </span>
                      <span style={{ color: '#34D399', fontWeight: 600 }}>Completed (3.2s)</span>
                    </div>

                    <div className="pipeline-check-item">
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <CheckCircle2 size={13} color="#34D399" />
                        <span>[5/7] PageRank centrality analysis</span>
                      </span>
                      <span style={{ color: '#34D399', fontWeight: 600 }}>Completed (1.8s)</span>
                    </div>

                    <div className="pipeline-check-item">
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <CheckCircle2 size={13} color="#34D399" />
                        <span>[6/7] Louvain community clustering</span>
                      </span>
                      <span style={{ color: '#34D399', fontWeight: 600 }}>Completed (2.1s)</span>
                    </div>

                    <div className="pipeline-check-item">
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <CheckCircle2 size={13} color="#34D399" />
                        <span>[7/7] Synthesizing 3D galaxy layout</span>
                      </span>
                      <span style={{ color: '#34D399', fontWeight: 600 }}>Ready (1.5s)</span>
                    </div>
                  </div>

                  {/* Right side metric summary panel */}
                  <div className="pipeline-summary-panel">
                    <div className="pipeline-summary-title">
                      Analysis Results
                    </div>
                    <div className="pipeline-metrics-stack">
                      <div className="pipeline-metric-stat">
                        <div className="pipeline-metric-value">12,432</div>
                        <div className="pipeline-metric-label">Nodes</div>
                      </div>
                      <div className="pipeline-metric-stat">
                        <div className="pipeline-metric-value pipeline-metric-value--accent">28,104</div>
                        <div className="pipeline-metric-label">Edges</div>
                      </div>
                      <div className="pipeline-metric-stat">
                        <div className="pipeline-metric-value pipeline-metric-value--peach">1,248</div>
                        <div className="pipeline-metric-label">Classes</div>
                      </div>
                      <div className="pipeline-metric-stat">
                        <div className="pipeline-metric-value" style={{ color: '#38BDF8' }}>45</div>
                        <div className="pipeline-metric-label">Communities</div>
                      </div>
                    </div>
                    <div style={{ fontSize: '0.65rem', color: '#6B7280', paddingTop: '0.5rem', borderTop: '1px solid rgba(255,247,237,0.08)' }}>
                      Execution time: 25.8s
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

        </section>

        {/* Bottom Callout Section: ONLY Back to Home (per user instruction) */}
        <section className="features-bottom-callout">
          <h2 className="callout-title">
            Stop navigating files. Start understanding systems.
          </h2>
          <p className="callout-sub">
            Explore architecture, trace dependencies, and discover the hidden structure of your code.
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

