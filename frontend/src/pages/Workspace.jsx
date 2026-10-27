import { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  Share2,
  FolderTree,
  Search,
  Bot,
  Activity,
  Layers,
  FileCode,
  Box,
  Terminal,
  ExternalLink,
  Cpu,
  GitFork,
  User
} from 'lucide-react';
import useAuth from '../hooks/useAuth.js';
import GalaxyGraph3D from '../components/Graph/GalaxyGraph3D.jsx';
import CytoscapeGalaxyGraph from '../components/Graph2D/CytoscapeGalaxyGraph.jsx';
import NodeInspectorPanel from '../components/Graph2D/NodeInspectorPanel.jsx';
import { getRepositoryGraph, getDiagnostics } from '../api/workspaceService.js';
import GraphToolsPanel from '../components/GraphToolsPanel.jsx';
import { getAssistantStatus } from '../services/astralAiService.ts';
import { DEFAULT_FILTERS, applyFilters, isolate } from '../services/graphView.js';
import AstralAiAssistant from '../components/AstralAiAssistant.tsx';
import EdgeDataFlowInspector from '../components/EdgeDataFlowInspector.tsx';
import { useGalaxyCopilotBridge } from '../hooks/useGalaxyCopilotBridge.ts';
import SiteFooter from '../components/SiteFooter.jsx';
import '../styles/workspace.css';

export default function Workspace() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams] = useSearchParams();
  const repoParam = searchParams.get('repo') || 'cosmic-weather-api';
  const nameParam = searchParams.get('name') || '';
  const urlParam = searchParams.get('url') || '';
  const [loadError, setLoadError] = useState(null);

  // Dynamic user data for Profile navigation
  const userName = user?.displayName || (user?.email ? user.email.split('@')[0] : 'Namish 008');
  const userInitial = (userName || 'U')[0].toUpperCase();
  const userPhoto = user?.photoURL;

  // Navigation tab states: 'graph2d' | 'graph' | 'explorer' | 'overview' | 'search' | 'ai' | 'status'
  const [activeTab, setActiveTab] = useState('graph2d');

  // Data & graph states
  const [graphData, setGraphData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [selectedCluster, setSelectedCluster] = useState(null);
  // Shared graph-view state: drives BOTH the 2D and 3D canvases, the inspectors and the tools panel
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [isolated, setIsolated] = useState(false);
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);
  const [highlight, setHighlight] = useState({ nodeIds: [], edgeIds: [] });
  const [resetToken, setResetToken] = useState(0);
  const [toolsOpen, setToolsOpen] = useState(true);
  const [diagnostics, setDiagnostics] = useState(null);
  const [diagnosticsError, setDiagnosticsError] = useState(null);
  const [aiStatus, setAiStatus] = useState(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');

  // Astral AI Copilot drawer (Ctrl/Cmd + K). In the "Astral AI Assistant" tab the copilot is docked instead.
  const [copilotOpen, setCopilotOpen] = useState(false);
  // Prompt sent into the copilot from the edge inspector ("Ask Astral AI to Trace Full Path")
  const [copilotRequest, setCopilotRequest] = useState(null);
  // Dependency beam selected in the 3D galaxy (opens the Edge Data-Flow Inspector)
  const [selectedEdgeId, setSelectedEdgeId] = useState(null);
  // "Focus Star" requests for the 2D graph (centers a node without closing the edge inspector)
  const [focus2d, setFocus2d] = useState(null);

  // Stable selection handler: shared by the 3D canvas and the AI bridge (never rebuilds the WebGL scene)
  const handleSelectNode = useCallback((id) => {
    setSelectedNodeId(id);
    setSelectedCluster(null);
    setSelectedEdgeId(null);
  }, []);

  const handleSelectEdge = useCallback((id) => {
    setSelectedEdgeId(id || null);
  }, []);

  // AI camera moves select nodes too, but must not close an Edge Data-Flow Inspector the user opened
  const handleCopilotSelect = useCallback((id) => {
    setSelectedNodeId(id);
    setSelectedCluster(null);
  }, []);

  // Tool calls from the AI need a tab that actually shows the galaxy
  const revealGalaxy = useCallback(() => {
    setActiveTab((tab) => (tab === 'graph' || tab === 'ai' ? tab : 'graph'));
  }, []);

  const copilot = useGalaxyCopilotBridge({
    graph: graphData,
    onSelectNode: handleCopilotSelect,
    onRevealGalaxy: revealGalaxy,
  });

  // Load graph payload
  useEffect(() => {
    async function load() {
      setLoading(true);
      setLoadError(null);
      try {
        const isExplicitDemo = repoParam === 'cosmic-weather-api';
        const data = await getRepositoryGraph(repoParam, { isDemo: isExplicitDemo });
        if (nameParam && (!data.repo_name || data.repo_name === 'cosmic-weather-api' || data.repo_name.startsWith('repo_'))) {
          data.repo_name = nameParam;
        }
        if (urlParam && !data.repo_url) {
          data.repo_url = urlParam;
        }
        setGraphData(data);
        setFilters(DEFAULT_FILTERS);
        setIsolated(false);
        setHighlight({ nodeIds: [], edgeIds: [] });
        setDiagnostics(null);
        setDiagnosticsError(null);
        if (data.repository_id && !data.is_demo) {
          getDiagnostics(data.repository_id)
            .then((d) => setDiagnostics(d.diagnostics))
            .catch((e) => setDiagnosticsError(e.message));
        }
        setSelectedNodeId(null); // no arbitrary default selection: it would bias AI retrieval
      } catch (err) {
        console.error('Failed to load repository graph:', err);
        setLoadError(err.message || 'Failed to load repository graph');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [repoParam, nameParam, urlParam]);

  useEffect(() => {
    getAssistantStatus().then(setAiStatus);
  }, []);

  const backendRepoId = graphData && !graphData.is_demo ? graphData.repository_id || repoParam : null;

  // The filtered/isolated graph handed to both canvases (same normalized data, same selection)
  const viewGraph = useMemo(() => {
    if (!graphData) return graphData;
    const filtered = applyFilters(graphData, filters);
    if (isolated && selectedNodeId) {
      const base = applyFilters(graphData, { ...filters, nodeKinds: 'all', language: 'all', directory: 'all' });
      const keep = new Set(isolate(base, selectedNodeId).nodeIds);
      return { ...filtered, nodes: filtered.nodes.filter((n) => keep.has(n.id)), edges: filtered.edges.filter((e) => keep.has(e.source) && keep.has(e.target)) };
    }
    return filtered;
  }, [graphData, filters, isolated, selectedNodeId]);

  const applyHighlight = useCallback((h) => {
    setHighlight({ nodeIds: h.nodeIds || [], edgeIds: h.edgeIds || [] });
    if (h.kind === 'impact') copilot.showImpact(h.sourceId, h.depths || []);
    else if (h.kind === 'path') copilot.showPath(h.label, h.nodeIds);
    else copilot.showSet(h.label || 'Selection', h.nodeIds);
  }, [copilot]);

  const clearHighlight = useCallback(() => {
    setHighlight({ nodeIds: [], edgeIds: [] });
    copilot.clearOverlay();
  }, [copilot]);

  const resetView = useCallback(() => {
    setFilters(DEFAULT_FILTERS);
    setIsolated(false);
    setShowEdgeLabels(false);
    clearHighlight();
    setResetToken(Date.now());
  }, [clearHighlight]);

  // Open a file from a reference (AI answer, finding, inspector) in the explorer/inspector
  const openPath = useCallback((path) => {
    const node = graphData?.nodes.find((n) => n.path === path);
    if (!node) return;
    handleSelectNode(node.id);
    setActiveTab((tab) => (tab === 'graph' || tab === 'graph2d' || tab === 'ai' ? tab : 'explorer'));
  }, [graphData, handleSelectNode]);

  // Selected Node data
  const selectedNode = useMemo(() => {
    if (!graphData?.nodes || !selectedNodeId) return null;
    return graphData.nodes.find((n) => n.id === selectedNodeId) || null;
  }, [graphData, selectedNodeId]);

  const selectedEdge = useMemo(() => {
    if (!graphData?.edges || !selectedEdgeId) return null;
    return graphData.edges.find((e) => e.id === selectedEdgeId) || null;
  }, [graphData, selectedEdgeId]);

  // Filtered nodes for Search & Explorer
  const filteredNodes = useMemo(() => {
    if (!graphData?.nodes) return [];
    if (!searchQuery.trim()) return graphData.nodes;
    const q = searchQuery.toLowerCase();
    return graphData.nodes.filter(
      (n) =>
        n.label.toLowerCase().includes(q) ||
        n.path.toLowerCase().includes(q) ||
        n.type.toLowerCase().includes(q)
    );
  }, [graphData, searchQuery]);

  // Ctrl/Cmd + K toggles the Astral AI Copilot drawer (or focuses the docked chat on the AI tab)
  useEffect(() => {
    const onKey = (e) => {
      if (e.defaultPrevented) return;
      if (activeTab === 'graph2d') return; // the 2D graph keeps Ctrl+K for its own search box
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (activeTab === 'ai') {
          document.querySelector('.astral-copilot--docked textarea')?.focus();
        } else {
          setCopilotOpen((open) => !open);
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [activeTab]);

  // Floating chip shown over the galaxy while an AI overlay (workflow / blast radius / cluster) is active
  const fxChip = copilot.hasOverlay ? (
    <div className="astral-fx-chip">
      <Bot size={13} />
      <span>{copilot.overlayLabel}</span>
      <button type="button" onClick={copilot.clearOverlay}>Clear</button>
    </div>
  ) : null;

  return (
    <div className="workspace-layout">
      {/* Header */}
      <header className="workspace-header">
        <div className="workspace-header__left">
          <button
            type="button"
            className="workspace-back-btn"
            onClick={() => navigate('/dashboard')}
          >
            <ArrowLeft size={14} /> Home
          </button>
          <div className="workspace-repo-title">
            <span className="workspace-repo-name">
              {graphData?.repo_name || repoParam.split('/').pop()}
            </span>
            <span className="workspace-branch-badge">
              git:{graphData?.branch || 'main'}
            </span>
          </div>
        </div>

        <div className="workspace-header__right">
          <span className="workspace-status-pill workspace-status-pill--ready">
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: graphData?.is_demo ? '#fb923c' : '#38bdf8',
                display: 'inline-block',
                marginRight: 6
              }}
            />
            {graphData?.is_demo ? 'DEMO DATA • PREVIEW' : 'LIVE CODEBASE • VERIFIED'}
          </span>

          {/* User Profile Navigation Button (returns to Dashboard & Profile settings) */}
          <button
            type="button"
            className="workspace-profile-btn"
            onClick={() => navigate('/dashboard')}
            title={`View profile for ${userName}`}
          >
            {userPhoto ? (
              <img
                src={userPhoto}
                alt={userName}
                className="workspace-profile-avatar"
              />
            ) : (
              <div className="workspace-profile-avatar-initial">
                {userInitial}
              </div>
            )}
            <span className="workspace-profile-name">{userName}</span>
          </button>
        </div>
      </header>

      {/* Tabs Bar */}
      <nav className="workspace-tabs">
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'graph2d' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('graph2d')}
        >
          <GitFork size={15} /> Code Graph (2D)
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'graph' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('graph')}
        >
          <Share2 size={15} /> Code Graph (3D)
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'explorer' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('explorer')}
        >
          <FolderTree size={15} /> File Explorer
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'overview' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <Layers size={15} /> Overview
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'search' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('search')}
        >
          <Search size={15} /> Code Search
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'ai' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('ai')}
        >
          <Bot size={15} /> Astral AI Assistant
        </button>
        <button
          type="button"
          className={`workspace-tab ${activeTab === 'status' ? 'workspace-tab--active' : ''}`}
          onClick={() => setActiveTab('status')}
        >
          <Activity size={15} /> Indexing Status
        </button>
      </nav>

      {/* Main Viewport */}
      <div className="workspace-viewport">
        {loadError && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '3rem',
            textAlign: 'center',
            background: 'rgba(15, 23, 42, 0.85)',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            borderRadius: '16px',
            margin: '3rem auto',
            maxWidth: '620px',
            boxShadow: '0 20px 40px rgba(0,0,0,0.6)',
            backdropFilter: 'blur(16px)',
            zIndex: 10,
          }}>
            <div style={{
              width: '54px',
              height: '54px',
              borderRadius: '50%',
              background: 'rgba(239, 68, 68, 0.15)',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#f87171',
              marginBottom: '1rem',
            }}>
              <AlertTriangle size={28} />
            </div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#FFF', marginBottom: '0.5rem' }}>
              Repository Graph Not Loaded
            </h3>
            <p style={{ fontSize: '0.9rem', color: '#94a3b8', marginBottom: '1.5rem', lineHeight: 1.5 }}>
              {loadError}
            </p>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', justifyContent: 'center' }}>
              <button
                type="button"
                onClick={() => window.location.reload()}
                style={{
                  padding: '9px 20px',
                  borderRadius: '8px',
                  background: '#fb923c',
                  color: '#000',
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                Retry Loading
              </button>
              <button
                type="button"
                onClick={() => navigate('/dashboard')}
                style={{
                  padding: '9px 20px',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.1)',
                  color: '#e2e8f0',
                  fontWeight: 500,
                  fontSize: '0.85rem',
                  border: '1px solid rgba(255, 255, 255, 0.2)',
                  cursor: 'pointer',
                }}
              >
                Return to Dashboard
              </button>
              <button
                type="button"
                onClick={() => navigate('/workspace?repo=cosmic-weather-api')}
                style={{
                  padding: '9px 20px',
                  borderRadius: '8px',
                  background: 'rgba(14, 165, 233, 0.15)',
                  color: '#38bdf8',
                  fontWeight: 500,
                  fontSize: '0.85rem',
                  border: '1px solid rgba(14, 165, 233, 0.3)',
                  cursor: 'pointer',
                }}
              >
                Explore Demo Repository
              </button>
            </div>
          </div>
        )}

        {/* Tab 1: 2D Code Graph (Cytoscape.js) */}
        {activeTab === 'graph2d' && (
          <div className="workspace-view workspace-view--graph">
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#38bdf8', fontFamily: 'var(--font-mono)' }}>
                INITIALIZING 2D DEPENDENCY TOPOLOGY...
              </div>
            ) : (
              <CytoscapeGalaxyGraph
                graphData={viewGraph}
                highlightNodeIds={highlight.nodeIds}
                highlightEdgeIds={highlight.edgeIds}
                showEdgeLabels={showEdgeLabels}
                selectedNodeId={selectedNodeId}
                onSelectNode={handleSelectNode}
                selectedEdgeId={selectedEdgeId}
                onSelectEdge={handleSelectEdge}
                focusRequest={focus2d}
                onSelectCluster={(cluster) => {
                  setSelectedCluster(cluster);
                  setSelectedNodeId(null);
                  setSelectedEdgeId(null);
                }}
              />
            )}
          </div>
        )}

        {/* Tab 2: 3D Code Graph */}
        {activeTab === 'graph' && (
          <div className="workspace-view workspace-view--graph">
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#00e5ff', fontFamily: 'var(--font-mono)' }}>
                INITIALIZING CELESTIAL MAPPING...
              </div>
            ) : (
              <>
                <GalaxyGraph3D
                  graphData={viewGraph}
                  showEdgeLabels={showEdgeLabels}
                  resetToken={resetToken}
                  selectedNodeId={selectedNodeId}
                  highlightedNodeIds={highlight.nodeIds}
                  onSelectNode={handleSelectNode}
                  copilotFx={copilot.fx}
                  selectedEdgeId={selectedEdgeId}
                  onSelectEdge={handleSelectEdge}
                />
                {fxChip}
              </>
            )}
          </div>
        )}

        {/* Tab 3: File Explorer */}
        {activeTab === 'explorer' && (
          <div className="workspace-view">
            <h2 className="text-lg font-semibold mb-4 text-cyan-300" style={{ color: '#67e8f9', marginBottom: '1rem' }}>
              Repository Structure
            </h2>
            <div className="explorer-tree">
              {filteredNodes.map((n) => (
                <div
                  key={n.id}
                  className={`explorer-item ${selectedNodeId === n.id ? 'explorer-item--active' : ''}`}
                  onClick={() => {
                    setSelectedNodeId(n.id);
                    setSelectedCluster(null);
                  }}
                >
                  {n.type === 'directory' ? <Box size={14} style={{ color: '#00e5ff' }} /> : <FileCode size={14} />}
                  <span>{n.path}</span>
                  <span style={{ fontSize: '0.75rem', color: '#64748b', marginLeft: 'auto' }}>{n.type}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 4: Overview */}
        {activeTab === 'overview' && (
          <div className="workspace-view" style={{ maxWidth: '900px', margin: '0 auto' }}>
            <div style={{ marginBottom: '2rem' }}>
              <p className="kicker-glow">ARCHITECTURAL TELEMETRY</p>
              <h2 className="overview-hero-title">
                Galaxy <em>Intelligence</em>
              </h2>
              <p className="overview-subtitle">
                Structural mapping, Louvain community clusters, and execution graph insights.
              </p>
            </div>

            <div className="overview-cards-grid">
              <div className="glow-feature-card glow-feature-card--orange">
                <div className="glow-icon-wrap glow-icon-wrap--orange">
                  <Box size={18} />
                </div>
                <div className="glow-card-metric">{graphData?.nodes?.length || 0}</div>
                <h3 className="glow-card-title">Total Nodes</h3>
                <p className="glow-card-desc">
                  Indexed structural entities including source files, modules, and callable functions.
                </p>
                <div className="glow-card-footer">
                  <span>Architecture Nodes</span>
                  <span>→</span>
                </div>
              </div>

              <div className="glow-feature-card glow-feature-card--peach">
                <div className="glow-icon-wrap glow-icon-wrap--peach">
                  <Share2 size={18} />
                </div>
                <div className="glow-card-metric">{graphData?.edges?.length || 0}</div>
                <h3 className="glow-card-title">Dependency Edges</h3>
                <p className="glow-card-desc">
                  Directed call graphs, module import chains, containment links, and subclass hierarchies.
                </p>
                <div className="glow-card-footer">
                  <span>Graph Traversal</span>
                  <span>→</span>
                </div>
              </div>

              <div className="glow-feature-card glow-feature-card--dark">
                <div className="glow-icon-wrap glow-icon-wrap--dark">
                  <Cpu size={18} />
                </div>
                <div className="glow-card-metric">{graphData?.clusters?.length ?? 0}</div>
                <h3 className="glow-card-title">Directory Clusters</h3>
                <p className="glow-card-desc">
                  Visual containment groups structuring child source files into module boundaries.
                </p>
                <div className="glow-card-footer">
                  <span>Module Domains</span>
                  <span>→</span>
                </div>
              </div>
            </div>

            {graphData?.workflows && graphData.workflows.length > 0 && (
              <div className="workflow-section" style={{ marginTop: '2.5rem' }}>
                <h3 className="workflow-section-title">
                  <Terminal size={16} /> Execution Workflows
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '1rem' }}>
                  {graphData.workflows.map((wf, idx) => (
                    <div key={idx} className="workflow-card">
                      <div className="workflow-card-head">
                        <span className="workflow-name">{wf.name}</span>
                        <span className="workflow-badge">{wf.nodes?.length || 0} stages</span>
                      </div>
                      <p className="workflow-desc">{wf.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 5: Search */}
        {activeTab === 'search' && (
          <div className="workspace-view" style={{ maxWidth: '800px', margin: '0 auto' }}>
            <div className="search-bar-wrap">
              <input
                type="text"
                className="search-input"
                placeholder="Search files, symbols, functions, classes..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                autoFocus
              />
            </div>
            <div className="explorer-tree">
              {filteredNodes.map((n) => (
                <div
                  key={n.id}
                  className={`explorer-item ${selectedNodeId === n.id ? 'explorer-item--active' : ''}`}
                  onClick={() => {
                    setSelectedNodeId(n.id);
                    setSelectedCluster(null);
                  }}
                >
                  <Search size={14} style={{ color: '#00e5ff' }} />
                  <span style={{ fontWeight: 600 }}>{n.label}</span>
                  <span style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'var(--font-mono)' }}>({n.path})</span>
                  <span style={{ fontSize: '0.75rem', color: '#94a3b8', marginLeft: 'auto' }}>{n.type}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 6: Astral AI Assistant — 3D galaxy (left ~65%) + docked copilot (right ~35%, rendered below) */}
        {activeTab === 'ai' && (
          <div className="workspace-view workspace-view--graph">
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#fb923c', fontFamily: 'var(--font-mono)' }}>
                INITIALIZING CELESTIAL MAPPING...
              </div>
            ) : (
              <>
                <GalaxyGraph3D
                  graphData={viewGraph}
                  showEdgeLabels={showEdgeLabels}
                  resetToken={resetToken}
                  selectedNodeId={selectedNodeId}
                  highlightedNodeIds={highlight.nodeIds}
                  onSelectNode={handleSelectNode}
                  copilotFx={copilot.fx}
                  selectedEdgeId={selectedEdgeId}
                  onSelectEdge={handleSelectEdge}
                />
                {fxChip}
              </>
            )}
          </div>
        )}

        {/* Tab 7: Indexing Status (real parser diagnostics from the persisted analysis) */}
        {activeTab === 'status' && (
          <div className="workspace-view" style={{ maxWidth: '760px', margin: '0 auto' }}>
            <div style={{ marginBottom: '1.5rem' }}>
              <p className="kicker-glow">PARSER DIAGNOSTICS</p>
              <h2 className="overview-hero-title">Analysis <em>Report</em></h2>
            </div>
            {graphData?.is_demo && <p className="overview-subtitle">Demo data has no parser run, so there are no diagnostics to show.</p>}
            {diagnosticsError && <p style={{ color: '#fca5a5' }}>{diagnosticsError}</p>}
            {diagnostics && (
              <div className="status-pipeline-box">
                <div className="status-pipeline-header">
                  <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>Latest analysis</span>
                  <span className="status-pipeline-badge">{String(diagnostics.status).toUpperCase()}</span>
                </div>
                <div className="status-steps-list">
                  <div className="status-step-item"><span>Files discovered: {diagnostics.files.discovered}; parsed: {diagnostics.files.parsed_successfully}/{diagnostics.files.parseable_discovered}; syntax errors: {diagnostics.files.with_syntax_errors}; unsupported: {diagnostics.files.unsupported}</span></div>
                  <div className="status-step-item"><span>Symbols: {diagnostics.symbols.extracted}; imports resolved: {diagnostics.dependencies.imports_resolved}; external: {diagnostics.dependencies.imports_external}; unresolved internal: {diagnostics.dependencies.imports_unresolved}</span></div>
                  <div className="status-step-item"><span>Calls resolved: {diagnostics.dependencies.calls_resolved}; ambiguous: {diagnostics.dependencies.calls_ambiguous}; unresolved: {diagnostics.dependencies.calls_unresolved}</span></div>
                  <div className="status-step-item"><span>Total parsing time: {diagnostics.timings_ms.total} ms ({Object.entries(diagnostics.timings_ms).filter(([k]) => k !== 'total').map(([k, v]) => `${k} ${v}ms`).join(', ')})</span></div>
                  {diagnostics.warnings.map((w, i) => (<div key={i} className="status-step-item"><span>⚠ {w}</span></div>))}
                </div>
              </div>
            )}
          </div>
        )}

        {['graph2d', 'graph'].includes(activeTab) && graphData && (
          <GraphToolsPanel
            repoId={backendRepoId}
            graph={graphData}
            viewGraph={viewGraph}
            filters={filters}
            setFilters={setFilters}
            selectedNodeId={selectedNodeId}
            isolated={isolated}
            setIsolated={setIsolated}
            showEdgeLabels={showEdgeLabels}
            setShowEdgeLabels={setShowEdgeLabels}
            onHighlight={applyHighlight}
            onClearHighlight={clearHighlight}
            onResetView={resetView}
            onOpenPath={openPath}
            diagnostics={diagnostics}
            diagnosticsError={diagnosticsError}
            aiStatus={backendRepoId ? aiStatus : { configured: false, reason: 'AI features need a real analysed repository (this is demo data).' }}
            open={toolsOpen}
            onToggle={() => setToolsOpen((o) => !o)}
          />
        )}

        {/* ─── SIDE INSPECTOR DRAWER ───────────────────────────────────────── */}
        {selectedEdge && graphData && (
          <EdgeDataFlowInspector
            edge={selectedEdge}
            graph={graphData}
            repoId={repoParam}
            onClose={() => setSelectedEdgeId(null)}
            onFocusNode={(id) => {
              if (activeTab === 'graph2d') {
                setFocus2d({ id, token: Date.now() });
                return;
              }
              copilot.focusNode(id); // camera flies to the star; the beam stays selected
            }}
            onAskAstral={(text) => {
              setCopilotRequest({ text, token: Date.now() });
              if (activeTab !== 'ai') setCopilotOpen(true);
            }}
            onSimulateBreak={(sourceId) => {
              copilot.executeTool(
                { id: `sim_${Date.now()}`, name: 'showBlastRadius', input: { sourceNodeId: sourceId, depth: 3, affectedNodeIds: [] } },
                { force: true },
              );
              if (activeTab !== 'ai') setCopilotOpen(true);
            }}
          />
        )}

        {!selectedEdge && (selectedNode || selectedCluster) && (
          <NodeInspectorPanel
            selectedNode={selectedNode}
            selectedCluster={selectedCluster}
            allNodes={graphData?.nodes || []}
            allEdges={graphData?.edges || []}
            repoName={graphData?.repo_name || repoParam}
            repoId={backendRepoId}
            onSelectNode={(id) => {
              setSelectedNodeId(id);
              setSelectedCluster(null);
            }}
            onClose={() => {
              setSelectedNodeId(null);
              setSelectedCluster(null);
            }}
          />
        )}

        {/* ─── ASTRAL AI COPILOT (docked on the AI tab, slide-over drawer elsewhere) ─── */}
        <AstralAiAssistant
          graph={graphData}
          repoId={backendRepoId}
          selectedNodeId={selectedNodeId}
          bridge={copilot}
          variant={activeTab === 'ai' ? 'docked' : 'drawer'}
          request={copilotRequest}
          drawerOffset={selectedEdge ? 392 : 16}
          open={copilotOpen}
          onOpen={() => setCopilotOpen(true)}
          onClose={() => setCopilotOpen(false)}
        />
      </div>

      {/* Shared Global Site Footer */}
      <SiteFooter compact />
    </div>
  );
}
