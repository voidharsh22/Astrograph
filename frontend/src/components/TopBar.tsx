/**
 * Astral Cartographer — Top Bar and View Mode Switcher
 * Contains breadcrumbs, 2D/3D Graph toggle, filter pills, search bar, and AI Copilot launcher
 */

import React from 'react'
import { NodeType } from '../types/galaxy'

interface TopBarProps {
  repoName: string
  viewMode: '3d' | '2d'
  activeFilter: string
  isChatOpen: boolean
  isBackendConnected: boolean
  onToggleViewMode: (mode: '3d' | '2d') => void
  onSelectFilter: (filter: string) => void
  onToggleChat: () => void
  onOpenSearch: () => void
}

export const TopBar: React.FC<TopBarProps> = ({
  repoName,
  viewMode,
  activeFilter,
  isChatOpen,
  isBackendConnected,
  onToggleViewMode,
  onSelectFilter,
  onToggleChat,
  onOpenSearch,
}) => {
  const filterOptions: Array<{ id: string; label: string; color?: string }> = [
    { id: 'all', label: 'All' },
    { id: 'file', label: 'File', color: '#38bdf8' },
    { id: 'class', label: 'Class', color: '#10b981' },
    { id: 'function', label: 'Function', color: '#a855f7' },
    { id: 'directory', label: 'Directory', color: '#f59e0b' },
  ]

  return (
    <header className="topbar">
      {/* Breadcrumbs */}
      <div className="breadcrumbs">
        <span>Repositories</span>
        <span>›</span>
        <span style={{ color: '#fb923c' }}>{repoName}</span>
        <span>›</span>
        <span className="crumb-active">Graph Explorer</span>

        {/* Backend Connectivity Status Dot */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '5px',
            marginLeft: '14px',
            padding: '2px 8px',
            borderRadius: '10px',
            background: isBackendConnected ? 'rgba(16, 185, 129, 0.12)' : 'rgba(239, 68, 68, 0.12)',
            fontSize: '11px',
            color: isBackendConnected ? '#10b981' : '#ef4444',
          }}
        >
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: isBackendConnected ? '#10b981' : '#ef4444',
              boxShadow: isBackendConnected ? '0 0 6px #10b981' : '0 0 6px #ef4444',
            }}
          />
          {isBackendConnected ? 'FastAPI Online' : 'Offline / Demo'}
        </div>
      </div>

      {/* Center: 2D / 3D Toggle & Filter Pills */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {/* 2D vs 3D Switcher (Matching Screen 3) */}
        <div
          style={{
            display: 'flex',
            background: 'rgba(15, 23, 42, 0.9)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '8px',
            padding: '3px',
            gap: '2px',
          }}
        >
          <button
            onClick={() => onToggleViewMode('2d')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 12px',
              borderRadius: '6px',
              background: viewMode === '2d' ? 'var(--brand-gradient)' : 'transparent',
              color: viewMode === '2d' ? '#fff' : '#94a3b8',
              border: 'none',
              fontWeight: 600,
              fontSize: '12px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <span>🗺️</span> 2D Graph
          </button>
          <button
            onClick={() => onToggleViewMode('3d')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '5px 14px',
              borderRadius: '6px',
              background: viewMode === '3d' ? 'var(--brand-gradient)' : 'transparent',
              color: viewMode === '3d' ? '#fff' : '#94a3b8',
              border: 'none',
              fontWeight: 600,
              fontSize: '12px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
              boxShadow: viewMode === '3d' ? '0 0 12px rgba(249, 115, 22, 0.4)' : 'none',
            }}
          >
            <span>🪐</span> 3D Galaxy
          </button>
        </div>

        {/* Node Taxonomy Filter Pills */}
        <div
          style={{
            display: 'flex',
            background: 'rgba(15, 23, 42, 0.6)',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            borderRadius: '20px',
            padding: '2px 4px',
            gap: '2px',
          }}
        >
          {filterOptions.map((opt) => {
            const isSelected = activeFilter === opt.id
            return (
              <button
                key={opt.id}
                onClick={() => onSelectFilter(opt.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                  padding: '4px 10px',
                  borderRadius: '16px',
                  background: isSelected ? 'rgba(255, 255, 255, 0.12)' : 'transparent',
                  color: isSelected ? '#fff' : '#94a3b8',
                  border: 'none',
                  fontSize: '11.5px',
                  fontWeight: isSelected ? 600 : 500,
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                {opt.color && (
                  <span
                    style={{
                      width: '6px',
                      height: '6px',
                      borderRadius: '50%',
                      background: opt.color,
                      boxShadow: isSelected ? `0 0 6px ${opt.color}` : 'none',
                    }}
                  />
                )}
                {opt.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Right Controls: Search, Copilot, Avatar */}
      <div className="topbar-right">
        {/* Search Input Trigger */}
        <div className="search-box-pill" onClick={onOpenSearch}>
          <span>🔍</span>
          <span>Search nodes, files, symbols…</span>
          <span className="search-shortcut">⌘K</span>
        </div>

        {/* AI Copilot Trigger Button */}
        <button
          onClick={onToggleChat}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 14px',
            borderRadius: '20px',
            background: isChatOpen
              ? 'var(--brand-gradient)'
              : 'linear-gradient(135deg, rgba(249, 115, 22, 0.2) 0%, rgba(168, 85, 247, 0.2) 100%)',
            border: '1px solid rgba(249, 115, 22, 0.4)',
            color: '#fff',
            fontWeight: 600,
            fontSize: '12px',
            cursor: 'pointer',
            boxShadow: isChatOpen ? '0 0 16px rgba(249, 115, 22, 0.5)' : 'none',
            transition: 'all 0.2s ease',
          }}
        >
          <span>✨</span>
          <span>AI Copilot</span>
        </button>

        {/* User Avatar */}
        <div className="user-profile-badge">
          <div className="avatar-circle">HN</div>
          <span>Harsh</span>
        </div>
      </div>
    </header>
  )
}
