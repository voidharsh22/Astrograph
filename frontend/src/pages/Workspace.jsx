import { useEffect, useState, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
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
  Cpu
} from 'lucide-react';
import GalaxyGraph3D from '../components/Graph/GalaxyGraph3D.jsx';
import { getRepositoryGraph, askCodebaseQuestion } from '../api/workspaceService.js';
import '../styles/workspace.css';

export default function Workspace() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const repoParam = searchParams.get('repo') || 'cosmic-weather-api';

  // Navigation tab states
  const [activeTab, setActiveTab] = useState('graph'); // 'overview' | 'explorer' | 'graph' | 'search' | 'ai' | 'status'

  // Data & graph states
  const [graphData, setGraphData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [highlightedNodeIds, setHighlightedNodeIds] = useState([]);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');

  // AI Chat state
  const [chatMessages, setChatMessages] = useState([
    {
      sender: 'ai',
      text: "Greetings! I'm your Astral Cartographer AI agent. I can guide your camera through the codebase, explain architectural workflows, or trace blast radius impacts."
    }
  ]);
  const [chatInput, setChatInput] = useState('');
  const [isAsking, setIsAsking] = useState(false);

  // Load graph payload
  useEffect(() => {
    async function load() {
      setLoading(true);
      const data = await getRepositoryGraph(repoParam);
      setGraphData(data);
      if (data?.nodes?.length > 0) {
        setSelectedNodeId(data.nodes[0].id);
      }
      setLoading(false);
    }
    load();
  }, [repoParam]);

  // Selected Node data
  const selectedNode = useMemo(() => {
    if (!graphData?.nodes || !selectedNodeId) return null;
    return graphData.nodes.find((n) => n.id === selectedNodeId) || null;
  }, [graphData, selectedNodeId]);

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

  // Handle AI question submit
  const handleSendChat = async (e) => {
    e?.preventDefault();
    if (!chatInput.trim() || isAsking) return;

    const userQ = chatInput.trim();
    setChatInput('');
    setChatMessages((prev) => [...prev, { sender: 'user', text: userQ }]);
    setIsAsking(true);

    try {
      const resp = await askCodebaseQuestion(userQ, repoParam);
      setChatMessages((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: resp.answer,
          highlights: resp.highlighted_node_ids
        }
      ]);
      if (resp.highlighted_node_ids?.length > 0) {
        setHighlightedNodeIds(resp.highlighted_node_ids);
        setSelectedNodeId(resp.highlighted_node_ids[0]);
      }
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        { sender: 'ai', text: "Encountered an issue analyzing the codebase query. Please try again." }
      ]);
    } finally {
      setIsAsking(false);
    }
  };

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
            <span className="w-2 h-2 rounded-full bg-cyan-400 inline-block animate-pulse mr-1" />
            INDEXED READY
          </span>
        </div>
      </header>

      {/* Tabs Bar */}
      <nav className="workspace-tabs">
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
          <Bot size={15} /> AI Assistant
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
        {/* Tab 1: 3D Code Graph */}
        {activeTab === 'graph' && (
          <div className="workspace-view workspace-view--graph">
            {loading ? (
              <div className="flex items-center justify-center h-full text-cyan-400 font-mono">
                INITIALIZING CELESTIAL MAPPING...
              </div>
            ) : (
              <GalaxyGraph3D
                graphData={graphData}
                selectedNodeId={selectedNodeId}
                highlightedNodeIds={highlightedNodeIds}
                onSelectNode={(id) => setSelectedNodeId(id)}
              />
            )}
          </div>
        )}

        {/* Tab 2: File Explorer */}
        {activeTab === 'explorer' && (
          <div className="workspace-view">
            <h2 className="text-lg font-semibold mb-4 text-cyan-300">Repository Structure</h2>
            <div className="explorer-tree">
              {filteredNodes.map((n) => (
                <div
                  key={n.id}
                  className={`explorer-item ${selectedNodeId === n.id ? 'explorer-item--active' : ''}`}
                  onClick={() => setSelectedNodeId(n.id)}
                >
                  {n.type === 'directory' ? <Box size={14} className="text-cyan-400" /> : <FileCode size={14} />}
                  <span>{n.path}</span>
                  <span className="text-xs text-gray-500 ml-auto">{n.type}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 3: Overview */}
        {activeTab === 'overview' && (
          <div className="workspace-view max-w-4xl mx-auto space-y-8">
            <div>
              <p className="kicker-glow">ARCHITECTURAL TELEMETRY</p>
              <h2 className="overview-hero-title">
                Galaxy <em>Intelligence</em>
              </h2>
              <p className="overview-subtitle">
                Structural mapping, Louvain community clusters, and execution graph insights.
              </p>
            </div>
            
            {/* Glowing Featured Cards matching image 2 */}
            <div className="overview-cards-grid">
              <div className="glow-feature-card glow-feature-card--orange">
                <div className="glow-icon-wrap glow-icon-wrap--orange">
                  <Box size={18} />
                </div>
                <div className="glow-card-metric">{graphData?.nodes?.length || 0}</div>
                <h3 className="glow-card-title">Total Nodes</h3>
                <p className="glow-card-desc">
                  Indexed structural entities including directories, modules, classes, and callable functions.
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
                <div className="glow-card-metric">{graphData?.workflows?.length || 0}</div>
                <h3 className="glow-card-title">Detected Workflows</h3>
                <p className="glow-card-desc">
                  Algorithmic end-to-end execution paths traced from HTTP entrance to data persistence.
                </p>
                <div className="glow-card-footer">
                  <span>Active Pathways</span>
                  <span>→</span>
                </div>
              </div>
            </div>

            {graphData?.workflows && graphData.workflows.length > 0 && (
              <div className="workflow-section">
                <h3 className="workflow-section-title">
                  <Terminal size={16} /> Execution Workflows
                </h3>
                <div className="space-y-3">
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

        {/* Tab 4: Search */}
        {activeTab === 'search' && (
          <div className="workspace-view max-w-3xl mx-auto">
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
                  onClick={() => setSelectedNodeId(n.id)}
                >
                  <Search size={14} className="text-cyan-400" />
                  <span className="font-semibold">{n.label}</span>
                  <span className="text-xs text-gray-500 font-mono">({n.path})</span>
                  <span className="text-xs text-gray-400 ml-auto">{n.type}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 5: AI Assistant */}
        {activeTab === 'ai' && (
          <div className="workspace-view">
            <div className="chat-container">
              <div className="chat-history">
                {chatMessages.map((msg, i) => (
                  <div
                    key={i}
                    className={`chat-message ${msg.sender === 'user' ? 'chat-message--user' : 'chat-message--ai'}`}
                  >
                    <div className="text-xs uppercase font-mono text-gray-400 mb-1">
                      {msg.sender === 'user' ? 'You' : 'Astral Agent'}
                    </div>
                    <div>{msg.text}</div>
                    {msg.highlights && (
                      <div className="mt-2 text-xs font-mono text-cyan-300">
                        ⚡ Highlighted {msg.highlights.length} nodes in 3D Galaxy
                      </div>
                    )}
                  </div>
                ))}
                {isAsking && (
                  <div className="chat-message chat-message--ai text-sm font-mono text-cyan-400 animate-pulse">
                    Traversing graph topology & synthesizing response...
                  </div>
                )}
              </div>
              <form onSubmit={handleSendChat} className="chat-input-row">
                <input
                  type="text"
                  className="chat-input-field"
                  placeholder="Ask anything about architecture, workflows, or impact radius..."
                  value={chatInput}
                  onChange={(e) => setChatInput(e.target.value)}
                />
                <button type="submit" className="chat-send-btn" disabled={isAsking}>
                  Send
                </button>
              </form>
            </div>
          </div>
        )}

        {/* Tab 6: Indexing Status */}
        {activeTab === 'status' && (
          <div className="workspace-view max-w-2xl mx-auto space-y-6">
            <div>
              <p className="kicker-glow">INDEXING ENGINE</p>
              <h2 className="overview-hero-title">
                Telemetry <em>Pipeline</em>
              </h2>
            </div>

            <div className="status-pipeline-box">
              <div className="status-pipeline-header">
                <span className="font-semibold text-sm tracking-wide">Pipeline Execution</span>
                <span className="status-pipeline-badge">100% COMPLETE</span>
              </div>
              <div className="status-progress-track">
                <div className="status-progress-bar" />
              </div>
              <div className="status-steps-list">
                <div className="status-step-item">
                  <span className="status-check-icon">✓</span>
                  <span>Repository cloned & AST parsed via Tree-sitter</span>
                </div>
                <div className="status-step-item">
                  <span className="status-check-icon">✓</span>
                  <span>NetworkX PageRank & Louvain community clusters computed</span>
                </div>
                <div className="status-step-item">
                  <span className="status-check-icon">✓</span>
                  <span>3D coordinates & celestial galaxy serialization completed</span>
                </div>
                <div className="status-step-item">
                  <span className="status-check-icon">✓</span>
                  <span>LangGraph Q&A camera targeting initialized</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Side Inspector Drawer (Consistent context across Explorer & Graph) */}
        {selectedNode && (
          <aside className="workspace-drawer">
            <div className="inspector-badge-row">
              <span className="kicker-glow">NODE INSPECTOR</span>
              <span className="inspector-type-pill">{selectedNode.type}</span>
            </div>

            <div className="inspector-title-wrap">
              <h3 className="inspector-node-title">{selectedNode.label}</h3>
              <div className="inspector-path-pill">
                <FileCode size={13} className="text-orange-400" />
                <span className="inspector-path-text">{selectedNode.path}</span>
              </div>
            </div>

            {selectedNode.ai_summary && (
              <div className="inspector-summary-box">
                <div className="inspector-summary-tag">
                  <Bot size={13} />
                  <span>AI ARCHITECTURAL BRIEF</span>
                </div>
                <p className="inspector-summary-text">
                  {selectedNode.ai_summary}
                </p>
              </div>
            )}

            <div className="inspector-metrics-section">
              <span className="kicker-glow">COMPUTED TELEMETRY</span>
              <div className="inspector-metrics-grid">
                <div className="inspector-metric-card">
                  <span className="inspector-metric-label">LOC</span>
                  <span className="inspector-metric-value">{selectedNode.metrics?.loc || 0}</span>
                </div>
                <div className="inspector-metric-card inspector-metric-card--highlight">
                  <span className="inspector-metric-label">Centrality</span>
                  <span className="inspector-metric-value inspector-metric-value--orange">
                    {selectedNode.metrics?.centrality?.toFixed(2) || '0.00'}
                  </span>
                </div>
                <div className="inspector-metric-card">
                  <span className="inspector-metric-label">Complexity</span>
                  <span className="inspector-metric-value inspector-metric-value--peach">
                    {selectedNode.metrics?.complexity || 0}
                  </span>
                </div>
                <div className="inspector-metric-card">
                  <span className="inspector-metric-label">Cluster ID</span>
                  <span className="inspector-metric-value">
                    #{selectedNode.position_hint?.cluster_id ?? 0}
                  </span>
                </div>
              </div>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}

