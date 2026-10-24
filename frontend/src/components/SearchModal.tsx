/**
 * Astral Cartographer — Universal Search Palette (Ctrl + K)
 * Instant autocomplete search over all files, functions, and classes with camera jump
 */

import React, { useEffect, useState } from 'react'
import { GraphNode } from '../types/galaxy'

interface SearchModalProps {
  isOpen: boolean
  nodes: GraphNode[]
  onClose: () => void
  onSelectNode: (node: GraphNode) => void
}

export const SearchModal: React.FC<SearchModalProps> = ({
  isOpen,
  nodes,
  onClose,
  onSelectNode,
}) => {
  const [query, setQuery] = useState('')

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        // Toggle or open
      }
      if (e.key === 'Escape' && isOpen) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const filtered = query.trim()
    ? nodes
        .filter(
          (n) =>
            n.label.toLowerCase().includes(query.toLowerCase()) ||
            n.path.toLowerCase().includes(query.toLowerCase())
        )
        .slice(0, 10)
    : nodes.slice(0, 8)

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(5, 8, 16, 0.75)',
        backdropFilter: 'blur(10px)',
        zIndex: 100,
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'center',
        paddingTop: '12vh',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '560px',
          background: 'rgba(15, 23, 42, 0.95)',
          border: '1px solid rgba(249, 115, 22, 0.35)',
          borderRadius: '16px',
          boxShadow: '0 24px 64px rgba(0,0,0,0.8), 0 0 32px rgba(249, 115, 22, 0.15)',
          overflow: 'hidden',
          animation: 'fadeIn 0.15s ease-out',
        }}
      >
        {/* Search Input */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            padding: '16px 20px',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          }}
        >
          <span style={{ fontSize: '18px', color: '#fb923c' }}>🔍</span>
          <input
            autoFocus
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search nodes, functions, classes, files…"
            style={{
              flex: 1,
              background: 'transparent',
              border: 'none',
              outline: 'none',
              color: '#fff',
              fontSize: '15px',
              fontFamily: 'Outfit, sans-serif',
            }}
          />
          <span
            style={{
              fontSize: '11px',
              padding: '2px 6px',
              borderRadius: '4px',
              background: 'rgba(255, 255, 255, 0.08)',
              color: '#94a3b8',
            }}
          >
            ESC to close
          </span>
        </div>

        {/* Results List */}
        <div style={{ maxHeight: '360px', overflowY: 'auto', padding: '8px' }}>
          {filtered.length === 0 ? (
            <div style={{ padding: '24px', textAlign: 'center', color: '#64748b' }}>
              No celestial symbols match "{query}"
            </div>
          ) : (
            filtered.map((node) => (
              <div
                key={node.id}
                onClick={() => {
                  onSelectNode(node)
                  onClose()
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '10px 14px',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(249, 115, 22, 0.12)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span
                    style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      background: node.color || '#38bdf8',
                    }}
                  />
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
                      {node.label}
                    </div>
                    <div
                      style={{
                        fontSize: '11px',
                        color: '#64748b',
                        fontFamily: 'JetBrains Mono, monospace',
                      }}
                    >
                      {node.path}
                    </div>
                  </div>
                </div>

                <span
                  style={{
                    fontSize: '10px',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    padding: '2px 8px',
                    borderRadius: '10px',
                    background: 'rgba(255, 255, 255, 0.06)',
                    color: node.color || '#38bdf8',
                  }}
                >
                  {node.type}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
