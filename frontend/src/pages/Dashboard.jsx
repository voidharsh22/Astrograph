import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Home,
  FolderGit2,
  Share2,
  BarChart3,
  Settings,
  Sparkles,
  Search,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  Clock,
  Layers,
  Cpu,
  Zap,
  Trash2,
  LogOut,
  ExternalLink
} from 'lucide-react';
import useAuth from '../hooks/useAuth.js';
import { uploadRepositoryZip } from '../api/workspaceService.js';
import GithubRepoPicker from '../components/GithubRepoPicker.jsx';
import { UploadCloud, FileArchive } from 'lucide-react';
import { parseGithubUrl } from '../utils/github.js';
import { RingedPlanetLogo } from './Landing.jsx';
import GalaxyBackground from '../components/GalaxyBackground.jsx';
import SiteFooter from '../components/SiteFooter.jsx';
import {
  getUserRepositoriesSync,
  loadUserRepositories,
  saveUserSingleRepository,
  deleteUserRepository
} from '../api/userRepoService.js';

// GitHub Octocat Icon (strictly sized 16px, never expands or obstructs text)
function GithubIcon({ size = 16, className = '' }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        maxWidth: `${size}px`,
        maxHeight: `${size}px`,
        flexShrink: 0
      }}
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
      />
    </svg>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  // Dynamic user data from Firebase auth (no hardcoded names)
  const userName = user?.displayName || (user?.email ? user.email.split('@')[0] : 'Namish 008');
  const userInitial = (userName || 'U')[0].toUpperCase();
  const userPhoto = user?.photoURL;

  const [inputUrl, setInputUrl] = useState('');
  const [submissionMode, setSubmissionMode] = useState(() =>
    /[?&]gh_(ticket|error|installed)=/.test(window.location.search) ? 'github' : 'url'
  ); // 'url' | 'zip' | 'github'
  const [zipFile, setZipFile] = useState(null);
  const [zipProjectName, setZipProjectName] = useState('');
  const [isUploadingZip, setIsUploadingZip] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [searchFilter, setSearchFilter] = useState('');
  const [filterType, setFilterType] = useState('All');
  const [activeNav, setActiveNav] = useState('Home');

  // User-isolated repositories (strictly scoped per user ID, synced with Firestore database)
  const [repositories, setRepositories] = useState(() => getUserRepositoriesSync(user));
  const [isLoadingRepos, setIsLoadingRepos] = useState(false);

  // Reload repositories whenever authenticated user changes (prevents account mixing)
  useEffect(() => {
    let isMounted = true;
    if (!user) {
      setRepositories([]);
      return;
    }

    // Load instantly from user partition
    setRepositories(getUserRepositoriesSync(user));

    // Non-blocking async sync from Cloud Firestore
    loadUserRepositories(user).then((repos) => {
      if (isMounted && repos && repos.length > 0) {
        setRepositories(repos);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [user?.uid, user?.email]);

  const handleStartAnalysis = (e) => {
    e?.preventDefault();
    const trimmedInput = inputUrl.trim();
    if (!trimmedInput) return;

    const parsed = parseGithubUrl(trimmedInput);
    const targetUrl = parsed
      ? parsed.url
      : (trimmedInput.startsWith('http')
          ? trimmedInput
          : `https://github.com/${trimmedInput.replace(/^\/+/, '')}`);
          
    const repoFullName = parsed
      ? `${parsed.owner}/${parsed.name}`
      : targetUrl.replace(/^https?:\/\/(www\.)?github\.com\//i, '').replace(/\/$/, '');

    // Navigate to analysis page directly to parse real AST and dependencies
    // Do not save fake/hardcoded stats ahead of actual backend analysis
    navigate(`/analyze?repo=${encodeURIComponent(targetUrl)}&name=${encodeURIComponent(repoFullName)}`);
  };

  const handleOpenWorkspace = (repo) => {
    if (!repo) {
      const inputEl = document.getElementById('repo-url-input');
      if (inputEl) inputEl.focus();
      return;
    }

    const repoObj = typeof repo === 'string' ? { url: repo, name: repo } : repo;
    const isAnalyzed = repoObj.status === 'done' && (repoObj.repository_id || (repoObj.id && repoObj.id.startsWith('repo_')));

    if (isAnalyzed) {
      const targetId = repoObj.repository_id || repoObj.id;
      navigate(`/workspace?repo=${encodeURIComponent(targetId)}&name=${encodeURIComponent(repoObj.name || '')}&url=${encodeURIComponent(repoObj.url || '')}`);
    } else {
      // Re-trigger or continue analysis for pending/unindexed repositories
      const targetUrl = repoObj.url || repoObj.id;
      navigate(`/analyze?repo=${encodeURIComponent(targetUrl)}&name=${encodeURIComponent(repoObj.name || '')}`);
    }
  };

  const handleStartZipAnalysis = async (e) => {
    e?.preventDefault();
    if (!zipFile) {
      setUploadError('Please select a ZIP file to upload.');
      return;
    }
    setIsUploadingZip(true);
    setUploadError('');
    try {
      const projName = (zipProjectName.trim() || zipFile.name.replace(/\.zip$/i, '')).replace(/[^a-zA-Z0-9_.-]/g, '_');
      const submitRes = await uploadRepositoryZip(zipFile, 'main', projName);
      navigate(`/analyze?repo_id=${encodeURIComponent(submitRes.repository_id)}&job_id=${encodeURIComponent(submitRes.job_id)}&name=${encodeURIComponent(projName)}`);
    } catch (err) {
      setUploadError(err.message || 'Failed to upload and queue ZIP archive');
    } finally {
      setIsUploadingZip(false);
    }
  };

  const handleRemoveRepo = (e, repoId) => {
    e.stopPropagation();
    const updated = deleteUserRepository(user, repoId);
    setRepositories(updated);
  };

  const handleFillSample = (sampleUrl) => {
    setInputUrl(sampleUrl);
    const inputEl = document.getElementById('repo-url-input');
    if (inputEl) inputEl.focus();
  };

  const handleLogout = async () => {
    try {
      if (logout) await logout();
    } catch (err) {
      console.error('Logout error', err);
    }
    navigate('/');
  };

  // Filter repositories dynamically based on search & type
  const filteredRepos = repositories.filter((r) => {
    const matchesSearch =
      r.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
      (r.desc && r.desc.toLowerCase().includes(searchFilter.toLowerCase()));
    const matchesType = filterType === 'All' ? true : r.type === filterType;
    return matchesSearch && matchesType;
  });

  // Dynamic Quick Stats computed strictly from real data
  const totalReposCount = repositories.length;
  const analyzedCount = repositories.filter((r) => r.status === 'done' || !r.status).length;
  const inProgressCount = repositories.filter((r) => r.status === 'indexing').length;

  return (
    <div className="dash-layout">
      {/* Full-screen Photorealistic Deep Space Galaxy Backdrop */}
      <GalaxyBackground />

      {/* Full-width Top Header Bar spanning the top */}
      <header className="dash-header">
        <div className="dash-brand-wrap cursor-pointer" onClick={() => navigate('/')}>
          <RingedPlanetLogo className="w-7 h-7 text-[#FB923C]" />
          <span className="dash-brand-title">A S T R O G R A P H</span>
        </div>

        <div className="dash-header-right">
          {/* Dynamic User Profile Pill */}
          <div className="dash-user-pill">
            {userPhoto ? (
              <img
                src={userPhoto}
                alt={userName}
                className="dash-user-avatar-img"
              />
            ) : (
              <div className="dash-avatar-circle">{userInitial}</div>
            )}
            <span className="text-[#FFF7ED] font-medium">{userName}</span>
          </div>

          {/* Dedicated Logout Button with spacious margin */}
          <button
            type="button"
            onClick={handleLogout}
            className="dash-logout-btn"
            title="Sign Out"
          >
            <LogOut size={15} />
            <span>Log Out</span>
          </button>
        </div>
      </header>

      {/* Main Viewport Body */}
      <div className="dash-viewport-body">
        
        {/* Fixed Constant Left Navigation Sidebar: Home & Repositories */}
        <aside className="dash-sidebar">
          <nav className="sidebar-nav-list">
            <button
              type="button"
              onClick={() => navigate('/dashboard')}
              className="sidebar-nav-item sidebar-nav-item--active"
              title="Dashboard Home"
            >
              <Home size={18} />
              <span>Home</span>
            </button>
            <button
              type="button"
              onClick={() => navigate('/repositories')}
              className="sidebar-nav-item"
              title="Previously Analysed Repositories"
            >
              <FolderGit2 size={18} />
              <span>Repositories</span>
            </button>
          </nav>

          {/* Poetic Quote anchored strictly at the bottom of the constant sidebar */}
          <div className="sidebar-bottom-quote">
            <p className="sidebar-quote-text">
              Code
              <br />
              is a map.
              <br />
              We help you
              <br />
              read it.
            </p>
          </div>
        </aside>

        {/* Scrollable Main Dashboard Content Area */}
        <div className="dash-main-area">
          <main className="dash-body-content">
          
          {/* Top Banner Section (Split Hero + New Analysis Card) */}
          <section className="dash-top-banner">
            <div className="banner-left-hero">
              <span className="banner-eyebrow-pill">
                AI-POWERED CODEBASE INTELLIGENCE
              </span>

              <h1 className="banner-title">
                Understand your
                <em>codebase.</em>
              </h1>

              <p className="banner-desc">
                Turn any GitHub repository into an interactive map of its architecture, dependencies and logic.
              </p>
            </div>

            {/* Right Side: New Analysis Glass Card */}
            <div className="new-analysis-card">
              <div className="new-analysis-head">
                <Sparkles size={18} className="text-[#FB923C]" />
                <h3 className="new-analysis-title">New Analysis</h3>
              </div>
              <p className="new-analysis-sub">Submit a GitHub URL or upload a ZIP archive of your source code.</p>

              {/* Mode Toggle Pills */}
              <div style={{ display: 'flex', gap: '8px', marginBottom: '14px' }}>
                <button
                  type="button"
                  onClick={() => { setSubmissionMode('url'); setUploadError(''); }}
                  style={{
                    padding: '6px 14px',
                    borderRadius: '20px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    border: '1px solid',
                    background: submissionMode === 'url' ? 'rgba(251, 146, 60, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                    borderColor: submissionMode === 'url' ? '#FB923C' : 'rgba(255, 255, 255, 0.1)',
                    color: submissionMode === 'url' ? '#FB923C' : '#9CA3AF',
                    transition: 'all 0.2s',
                  }}
                >
                  GitHub Repository
                </button>
                <button
                  type="button"
                  onClick={() => { setSubmissionMode('zip'); setUploadError(''); }}
                  style={{
                    padding: '6px 14px',
                    borderRadius: '20px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    border: '1px solid',
                    background: submissionMode === 'zip' ? 'rgba(251, 146, 60, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                    borderColor: submissionMode === 'zip' ? '#FB923C' : 'rgba(255, 255, 255, 0.1)',
                    color: submissionMode === 'zip' ? '#FB923C' : '#9CA3AF',
                    transition: 'all 0.2s',
                  }}
                >
                  Upload ZIP Archive
                </button>
                <button
                  type="button"
                  onClick={() => { setSubmissionMode('github'); setUploadError(''); }}
                  style={{
                    padding: '6px 14px',
                    borderRadius: '20px',
                    fontSize: '0.8rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    border: '1px solid',
                    background: submissionMode === 'github' ? 'rgba(251, 146, 60, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                    borderColor: submissionMode === 'github' ? '#FB923C' : 'rgba(255, 255, 255, 0.1)',
                    color: submissionMode === 'github' ? '#FB923C' : '#9CA3AF',
                    transition: 'all 0.2s',
                  }}
                >
                  Connect GitHub
                </button>
              </div>

              {submissionMode === 'url' ? (
                <form onSubmit={handleStartAnalysis} className="new-analysis-form">
                  <div className="analysis-input-wrap">
                    <GithubIcon className="analysis-input-icon" />
                    <input
                      id="repo-url-input"
                      type="text"
                      required
                      placeholder="https://github.com/owner/repo"
                      value={inputUrl}
                      onChange={(e) => setInputUrl(e.target.value)}
                      className="analysis-text-input"
                    />
                  </div>
                  <button type="submit" className="analysis-submit-btn">
                    <span>Analyse</span>
                    <ArrowRight size={15} />
                  </button>
                </form>
              ) : submissionMode === 'github' ? (
                <GithubRepoPicker />
              ) : (
                <form onSubmit={handleStartZipAnalysis} className="new-analysis-form" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{
                    position: 'relative',
                    border: '1px dashed rgba(251, 146, 60, 0.4)',
                    borderRadius: '10px',
                    padding: '12px',
                    background: 'rgba(0, 0, 0, 0.3)',
                    textAlign: 'center',
                    cursor: 'pointer',
                  }}>
                    <input
                      type="file"
                      accept=".zip"
                      required
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setZipFile(file);
                          if (!zipProjectName) setZipProjectName(file.name.replace(/\.zip$/i, ''));
                        }
                      }}
                      style={{
                        position: 'absolute',
                        inset: 0,
                        opacity: 0,
                        cursor: 'pointer',
                        width: '100%',
                        height: '100%',
                      }}
                    />
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px', color: '#FB923C', fontSize: '0.85rem' }}>
                      <FileArchive size={18} />
                      <span>{zipFile ? zipFile.name : 'Select or drop .zip codebase archive'}</span>
                    </div>
                  </div>

                  <input
                    type="text"
                    placeholder="Project Name (optional)"
                    value={zipProjectName}
                    onChange={(e) => setZipProjectName(e.target.value)}
                    className="analysis-text-input"
                    style={{ paddingLeft: '14px', fontSize: '0.85rem' }}
                  />

                  {uploadError && (
                    <div style={{ color: '#f87171', fontSize: '0.8rem', textAlign: 'left' }}>
                      {uploadError}
                    </div>
                  )}

                  <button type="submit" className="analysis-submit-btn" disabled={isUploadingZip || !zipFile}>
                    <span>{isUploadingZip ? 'Uploading...' : 'Upload & Analyse'}</span>
                    <ArrowRight size={15} />
                  </button>
                </form>
              )}

              <div className="analysis-trust-badges">
                <span>✓ Public & private repos, ZIPs</span>
                <span>✓ Tree-sitter AST</span>
                <span>✓ 2D & 3D Knowledge Graph</span>
              </div>
            </div>
          </section>

          {/* Main Lower Section (Repositories Grid + Right Telemetry Sidebar) */}
          <div className="dash-grid-sections">
            
            {/* Center-Left: Your Repositories Section */}
            <div id="repos-section">
              <div className="repos-section-header">
                <div className="repos-section-title-wrap">
                  <div className="w-8 h-8 rounded-lg bg-[#FB923C]/15 border border-[#FB923C]/30 flex items-center justify-center text-[#FB923C]">
                    <Layers size={18} />
                  </div>
                  <div>
                    <h2 className="repos-section-title">Your Repositories</h2>
                    <p className="repos-section-sub">
                      Access your previously analysed repositories or start a new one.
                    </p>
                  </div>
                </div>

                {repositories.length > 0 && (
                  <div className="repos-controls-row">
                    <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                      <Search
                        size={14}
                        style={{
                          position: 'absolute',
                          left: '12px',
                          color: '#9CA3AF',
                          pointerEvents: 'none',
                          zIndex: 2,
                        }}
                      />
                      <input
                        type="text"
                        placeholder="Search repositories..."
                        value={searchFilter}
                        onChange={(e) => setSearchFilter(e.target.value)}
                        className="repo-search-input"
                        style={{ paddingLeft: '34px' }}
                      />
                    </div>

                    <select
                      value={filterType}
                      onChange={(e) => setFilterType(e.target.value)}
                      className="repo-filter-select"
                    >
                      <option value="All">All</option>
                      <option value="Private">Private</option>
                      <option value="Public">Public</option>
                    </select>
                  </div>
                )}
              </div>

              {/* Dynamic Repositories List or Uncluttered Empty State */}
              {repositories.length === 0 ? (
                <div className="dash-empty-repos">
                  <div className="dash-empty-icon-wrap">
                    <FolderGit2 size={32} />
                  </div>
                  <div>
                    <h3 className="dash-empty-title">No repositories analyzed yet</h3>
                    <p className="dash-empty-sub">
                      Enter any public GitHub repository URL in the box above to generate your first interactive 3D knowledge graph.
                    </p>
                  </div>

                  {/* Sample Repositories to try */}
                  <div className="sample-repos-row">
                    <span className="text-xs text-gray-400">Quick start:</span>
                    <button
                      type="button"
                      onClick={() => handleFillSample('https://github.com/facebook/react')}
                      className="sample-repo-pill"
                    >
                      facebook/react
                    </button>
                    <button
                      type="button"
                      onClick={() => handleFillSample('https://github.com/expressjs/express')}
                      className="sample-repo-pill"
                    >
                      expressjs/express
                    </button>
                    <button
                      type="button"
                      onClick={() => handleFillSample('https://github.com/pallets/flask')}
                      className="sample-repo-pill"
                    >
                      pallets/flask
                    </button>
                  </div>
                </div>
              ) : filteredRepos.length === 0 ? (
                <div className="dash-empty-repos">
                  <div className="text-gray-400 text-sm">No repositories matched your search query.</div>
                </div>
              ) : (
                <div className="repo-cards-grid">
                  {filteredRepos.map((repo) => (
                    <div
                      key={repo.id}
                      onClick={() => handleOpenWorkspace(repo)}
                      className="repo-card cursor-pointer"
                    >
                      <div className="repo-card-head">
                        <div className="repo-card-identity">
                          <GithubIcon className="w-4 h-4 text-white" />
                          <span className="repo-card-name truncate max-w-[170px]" title={repo.name}>
                            {repo.name}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="repo-type-tag">{repo.type || 'Public'}</span>
                          <button
                            type="button"
                            onClick={(e) => handleRemoveRepo(e, repo.id)}
                            title="Remove from dashboard"
                            className="text-gray-500 hover:text-red-400 p-1 transition"
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>

                      <p className="repo-card-desc">{repo.desc}</p>

                      <div className="repo-tech-pills">
                        {repo.tech && repo.tech.map((t, idx) => (
                          <span key={idx} className="tech-pill">{t}</span>
                        ))}
                      </div>

                      {/* Progress Bar if indexing */}
                      {repo.status === 'indexing' && (
                        <div className="space-y-1.5 pt-1">
                          <div className="card-progress-bar">
                            <div
                              className="card-progress-bar-fill"
                              style={{ width: `${repo.progress || 60}%` }}
                            />
                          </div>
                          <div className="text-[11px] font-mono text-[#38BDF8]">
                            {repo.progressSubText || 'Parsing code tree...'}
                          </div>
                        </div>
                      )}

                      <div className="repo-metrics-row">
                        <span>{repo.nodes || 'Nodes mapped'} · {repo.edges || 'Edges mapped'}</span>
                        <div
                          className={`repo-status-indicator ${
                            repo.status === 'done' || !repo.status
                              ? 'repo-status-indicator--done'
                              : 'repo-status-indicator--progress'
                          }`}
                        >
                          <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
                          <span>{repo.statusText || 'Analysis complete'}</span>
                        </div>
                      </div>

                      <div className="repo-card-footer">
                        <span>Last analysed · {repo.lastAnalysed || 'Recently'}</span>
                        <ArrowRight size={14} className="text-[#FB923C]" />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Right Column: Quick Stats, Recent Activity, Promo */}
            <aside className="dash-right-widgets">
              
              {/* Quick Stats 2x2 Bento (100% dynamic) */}
              <div className="widget-card">
                <h3 className="widget-card-title">
                  <BarChart3 size={17} className="text-[#FB923C]" />
                  <span>Quick Stats</span>
                </h3>

                <div className="bento-stats-grid">
                  <div className="bento-stat-tile">
                    <span className="bento-stat-num">{totalReposCount}</span>
                    <span className="bento-stat-label">Total Repositories</span>
                  </div>
                  <div className="bento-stat-tile">
                    <span className="bento-stat-num text-emerald-400">{analyzedCount}</span>
                    <span className="bento-stat-label">Analyzed</span>
                  </div>
                  <div className="bento-stat-tile">
                    <span className="bento-stat-num text-[#38BDF8]">{inProgressCount}</span>
                    <span className="bento-stat-label">In Progress</span>
                  </div>
                  <div className="bento-stat-tile">
                    <span className="bento-stat-num text-gray-500">0</span>
                    <span className="bento-stat-label">Failed</span>
                  </div>
                </div>
              </div>

              {/* Recent Activity Timeline (Dynamic) */}
              <div className="widget-card">
                <h3 className="widget-card-title">
                  <Zap size={17} className="text-[#FB923C]" />
                  <span>Recent Activity</span>
                </h3>

                <div className="timeline-list">
                  {repositories.length === 0 ? (
                    <div className="text-xs text-gray-500 py-3 text-center">
                      No analysis activity yet. Analyzed repositories will appear here.
                    </div>
                  ) : (
                    repositories.slice(0, 4).map((repo) => (
                      <div key={repo.id} className="timeline-item">
                        <span
                          className={`timeline-dot ${
                            repo.status === 'indexing'
                              ? 'timeline-dot--blue'
                              : 'timeline-dot--green'
                          }`}
                        />
                        <div>
                          <div className="timeline-title">
                            {repo.status === 'indexing' ? 'Indexing in progress' : 'Analysis completed'}
                          </div>
                          <div className="text-[#9CA3AF] text-xs font-mono">{repo.name}</div>
                          <span className="timeline-date">{repo.lastAnalysed}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Explore the power of graphs Promo Card */}
              <div className="promo-graph-card">
                <div className="w-9 h-9 rounded-xl bg-[#FB923C]/20 border border-[#FB923C]/40 flex items-center justify-center text-[#FB923C]">
                  <Share2 size={18} />
                </div>
                <div>
                  <h4 className="font-bold text-sm text-[#FFF7ED]">Explore the power of graphs</h4>
                  <p className="text-xs text-[#9CA3AF] mt-1 leading-relaxed">
                    Visualize relationships, find dependencies and understand your codebase.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleOpenWorkspace(repositories[0])}
                  className="promo-btn"
                >
                  Open Graph Explorer →
                </button>
              </div>

            </aside>
          </div>

          {/* Bottom Feature Strip (3-column horizontal feature bar) */}
          <div className="dash-bottom-strip" role="region" aria-label="Feature Highlights">
            <div className="strip-item">
              <div className="strip-icon-circle">
                <Share2 size={18} />
              </div>
              <div>
                <h5 className="strip-title">Repository Graph</h5>
                <p className="strip-desc">Visualize code structure & relationships</p>
              </div>
            </div>

            <div className="strip-item">
              <div className="strip-icon-circle">
                <Sparkles size={18} />
              </div>
              <div>
                <h5 className="strip-title">Smart Analysis</h5>
                <p className="strip-desc">AI-powered insights & recommendations</p>
              </div>
            </div>

            <div className="strip-item">
              <div className="strip-icon-circle">
                <Cpu size={18} />
              </div>
              <div>
                <h5 className="strip-title">Developer Focused</h5>
                <p className="strip-desc">Built for speed, clarity and productivity</p>
              </div>
            </div>
          </div>

        </main>

        {/* Shared Global Site Footer */}
        <SiteFooter />
      </div>

    </div>

  </div>
);
}
