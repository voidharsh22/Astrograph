/**
 * Astral Cartographer — Right Node Inspector Panel
 * Exact replication of the Details / References / Files sidebar from Astrograph snapshots
 */

import React, { useState } from 'react'
import { GraphEdge, GraphNode, NodeType } from '../types/galaxy'

interface NodeInspectorProps {
  node: GraphNode | null
  allNodes: GraphNode[]
  allEdges: GraphEdge[]
  onSelectNode: (node: GraphNode) => void
  onClose: () => void
  onTraceWorkflow?: () => void
}

export const NodeInspector: React.FC<NodeInspectorProps> = ({
  node,
  allNodes,
  allEdges,
  onSelectNode,
  onClose,
  onTraceWorkflow,
}) => {
  const [activeTab, setActiveTab] = useState<'details' | 'references' | 'files'>('details')

  if (!node) return null

  // Compute relationships
  const incoming = allEdges.filter((e) => e.target === node.id)
  const outgoing = allEdges.filter((e) => e.source === node.id)

  const callsCount = outgoing.filter((e) => e.relation === 'calls').length
  const calledByCount = incoming.filter((e) => e.relation === 'calls').length
  const importsCount = outgoing.filter((e) => e.relation === 'imports').length
  const containsCount = outgoing.filter((e) => e.relation === 'contains').length
  const definedInCount = incoming.filter((e) => e.relation === 'contains').length

  // Find related nodes
  const relatedNodeIds = Array.from(new Set([...incoming.map((e) => e.source), ...outgoing.map((e) => e.target)]))
  const relatedNodes = relatedNodeIds
    .map((id) => allNodes.find((n) => n.id === id))
    .filter((n): n is GraphNode => Boolean(n))
    .slice(0, 8)

  const typeBadgeColors: Record<NodeType, { color: string; bg: string }> = {
    directory: { color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.14)' },
    file: { color: '#38bdf8', bg: 'rgba(56, 189, 248, 0.14)' },
    class: { color: '#10b981', bg: 'rgba(16, 185, 129, 0.14)' },
    function: { color: '#a855f7', bg: 'rgba(168, 85, 247, 0.14)' },
  }

  const badge = typeBadgeColors[node.type] || typeBadgeColors.file

  return (
    <aside
      style={{
        width: '340px',
        height: '100%',
        background: 'rgba(11, 15, 25, 0.94)',
        backdropFilter: 'blur(20px)',
        borderLeft: '1px solid rgba(255, 255, 255, 0.08)',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 45,
        flexShrink: 0,
        overflowY: 'auto',
      }}
    >
      {/* Header Tabs */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px 0',
          borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
        }}
      >
        <div style={{ display: 'flex', gap: '20px' }}>
          {(['details', 'references', 'files'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                background: 'none',
                border: 'none',
                paddingBottom: '12px',
                color: activeTab === tab ? '#f8fafc' : '#64748b',
                fontWeight: activeTab === tab ? 600 : 500,
                fontSize: '13px',
                cursor: 'pointer',
                borderBottom: activeTab === tab ? '2px solid #f97316' : '2px solid transparent',
                textTransform: 'capitalize',
                transition: 'all 0.15s ease',
              }}
            >
              {tab}
            </button>
          ))}
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: '#64748b',
            fontSize: '16px',
            cursor: 'pointer',
            paddingBottom: '10px',
          }}
          title="Close details"
        >
          ✕
        </button>
      </div>

      <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* Node Banner Card */}
        <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
          <div
            style={{
              width: '42px',
              height: '42px',
              borderRadius: '8px',
              background: badge.bg,
              border: `1px solid ${badge.color}40`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '20px',
              flexShrink: 0,
            }}
          >
            {node.type === 'directory' ? '📁' : node.type === 'file' ? '📄' : node.type === 'class' ? '🧊' : '⚡'}
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <h2
                style={{
                  fontSize: '15px',
                  fontWeight: 600,
                  color: '#fff',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  margin: 0,
                }}
              >
                {node.label}
              </h2>
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 600,
                  textTransform: 'capitalize',
                  padding: '2px 8px',
                  borderRadius: '12px',
                  background: badge.bg,
                  color: badge.color,
                  border: `1px solid ${badge.color}30`,
                }}
              >
                {node.type}
              </span>
            </div>
            <div
              style={{
                fontSize: '11px',
                color: '#64748b',
                fontFamily: 'JetBrains Mono, monospace',
                wordBreak: 'break-all',
              }}
            >
              /{node.path}
            </div>
          </div>
        </div>

        {/* AI Summary Section */}
        {node.ai_summary && (
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(249, 115, 22, 0.08) 0%, rgba(168, 85, 247, 0.06) 100%)',
              border: '1px solid rgba(249, 115, 22, 0.25)',
              borderRadius: '10px',
              padding: '12px 14px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '11px',
                fontWeight: 600,
                color: '#fb923c',
                marginBottom: '6px',
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
              }}
            >
              ✨ Celestial AI Insight
            </div>
            <p style={{ fontSize: '12px', color: '#cbd5e1', lineHeight: '1.45', margin: 0 }}>
              {node.ai_summary}
            </p>
          </div>
        )}

        {/* Information Table Section */}
        <div>
          <h3
            style={{
              fontSize: '11px',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '1px',
              color: '#94a3b8',
              marginBottom: '12px',
            }}
          >
            Information
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={infoRowStyle}>
              <span style={{ color: '#64748b' }}>Language</span>
              <span style={{ color: '#f8fafc', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '6px' }}>
                🐍 {node.language || 'Python'}
              </span>
            </div>
            <div style={infoRowStyle}>
              <span style={{ color: '#64748b' }}>Lines of Code</span>
              <span style={{ color: '#f8fafc', fontWeight: 500 }}>{node.metrics?.loc || 0}</span>
            </div>
            <div style={infoRowStyle}>
              <span style={{ color: '#64748b' }}>Centrality (PageRank)</span>
              <span style={{ color: '#38bdf8', fontWeight: 600 }}>
                {((node.metrics?.centrality || 0) * 100).toFixed(1)}%
              </span>
            </div>
            <div style={infoRowStyle}>
              <span style={{ color: '#64748b' }}>Constellation Cluster</span>
              <span style={{ color: '#fb923c', fontWeight: 500 }}>
                Cluster #{node.position_hint?.cluster_id ?? 0}
              </span>
            </div>
          </div>
        </div>

        {/* Relationships Section (From Snapshot) */}
        <div>
          <h3
            style={{
              fontSize: '11px',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '1px',
              color: '#94a3b8',
              marginBottom: '12px',
            }}
          >
            Relationships
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={infoRowStyle}>
              <span style={{ color: '#64748b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: '#a855f7' }}>⚡</span> Calls
              </span>
              <span style={{ color: '#f8fafc', fontWeight: 600 }}>{callsCount}</span>
            </div>
            <div style={infoRowStyle}>
              <span style={{ color: '#64748b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: '#38bdf8' }}>📥</span> Called by
              </span>
              <span style={{ color: '#f8fafc', fontWeight: 600 }}>{calledByCount}</span>
            </div>
            <div style={infoRowStyle}>
              <span style={{ color: '#64748b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: '#f59e0b' }}>📁</span> Contains
              </span>
              <span style={{ color: '#f8fafc', fontWeight: 600 }}>{containsCount}</span>
            </div>
            <div style={infoRowStyle}>
              <span style={{ color: '#64748b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: '#38bdf8' }}>📦</span> Imports
              </span>
              <span style={{ color: '#f8fafc', fontWeight: 600 }}>{importsCount}</span>
            </div>
            <div style={infoRowStyle}>
              <span style={{ color: '#64748b', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: '#10b981' }}>🎯</span> Defined in
              </span>
              <span style={{ color: '#f8fafc', fontWeight: 600 }}>{definedInCount}</span>
            </div>
          </div>
        </div>

        {/* Related Nodes Navigation Section */}
        {relatedNodes.length > 0 && (
          <div>
            <h3
              style={{
                fontSize: '11px',
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '1px',
                color: '#94a3b8',
                marginBottom: '12px',
              }}
            >
              Related Nodes
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {relatedNodes.map((rn) => (
                <div
                  key={rn.id}
                  onClick={() => onSelectNode(rn)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    background: 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid rgba(255, 255, 255, 0.05)',
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(255, 255, 255, 0.07)'
                    e.currentTarget.style.borderColor = 'rgba(249, 115, 22, 0.3)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)'
                    e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.05)'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                    <span
                      style={{
                        width: '6px',
                        height: '6px',
                        borderRadius: '50%',
                        background: rn.color || '#38bdf8',
                      }}
                    />
                    <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      <div style={{ fontSize: '12px', fontWeight: 500, color: '#f8fafc' }}>{rn.label}</div>
                      <div style={{ fontSize: '10px', color: '#64748b' }}>{rn.type}</div>
                    </div>
                  </div>
                  <span style={{ color: '#64748b', fontSize: '14px' }}>›</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Action Button */}
        <button
          onClick={() => {
            alert(`Opening source file: ${node.path}`)
          }}
          style={{
            width: '100%',
            padding: '12px',
            borderRadius: '8px',
            background: 'transparent',
            border: '1px solid rgba(249, 115, 22, 0.4)',
            color: '#fb923c',
            fontWeight: 600,
            fontSize: '13px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            transition: 'all 0.15s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'rgba(249, 115, 22, 0.12)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent'
          }}
        >
          Open in Editor ↗
        </button>
      </div>
    </aside>
  )
}

const infoRowStyle: React.CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  fontSize: '12.5px',
  padding: '4px 0',
}
