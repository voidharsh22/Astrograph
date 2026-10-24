import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Home,
  FolderGit2,
  Share2,
  Search,
  ArrowRight,
  ArrowLeft,
  Trash2,
  Sparkles,
  ExternalLink,
  Layers,
  Database,
  LogOut,
  Plus,
} from "lucide-react";
import useAuth from "../hooks/useAuth.js";
import { RingedPlanetLogo } from "./Landing.jsx";
import GalaxyBackground from "../components/GalaxyBackground.jsx";
import {
  getUserRepositoriesSync,
  loadUserRepositories,
  deleteUserRepository,
  clearAllUserRepositories,
} from "../api/userRepoService.js";

// GitHub Octocat Icon (strictly sized 16px)
function GithubIcon({ size = 16, className = "" }) {
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
        flexShrink: 0,
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

export default function Repositories() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  // Dynamic user data from Firebase auth
  const userName =
    user?.displayName ||
    (user?.email ? user.email.split("@")[0] : "Namish 008");
  const userInitial = (userName || "U")[0].toUpperCase();
  const userPhoto = user?.photoURL;

  const [searchFilter, setSearchFilter] = useState("");
  const [filterType, setFilterType] = useState("All");
  const [sortBy, setSortBy] = useState("last");

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

    setRepositories(getUserRepositoriesSync(user));

    loadUserRepositories(user).then((repos) => {
      if (isMounted && repos && repos.length > 0) {
        setRepositories(repos);
      }
    });

    return () => {
      isMounted = false;
    };
  }, [user?.uid, user?.email]);

  const handleOpenWorkspace = (repo) => {
    const target = repo?.url || (typeof repo === "string" ? repo : "");
    if (!target) return;
    navigate(`/workspace?repo=${encodeURIComponent(target)}`);
  };

  const handleRemoveRepo = (e, repoId) => {
    e.stopPropagation();
    const updated = deleteUserRepository(user, repoId);
    setRepositories(updated);
  };

  const handleClearAll = () => {
    if (
      window.confirm(
        "Are you sure you want to clear your analyzed repositories history?",
      )
    ) {
      const updated = clearAllUserRepositories(user);
      setRepositories(updated);
    }
  };

  const handleLogout = async () => {
    try {
      if (logout) await logout();
    } catch (err) {
      console.error("Logout error", err);
    }
    navigate("/");
  };

  // Filter & sort repositories
  const filteredRepos = repositories
    .filter((r) => {
      const matchesSearch =
        r.name.toLowerCase().includes(searchFilter.toLowerCase()) ||
        (r.desc && r.desc.toLowerCase().includes(searchFilter.toLowerCase()));
      const matchesType = filterType === "All" ? true : r.type === filterType;
      return matchesSearch && matchesType;
    })
    .sort((a, b) => {
      if (sortBy === "name") return a.name.localeCompare(b.name);
      return 0; // default keep recent order
    });

  return (
    <div className="dash-layout">
      {/* Full-screen Deep Space Galaxy Backdrop */}
      <GalaxyBackground />

      {/* Top Header Bar */}
      <header className="dash-header">
        <div
          className="dash-brand-wrap cursor-pointer"
          onClick={() => navigate("/dashboard")}
        >
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
        {/* Fixed Constant Left Sidebar: Home & Repositories */}
        <aside className="dash-sidebar">
          <nav className="sidebar-nav-list">
            <button
              type="button"
              onClick={() => navigate("/dashboard")}
              className="sidebar-nav-item"
              title="Dashboard Home"
            >
              <Home size={18} />
              <span>Home</span>
            </button>
            <button
              type="button"
              className="sidebar-nav-item sidebar-nav-item--active"
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

        {/* Scrollable Main Content Area */}
        <div className="dash-main-area">
          <main className="dash-body-content">
            {/* Top Page Header & Action */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/10 pb-6">
              <div>
                <span className="text-xs font-mono text-[#FB923C] tracking-widest uppercase block mb-1">
                  [ CELESTIAL REPOSITORY ARCHIVE ]
                </span>
                <h1 className="text-3xl font-bold tracking-tight text-[#FFF7ED]">
                  Previously Analysed Repositories
                </h1>
                <p className="text-sm text-gray-400 mt-1 max-w-2xl">
                  Access and explore your mapped codebases, inspect interactive
                  3D architecture graphs, or start a new repository analysis.
                </p>
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => navigate("/dashboard")}
                  className="dash-btn-primary"
                >
                  <Plus size={16} />
                  <span>New Analysis</span>
                </button>
              </div>
            </div>

            {/* Repositories Controls & Filter Bar */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 py-2">
              <div className="relative w-full sm:w-80">
                <Search
                  size={14}
                  className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400"
                />
                <input
                  type="text"
                  placeholder="Search your repositories..."
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  className="dash-search-input"
                  style={{ width: "100%" }}
                />
              </div>

              <div className="flex items-center gap-3 w-full sm:w-auto justify-end">
                <select
                  value={filterType}
                  onChange={(e) => setFilterType(e.target.value)}
                  className="dash-filter-select"
                >
                  <option value="All">All Types</option>
                  <option value="Public">Public Only</option>
                  <option value="Private">Private Only</option>
                </select>

                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  className="dash-filter-select"
                >
                  <option value="last">Last Analysed</option>
                  <option value="name">Alphabetical</option>
                </select>

                {repositories.length > 0 && (
                  <button
                    type="button"
                    onClick={handleClearAll}
                    title="Clear list"
                    className="dash-clear-link"
                  >
                    Clear All
                  </button>
                )}
              </div>
            </div>

            {/* Repositories Grid or Empty State */}
            {repositories.length === 0 ? (
              <div className="dash-empty-repos">
                <div className="dash-empty-icon-wrap">
                  <FolderGit2 size={32} />
                </div>
                <div>
                  <h3 className="dash-empty-title">
                    No previously analysed repositories
                  </h3>
                  <p className="dash-empty-sub">
                    You haven't analysed any GitHub repositories yet. Enter any
                    public repository URL to parse its AST and create an
                    interactive 3D knowledge galaxy.
                  </p>
                </div>

                <div className="flex flex-col sm:flex-row items-center gap-3 mt-2">
                  <button
                    type="button"
                    onClick={() => navigate("/dashboard")}
                    className="dash-btn-primary"
                  >
                    <span>Analyse a Repository</span>
                    <ArrowRight size={15} />
                  </button>
                </div>
              </div>
            ) : filteredRepos.length === 0 ? (
              <div className="dash-empty-repos">
                <div className="text-gray-400 text-sm">
                  No repositories matched your search query.
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {filteredRepos.map((repo) => (
                  <div
                    key={repo.id}
                    onClick={() => handleOpenWorkspace(repo)}
                    className="repo-card cursor-pointer group"
                  >
                    <div className="repo-card-head">
                      <div className="repo-card-identity">
                        <GithubIcon className="w-4 h-4 text-white" />
                        <span
                          className="repo-card-name truncate max-w-[180px]"
                          title={repo.name}
                        >
                          {repo.name}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="repo-type-tag">
                          {repo.type || "Public"}
                        </span>
                        <button
                          type="button"
                          onClick={(e) => handleRemoveRepo(e, repo.id)}
                          title="Remove repository"
                          className="text-gray-500 hover:text-red-400 p-1 transition"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>

                    <p className="repo-card-desc">{repo.desc}</p>

                    <div className="repo-tech-pills">
                      {repo.tech &&
                        repo.tech.map((t, idx) => (
                          <span key={idx} className="tech-pill">
                            {t}
                          </span>
                        ))}
                    </div>

                    <div className="repo-metrics-row">
                      <span>
                        {repo.nodes || "Nodes mapped"} ·{" "}
                        {repo.edges || "Edges mapped"}
                      </span>
                      <div className="repo-status-indicator repo-status-indicator--done">
                        <span className="w-1.5 h-1.5 rounded-full bg-current" />
                        <span>{repo.statusText || "Analysis complete"}</span>
                      </div>
                    </div>

                    <div className="repo-card-footer">
                      <span>
                        Last analysed · {repo.lastAnalysed || "Recently"}
                      </span>
                      <div className="flex items-center gap-1 text-[#FB923C] font-semibold text-xs group-hover:translate-x-1 transition-transform">
                        <span>Explore</span>
                        <ArrowRight size={13} />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
