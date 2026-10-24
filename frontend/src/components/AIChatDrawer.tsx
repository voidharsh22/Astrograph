/**
 * Astral Cartographer — Autonomous AI Codebase Intelligence Drawer
 * LangGraph-powered Q&A agent with 3D camera targeting
 */

import React, { useState } from 'react'
import { askCodebaseQuestion } from '../services/api'
import { GraphNode } from '../types/galaxy'

interface AIChatDrawerProps {
  isOpen: boolean
  repoName: string
  allNodes: GraphNode[]
  onClose: () => void
  onFlyToNode: (nodeId: string) => void
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  highlightedNodeIds?: string[]
}

export const AIChatDrawer: React.FC<AIChatDrawerProps> = ({
  isOpen,
  repoName,
  allNodes,
  onClose,
  onFlyToNode,
}) => {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'assistant',
      content: `Welcome to **Astrograph AI Intelligence**. I have indexed the knowledge graph for **${repoName}**. Ask me anything about module architectures, execution paths, or function call trees, and I'll fly your 3D camera directly to the relevant stars!`,
      highlightedNodeIds: [],
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)

  if (!isOpen) return null

  const handleSend = async (questionText?: string) => {
    const q = (questionText || input).trim()
    if (!q || loading) return

    setMessages((prev) => [...prev, { role: 'user', content: q }])
    setInput('')
    setLoading(true)

    try {
      const response = await askCodebaseQuestion(q)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: response.answer,
          highlightedNodeIds: response.highlighted_node_ids || [],
        },
      ])

      // Automatically fly camera to the first target node if present
      if (response.highlighted_node_ids && response.highlighted_node_ids.length > 0) {
        onFlyToNode(response.highlighted_node_ids[0])
      }
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: `⚠️ Failed to query agent: ${err.message || 'Server error'}. Please verify your backend server is running.`,
        },
      ])
    } finally {
      setLoading(false)
    }
  }

  const sampleQuestions = [
    'How does request routing and application setup work?',
    'Trace dependencies between services and data models',
    'Which classes have the highest PageRank centrality?',
  ]

  return (
    <div
      style={{
        position: 'fixed',
        bottom: '24px',
        right: '360px',
        width: '420px',
        height: '560px',
        background: 'rgba(11, 15, 25, 0.96)',
        backdropFilter: 'blur(24px)',
        border: '1px solid rgba(249, 115, 22, 0.35)',
        boxShadow: '0 16px 48px rgba(0,0,0,0.7), 0 0 30px rgba(249, 115, 22, 0.2)',
        borderRadius: '16px',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 60,
        overflow: 'hidden',
        animation: 'fadeIn 0.2s ease-out',
      }}
    >
      {/* Drawer Header */}
      <div
        style={{
          padding: '16px 20px',
          background: 'linear-gradient(90deg, rgba(249, 115, 22, 0.15) 0%, rgba(168, 85, 247, 0.1) 100%)',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #f97316 0%, #a855f7 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '14px',
            }}
          >
            🪐
          </div>
          <div>
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#fff' }}>Astrograph Copilot</div>
            <div style={{ fontSize: '10px', color: '#fb923c' }}>Autonomous 3D Spatial Agent</div>
          </div>
        </div>

        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: '#94a3b8',
            fontSize: '18px',
            cursor: 'pointer',
          }}
        >
          ✕
        </button>
      </div>

      {/* Messages Feed */}
      <div
        style={{
          flex: 1,
          padding: '16px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
        }}
      >
        {messages.map((m, idx) => (
          <div
            key={idx}
            style={{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '88%',
              padding: '10px 14px',
              borderRadius: m.role === 'user' ? '14px 14px 2px 14px' : '14px 14px 14px 2px',
              background:
                m.role === 'user'
                  ? 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)'
                  : 'rgba(255, 255, 255, 0.05)',
              border: m.role === 'user' ? 'none' : '1px solid rgba(255, 255, 255, 0.08)',
              color: '#f8fafc',
              fontSize: '12.5px',
              lineHeight: '1.45',
            }}
          >
            <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>

            {/* Target 3D Nodes Badges */}
            {m.highlightedNodeIds && m.highlightedNodeIds.length > 0 && (
              <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                <div style={{ fontSize: '10px', color: '#fb923c', fontWeight: 600, marginBottom: '6px' }}>
                  🎯 CAMERA TARGETS (CLICK TO FLY):
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                  {m.highlightedNodeIds.map((nodeId) => {
                    const matched = allNodes.find((n) => n.id === nodeId)
                    return (
                      <button
                        key={nodeId}
                        onClick={() => onFlyToNode(nodeId)}
                        style={{
                          background: 'rgba(249, 115, 22, 0.16)',
                          border: '1px solid rgba(249, 115, 22, 0.4)',
                          color: '#ffedd5',
                          borderRadius: '6px',
                          padding: '3px 8px',
                          fontSize: '11px',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        🚀 {matched?.label || nodeId}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div
            style={{
              alignSelf: 'flex-start',
              padding: '10px 14px',
              borderRadius: '12px',
              background: 'rgba(255, 255, 255, 0.05)',
              color: '#fb923c',
              fontSize: '12px',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}
          >
            <span style={{ animation: 'spinSlow 1.5s linear infinite' }}>🪐</span> Reasoning over galaxy graph topology…
          </div>
        )}
      </div>

      {/* Suggested Quick Prompts */}
      <div style={{ padding: '0 16px 8px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <div style={{ fontSize: '10px', color: '#64748b', fontWeight: 600 }}>SUGGESTIONS:</div>
        <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', paddingBottom: '4px' }}>
          {sampleQuestions.map((sq, i) => (
            <button
              key={i}
              onClick={() => handleSend(sq)}
              style={{
                whiteSpace: 'nowrap',
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                color: '#cbd5e1',
                padding: '4px 10px',
                borderRadius: '12px',
                fontSize: '11px',
                cursor: 'pointer',
              }}
            >
              {sq}
            </button>
          ))}
        </div>
      </div>

      {/* Input Bar */}
      <div
        style={{
          padding: '12px 16px',
          borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          display: 'flex',
          gap: '8px',
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          placeholder="Ask about architecture, functions, flows…"
          style={{
            flex: 1,
            background: 'rgba(15, 23, 42, 0.8)',
            border: '1px solid rgba(255, 255, 255, 0.12)',
            borderRadius: '8px',
            padding: '8px 12px',
            color: '#fff',
            fontSize: '12.5px',
            outline: 'none',
          }}
        />
        <button
          onClick={() => handleSend()}
          disabled={loading || !input.trim()}
          style={{
            background: 'var(--brand-gradient)',
            border: 'none',
            borderRadius: '8px',
            padding: '0 14px',
            color: '#fff',
            fontWeight: 600,
            cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
            opacity: loading || !input.trim() ? 0.5 : 1,
          }}
        >
          Send
        </button>
      </div>
    </div>
  )
}
