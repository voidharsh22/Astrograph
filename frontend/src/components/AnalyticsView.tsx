/**
 * Astral Cartographer — Analytics View
 * Displays high-level galaxy metrics, Louvain constellation breakdowns, and PageRank leaderboards
 */

import React from 'react'
import { CelestialClusterInfo } from '../services/galaxyLayout'
import { AstralGraph, GraphNode } from '../types/galaxy'

interface AnalyticsViewProps {
  graph: AstralGraph | null
  nodes: GraphNode[]
  clusters: CelestialClusterInfo[]
  onSelectNode: (node: GraphNode) => void
  onOpenExplorer: () => void
}

export const AnalyticsView: React.FC<AnalyticsViewProps> = ({
  graph,
  nodes,
  clusters,
  onSelectNode,
  onOpenExplorer,
}) => {
  if (!graph) return null

  // Sort nodes by PageRank centrality
  const topCentralNodes = [...nodes]
    .sort((a, b) => (b.metrics?.centrality ?? 0) - (a.metrics?.centrality ?? 0))
    .slice(0, 8)

  return (
    <div
      style={{
        flex: 1,
        height: '100%',
        overflowY: 'auto',
        padding: '36px 44px',
        background: '#070a13',
        display: 'flex',
        flexDirection: 'column',
        gap: '28px',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: '26px', fontWeight: 800, color: '#fff', marginBottom: '6px' }}>
            Galaxy Analytics — {graph.repo_name}
          </h1>
          <p style={{ fontSize: '13px', color: '#94a3b8' }}>
            Quantitative graph theory metrics, Louvain community clusters, and structural centrality.
          </p>
        </div>
        <button onClick={onOpenExplorer} className="btn-primary">
          Open in 3D Galaxy 🪐
        </button>
      </div>

      {/* Metric Cards Banner */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '16px',
        }}
      >
        <div style={cardStyle}>
          <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>Total Celestial Nodes</div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#f8fafc' }}>{graph.nodes.length}</div>
          <div style={{ fontSize: '11px', color: '#38bdf8', marginTop: '4px' }}>
            {graph.metadata.total_files} files • {graph.metadata.total_functions} functions
          </div>
        </div>

        <div style={cardStyle}>
          <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>Dependency Edges</div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#f8fafc' }}>{graph.edges.length}</div>
          <div style={{ fontSize: '11px', color: '#a855f7', marginTop: '4px' }}>AST imports, calls, inherits</div>
        </div>

        <div style={cardStyle}>
          <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>Constellation Clusters</div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#f97316' }}>{clusters.length}</div>
          <div style={{ fontSize: '11px', color: '#fb923c', marginTop: '4px' }}>Louvain community partitions</div>
        </div>

        <div style={cardStyle}>
          <div style={{ fontSize: '12px', color: '#94a3b8', marginBottom: '4px' }}>Execution Workflows</div>
          <div style={{ fontSize: '28px', fontWeight: 800, color: '#10b981' }}>{graph.workflows.length}</div>
          <div style={{ fontSize: '11px', color: '#34d399', marginTop: '4px' }}>Traced request pathways</div>
        </div>
      </div>

      {/* Two Column Layout: Clusters Breakdown & PageRank Leaderboard */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: '24px' }}>
        {/* Louvain Clusters Card */}
        <div style={{ ...cardStyle, display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#fff', margin: 0 }}>
            Galactic Constellations (Louvain Communities)
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {clusters.map((c) => (
              <div
                key={c.id}
                style={{
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid rgba(255,255,255,0.06)',
                  borderRadius: '10px',
                  padding: '14px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span
                      style={{
                        width: '10px',
                        height: '10px',
                        borderRadius: '50%',
                        background: c.color,
                        boxShadow: `0 0 8px ${c.color}`,
                      }}
                    />
                    <span style={{ fontSize: '14px', fontWeight: 600, color: '#fff' }}>{c.name}</span>
                  </div>
                  <span style={{ fontSize: '11px', color: '#94a3b8' }}>{c.nodeCount} nodes</span>
                </div>
                {c.summary && (
                  <p style={{ fontSize: '12px', color: '#cbd5e1', lineHeight: 1.45, margin: 0 }}>
                    {c.summary}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Centrality PageRank Leaderboard */}
        <div style={{ ...cardStyle, display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h2 style={{ fontSize: '16px', fontWeight: 700, color: '#fff', margin: 0 }}>
            Top Architectural Hubs (PageRank)
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {topCentralNodes.map((n, idx) => (
              <div
                key={n.id}
                onClick={() => {
                  onSelectNode(n)
                  onOpenExplorer()
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  background: 'rgba(255, 255, 255, 0.02)',
                  border: '1px solid rgba(255, 255, 255, 0.05)',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(249, 115, 22, 0.1)'
                  e.currentTarget.style.borderColor = 'rgba(249, 115, 22, 0.3)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.02)'
                  e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.05)'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '12px', fontWeight: 700, color: '#64748b', width: '16px' }}>
                    #{idx + 1}
                  </span>
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>{n.label}</div>
                    <div style={{ fontSize: '10.5px', color: '#64748b', fontFamily: 'JetBrains Mono, monospace' }}>
                      {n.path}
                    </div>
                  </div>
                </div>

                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '12px', fontWeight: 700, color: '#38bdf8' }}>
                    {((n.metrics?.centrality ?? 0) * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '10px', color: '#64748b' }}>centrality</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

const cardStyle: React.CSSProperties = {
  background: 'rgba(15, 23, 42, 0.7)',
  border: '1px solid rgba(255, 255, 255, 0.08)',
  borderRadius: '12px',
  padding: '20px',
  backdropFilter: 'blur(12px)',
}
