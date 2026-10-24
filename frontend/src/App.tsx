/**
 * ASTROGRAPH — Main Application Container
 * Full integration of the 3D WebGL Galaxy, 2D Knowledge Graph, AI Copilot, and Dashboard
 * Synced with the deep obsidian & solar amber design system from user snapshots.
 */

import React, { useEffect, useMemo, useState } from 'react'
import { AIChatDrawer } from './components/AIChatDrawer'
import { AnalyticsView } from './components/AnalyticsView'
import { GalaxyCanvas2D } from './components/GalaxyCanvas2D'
import { GalaxyCanvas3D } from './components/GalaxyCanvas3D'
import { HomeDashboard } from './components/HomeDashboard'
import { NodeInspector } from './components/NodeInspector'
import { SearchModal } from './components/SearchModal'
import { NavView, Sidebar } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { WorkflowBar } from './components/WorkflowBar'
import {
  analyzeRepository,
  checkBackendHealth,
  checkJobStatus,
  fetchDemoGraph,
  fetchRepositoryGraph,
  listRepositories,
  submitRepositoryJob,
} from './services/api'
import { computeGalaxyLayout } from './services/galaxyLayout'
import { AstralGraph, GraphNode, RepositoryItem, Workflow } from './types/galaxy'

export const App: React.FC = () => {
  // Navigation & View Mode
  const [currentView, setCurrentView] = useState<NavView>('explorer')
  const [viewMode, setViewMode] = useState<'3d' | '2d'>('3d')

  // Graph Data & Layout
  const [graph, setGraph] = useState<AstralGraph | null>(null)
  const [repositories, setRepositories] = useState<RepositoryItem[]>([])
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(false)

  // Interaction State
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  const [activeFilter, setActiveFilter] = useState<string>('all')
  const [activeWorkflow, setActiveWorkflow] = useState<Workflow | null>(null)

  // Modals & Drawers
  const [isChatOpen, setIsChatOpen] = useState<boolean>(false)
  const [isSearchOpen, setIsSearchOpen] = useState<boolean>(false)

  // Indexing & Job Progress
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false)
  const [indexingProgress, setIndexingProgress] = useState<number>(0)
  const [indexingStage, setIndexingStage] = useState<string | null>(null)

  // Compute 3D and 2D celestial coordinates
  const { layoutNodes, clusters } = useMemo(() => {
    if (!graph) return { layoutNodes: [], clusters: [] }
    const res = computeGalaxyLayout(graph)
    return { layoutNodes: res.nodes, clusters: res.clusters }
  }, [graph])

  // Initial Load & Backend Health Check
  useEffect(() => {
    async function init() {
      try {
        await checkBackendHealth()
        setIsBackendConnected(true)

        // Load repository list
        try {
          const repos = await listRepositories()
          setRepositories(repos)
        } catch {
          // ignore
        }

        // Load default demo galaxy
        const demo = await fetchDemoGraph()
        setGraph(demo)
        if (demo.nodes.length > 0) {
          setSelectedNode(demo.nodes[0])
        }
      } catch (err) {
        console.warn('Backend connection warning, loading fallback graph:', err)
        setIsBackendConnected(false)
        // Fallback local demo graph if backend is booting
        try {
          const demo = await fetchDemoGraph()
          setGraph(demo)
        } catch {
          // If fetch fails, provide empty template
          setGraph({
            repo_url: 'https://github.com/voidharsh22/Astrograph',
            repo_name: 'Astrograph',
            branch: 'dev',
            commit_sha: null,
            generated_at: new Date().toISOString(),
            nodes: [
              {
                id: 'dir::backend',
                label: 'backend',
                type: 'directory',
                language: null,
                path: 'backend',
                metrics: { loc: 0, centrality: 0.8, complexity: 0 },
                position_hint: { cluster_id: 0, depth: 0 },
                ai_summary: 'Core backend engine architecture.',
              },
              {
                id: 'file::backend/app/main.py',
                label: 'main.py',
                type: 'file',
                language: 'python',
                path: 'backend/app/main.py',
                metrics: { loc: 60, centrality: 0.95, complexity: 2 },
                position_hint: { cluster_id: 0, depth: 1 },
                ai_summary: 'FastAPI application router and middleware.',
              },
              {
                id: 'func::backend/app/main.py::lifespan',
                label: 'lifespan()',
                type: 'function',
                language: 'python',
                path: 'backend/app/main.py',
                metrics: { loc: 15, centrality: 0.4, complexity: 1 },
                position_hint: { cluster_id: 0, depth: 2 },
                ai_summary: 'Database lifecycle initialization hook.',
              },
            ],
            edges: [
              {
                id: 'e-01',
                source: 'dir::backend',
                target: 'file::backend/app/main.py',
                relation: 'contains',
                weight: 1,
              },
              {
                id: 'e-02',
                source: 'file::backend/app/main.py',
                target: 'func::backend/app/main.py::lifespan',
                relation: 'contains',
                weight: 1,
              },
            ],
            workflows: [],
            metadata: {
              total_files: 1,
              total_functions: 1,
              total_classes: 0,
              languages: ['python'],
              analysis_duration_ms: 12.0,
              cluster_summaries: { 0: 'Core backend service and routing' },
            },
          })
        }
      }
    }

    init()
  }, [])

  // Handle repository selection
  const handleSelectRepo = async (repo: RepositoryItem) => {
    try {
      if (repo.id.startsWith('demo-')) {
        const demo = await fetchDemoGraph()
        setGraph({ ...demo, repo_name: repo.name, repo_url: repo.url })
      } else {
        const g = await fetchRepositoryGraph(repo.id)
        setGraph(g)
      }
      setCurrentView('explorer')
    } catch (err: any) {
      alert(`Could not load graph for ${repo.name}: ${err.message}`)
    }
  }

  // Handle URL analysis request
  const handleAnalyzeUrl = async (url: string) => {
    setIsAnalyzing(true)
    setIndexingProgress(15)
    setIndexingStage('Cloning & running Tree-Sitter AST parsing…')

    try {
      // Run analysis
      const newGraph = await analyzeRepository(url, 'main', false)
      setIndexingProgress(85)
      setIndexingStage('Computing PageRank and Louvain constellations…')

      setGraph(newGraph)
      setIndexingProgress(100)
      setIndexingStage('Complete!')

      // Refresh repo list
      try {
        const updatedRepos = await listRepositories()
        setRepositories(updatedRepos)
      } catch {
        // ignore
      }

      setTimeout(() => {
        setIsAnalyzing(false)
        setCurrentView('explorer')
      }, 500)
    } catch (err: any) {
      alert(`Analysis failed: ${err.message || 'Error communicating with backend'}`)
      setIsAnalyzing(false)
    }
  }

  const handleFlyToNode = (nodeId: string) => {
    setFocusNodeId(nodeId)
    const match = layoutNodes.find((n) => n.id === nodeId)
    if (match) {
      setSelectedNode(match)
    }
    // Switch to explorer if not currently active
    if (currentView !== 'explorer') {
      setCurrentView('explorer')
    }
  }

  return (
    <div className="app-container">
      {/* Left Sidebar */}
      <Sidebar currentView={currentView} onSelectView={setCurrentView} />

      {/* Main Workspace */}
      <div className="workspace">
        {/* Top Bar */}
        <TopBar
          repoName={graph?.repo_name || 'Astrograph'}
          viewMode={viewMode}
          activeFilter={activeFilter}
          isChatOpen={isChatOpen}
          isBackendConnected={isBackendConnected}
          onToggleViewMode={setViewMode}
          onSelectFilter={setActiveFilter}
          onToggleChat={() => setIsChatOpen(!isChatOpen)}
          onOpenSearch={() => setIsSearchOpen(true)}
        />

        {/* View Routing */}
        {currentView === 'home' && (
          <HomeDashboard
            repositories={repositories}
            isAnalyzing={isAnalyzing}
            indexingProgress={indexingProgress}
            indexingStage={indexingStage}
            onAnalyzeUrl={handleAnalyzeUrl}
            onSelectRepo={handleSelectRepo}
            onOpenExplorer={() => setCurrentView('explorer')}
          />
        )}

        {currentView === 'repositories' && (
          <HomeDashboard
            repositories={repositories}
            isAnalyzing={isAnalyzing}
            indexingProgress={indexingProgress}
            indexingStage={indexingStage}
            onAnalyzeUrl={handleAnalyzeUrl}
            onSelectRepo={handleSelectRepo}
            onOpenExplorer={() => setCurrentView('explorer')}
          />
        )}

        {currentView === 'analytics' && (
          <AnalyticsView
            graph={graph}
            nodes={layoutNodes}
            clusters={clusters}
            onSelectNode={setSelectedNode}
            onOpenExplorer={() => setCurrentView('explorer')}
          />
        )}

        {currentView === 'settings' && (
          <div style={{ padding: '40px', color: '#fff' }}>
            <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '12px' }}>Astrograph Settings</h1>
            <p style={{ color: '#94a3b8', fontSize: '13px', marginBottom: '24px' }}>
              Configure FastAPI backend URL, 3D rendering quality, and Gemini AI credentials.
            </p>
            <div style={{ background: 'rgba(15,23,42,0.8)', padding: '24px', borderRadius: '12px', maxWidth: '500px' }}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: '12px', marginBottom: '6px' }}>
                  Backend Endpoint Proxy:
                </label>
                <input
                  type="text"
                  readOnly
                  value="http://localhost:8000/api/v1"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    background: '#070a13',
                    border: '1px solid rgba(255,255,255,0.1)',
                    color: '#38bdf8',
                    fontFamily: 'JetBrains Mono, monospace',
                  }}
                />
              </div>
              <div>
                <label style={{ display: 'block', color: '#94a3b8', fontSize: '12px', marginBottom: '6px' }}>
                  3D WebGL Rendering Mode:
                </label>
                <div style={{ color: '#10b981', fontSize: '12px' }}>● ACESFilmicToneMapping (Antialiased)</div>
              </div>
            </div>
          </div>
        )}

        {currentView === 'explorer' && (
          <div style={{ flex: 1, display: 'flex', position: 'relative', overflow: 'hidden' }}>
            {/* Graph Canvas Container (3D Three.js or 2D SVG) */}
            <main style={{ flex: 1, height: '100%', position: 'relative' }}>
              {viewMode === '3d' ? (
                <GalaxyCanvas3D
                  nodes={layoutNodes}
                  edges={graph?.edges || []}
                  selectedNodeId={selectedNode?.id || null}
                  focusNodeId={focusNodeId}
                  activeWorkflow={activeWorkflow}
                  activeTypeFilter={activeFilter}
                  onSelectNode={setSelectedNode}
                />
              ) : (
                <GalaxyCanvas2D
                  nodes={layoutNodes}
                  edges={graph?.edges || []}
                  selectedNodeId={selectedNode?.id || null}
                  activeWorkflow={activeWorkflow}
                  activeTypeFilter={activeFilter}
                  onSelectNode={setSelectedNode}
                />
              )}

              {/* Execution Workflow Bar (Bottom Center) */}
              <WorkflowBar
                workflows={graph?.workflows || []}
                activeWorkflow={activeWorkflow}
                onSelectWorkflow={setActiveWorkflow}
                onFlyToNode={handleFlyToNode}
              />
            </main>

            {/* Right Node Inspector Details Sidebar */}
            {selectedNode && (
              <NodeInspector
                node={selectedNode}
                allNodes={layoutNodes}
                allEdges={graph?.edges || []}
                onSelectNode={setSelectedNode}
                onClose={() => setSelectedNode(null)}
              />
            )}
          </div>
        )}
      </div>

      {/* Autonomous AI Copilot Drawer */}
      <AIChatDrawer
        isOpen={isChatOpen}
        repoName={graph?.repo_name || 'Repository'}
        allNodes={layoutNodes}
        onClose={() => setIsChatOpen(false)}
        onFlyToNode={handleFlyToNode}
      />

      {/* Search Palette (Ctrl + K) */}
      <SearchModal
        isOpen={isSearchOpen}
        nodes={layoutNodes}
        onClose={() => setIsSearchOpen(false)}
        onSelectNode={(node) => {
          setSelectedNode(node)
          handleFlyToNode(node.id)
        }}
      />
    </div>
  )
}

export default App
