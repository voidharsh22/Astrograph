/**
 * Astral Cartographer — Main Sidebar Navigation
 * Exact match to the Astrograph dashboard sidebar
 */

import React from 'react'

export type NavView = 'home' | 'repositories' | 'explorer' | 'analytics' | 'settings'

interface SidebarProps {
  currentView: NavView
  onSelectView: (view: NavView) => void
}

export const Sidebar: React.FC<SidebarProps> = ({ currentView, onSelectView }) => {
  const navItems: Array<{ id: NavView; label: string; icon: string }> = [
    { id: 'home', label: 'Home', icon: '🏠' },
    { id: 'repositories', label: 'Repositories', icon: '📁' },
    { id: 'explorer', label: 'Graph Explorer', icon: '🪐' },
    { id: 'analytics', label: 'Analytics', icon: '📊' },
    { id: 'settings', label: 'Settings', icon: '⚙️' },
  ]

  return (
    <aside className="sidebar">
      {/* Brand Logo & Title */}
      <div className="brand-section">
        <div className="brand-logo-wrap">
          <svg viewBox="0 0 100 100" width="30" height="30" fill="none">
            <circle cx="50" cy="50" r="22" fill="#f97316" filter="drop-shadow(0 0 8px #f97316)" />
            <ellipse
              cx="50"
              cy="50"
              rx="42"
              ry="16"
              stroke="#fb923c"
              strokeWidth="4"
              transform="rotate(-25 50 50)"
            />
          </svg>
        </div>
        <div className="brand-title">Astrograph</div>
      </div>

      {/* Nav Links */}
      <nav className="nav-links">
        {navItems.map((item) => {
          const isActive = currentView === item.id
          return (
            <button
              key={item.id}
              onClick={() => onSelectView(item.id)}
              className={`nav-item ${isActive ? 'active' : ''}`}
            >
              <span style={{ fontSize: '15px' }}>{item.icon}</span>
              <span>{item.label}</span>
            </button>
          )
        })}
      </nav>

      {/* Sidebar Footer */}
      <div className="sidebar-footer">
        <div className="sidebar-tagline">
          Code is a map.<br />
          <span>We help you read it.</span>
        </div>
      </div>
    </aside>
  )
}
