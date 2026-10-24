/**
 * Astral Cartographer — Home Dashboard View
 * Exact match to Screen 1 from Astrograph snapshots:
 * Hero section, New Analysis input with live indexing, Your Repositories grid, Quick Stats, and Recent Activity.
 */

import React, { useState } from 'react'
import { RepositoryItem } from '../types/galaxy'

interface HomeDashboardProps {
  repositories: RepositoryItem[]
  isAnalyzing: boolean
  indexingProgress: number
  indexingStage: string | null
  onAnalyzeUrl: (url: string) => void
  onSelectRepo: (repo: RepositoryItem) => void
  onOpenExplorer: () => void
}

export const HomeDashboard: React.FC<HomeDashboardProps> = ({
  repositories,
  isAnalyzing,
  indexingProgress,
  indexingStage,
  onAnalyzeUrl,
  onSelectRepo,
  onOpenExplorer,
}) => {
  const [repoInput, setRepoInput] = useState('https://github.com/voidharsh22/Astrograph')
  const [searchQuery, setSearchQuery] = useState('')

  // Pre-populated demo/showcase repositories matching Screen 1 snapshot
  const defaultShowcaseRepos: RepositoryItem[] = [
    {
      id: 'demo-heritage-guard',
      url: 'https://github.com/Sammmyyyyyy/HeritageGuard',
      owner: 'Sammmyyyyyy',
      name: 'HeritageGuard',
      branch: 'main',
      created_at: '2026-10-21T07:00:00Z',
      last_indexed_at: '2026-10-24T12:00:00Z',
      status: 'completed',
    },
    {
      id: 'demo-thermoscope',
      url: 'https://github.com/Sammmyyyyyy/ThermoScope',
      owner: 'Sammmyyyyyy',
      name: 'ThermoScope',
      branch: 'main',
      created_at: '2026-10-21T07:00:00Z',
      last_indexed_at: '2026-10-24T11:30:00Z',
      status: 'completed',
    },
    {
      id: 'demo-astrograph',
      url: 'https://github.com/voidharsh22/Astrograph',
      owner: 'voidharsh22',
      name: 'Astrograph',
      branch: 'dev',
      created_at: '2026-10-22T01:00:00Z',
      last_indexed_at: '2026-10-24T12:45:00Z',
      status: 'completed',
    },
    {
      id: 'demo-react',
      url: 'https://github.com/facebook/react',
      owner: 'facebook',
      name: 'react',
      branch: 'main',
      created_at: '2026-10-20T00:00:00Z',
      last_indexed_at: '2026-10-23T18:00:00Z',
      status: 'completed',
    },
    {
      id: 'demo-node',
      url: 'https://github.com/nodejs/node',
      owner: 'nodejs',
      name: 'node',
      branch: 'main',
      created_at: '2026-10-20T00:00:00Z',
      last_indexed_at: '2026-10-23T14:00:00Z',
      status: 'completed',
    },
    {
      id: 'demo-vscode',
      url: 'https://github.com/microsoft/vscode',
      owner: 'microsoft',
      name: 'vscode',
      branch: 'main',
      created_at: '2026-10-20T00:00:00Z',
      last_indexed_at: '2026-10-23T10:00:00Z',
      status: 'completed',
    },
  ]

  // Merge live backend repos with showcase repos
  const allRepos = repositories.length > 0 ? repositories : defaultShowcaseRepos

  const filteredRepos = allRepos.filter(
    (r) =>
      r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.owner.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const handleStartAnalysis = (e: React.FormEvent) => {
    e.preventDefault()
    if (!repoInput.trim() || isAnalyzing) return
    onAnalyzeUrl(repoInput.trim())
  }

  return (
    <div
      style={{
        flex: 1,
        height: '100%',
        overflowY: 'auto',
        padding: '32px 40px',
        display: 'flex',
        flexDirection: 'column',
        gap: '32px',
        background: 'radial-gradient(circle at 65% 15%, rgba(249, 115, 22, 0.1) 0%, transparent 45%), #070a13',
      }}
    >
      {/* Top Hero Section + New Analysis Card */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1.2fr 1fr',
          gap: '36px',
          alignItems: 'center',
        }}
      >
        {/* Left Hero Text */}
        <div>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 12px',
              borderRadius: '20px',
              border: '1px solid rgba(249, 115, 22, 0.4)',
              background: 'rgba(249, 115, 22, 0.08)',
              color: '#fb923c',
              fontSize: '11px',
              fontWeight: 700,
              letterSpacing: '1px',
              marginBottom: '16px',
              textTransform: 'uppercase',
            }}
          >
            <span>✨</span> AI-POWERED CODEBASE INTELLIGENCE
          </div>

          <h1
            style={{
              fontSize: '48px',
              fontWeight: 800,
              fontFamily: 'Space Grotesk, Outfit, sans-serif',
              lineHeight: 1.1,
              marginBottom: '16px',
              letterSpacing: '-1px',
              color: '#fff',
            }}
          >
            Understand your <br />
            <span
              style={{
                background: 'linear-gradient(135deg, #fb923c 0%, #ea580c 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                fontStyle: 'italic',
              }}
            >
              codebase.
            </span>
          </h1>

          <p
            style={{
              fontSize: '15px',
              color: '#94a3b8',
              lineHeight: 1.6,
              maxWidth: '460px',
            }}
          >
            Turn any GitHub repository into an interactive 3D celestial map of its architecture,
            dependencies, and execution logic.
          </p>
        </div>

        {/* Right: New Analysis Card (From Screen 1) */}
        <div
          style={{
            background: 'rgba(15, 23, 42, 0.75)',
            backdropFilter: 'blur(16px)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '16px',
            padding: '28px',
            boxShadow: '0 16px 40px rgba(0,0,0,0.5), 0 0 30px rgba(249, 115, 22, 0.12)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
            <span style={{ fontSize: '18px', color: '#fb923c' }}>✨</span>
            <h2 style={{ fontSize: '17px', fontWeight: 700, color: '#fff', margin: 0 }}>New Analysis</h2>
          </div>
          <p style={{ fontSize: '12.5px', color: '#64748b', marginBottom: '18px' }}>
            Enter a GitHub repository URL to build its 3D galaxy graph.
          </p>

          <form onSubmit={handleStartAnalysis}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                background: 'rgba(7, 10, 19, 0.9)',
                border: '1px solid rgba(255, 255, 255, 0.12)',
                borderRadius: '10px',
                padding: '4px 6px 4px 14px',
                gap: '10px',
                marginBottom: '14px',
              }}
            >
              <span style={{ color: '#94a3b8', fontSize: '16px' }}>🐙</span>
              <input
                type="text"
                value={repoInput}
                onChange={(e) => setRepoInput(e.target.value)}
                placeholder="https://github.com/owner/repo"
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: 'none',
                  outline: 'none',
                  color: '#fff',
                  fontSize: '13px',
                  fontFamily: 'JetBrains Mono, monospace',
                }}
              />
              <button
                type="submit"
                disabled={isAnalyzing}
                style={{
                  background: 'var(--brand-gradient)',
                  border: 'none',
                  borderRadius: '8px',
                  padding: '9px 18px',
                  color: '#fff',
                  fontWeight: 600,
                  fontSize: '13px',
                  cursor: isAnalyzing ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  boxShadow: '0 4px 14px rgba(249, 115, 22, 0.4)',
                }}
              >
                {isAnalyzing ? (
                  <>
                    <span style={{ animation: 'spinSlow 1s linear infinite' }}>🪐</span>
                    Indexing…
                  </>
                ) : (
                  <>
                    Analyse <span>→</span>
                  </>
                )}
              </button>
            </div>
          </form>

          {/* Indexing Progress Indicator */}
          {isAnalyzing && (
            <div style={{ marginBottom: '14px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#fb923c', marginBottom: '6px' }}>
                <span>{indexingStage || 'Cloning and Tree-Sitter parsing…'}</span>
                <span>{indexingProgress}%</span>
              </div>
              <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px', overflow: 'hidden' }}>
                <div
                  style={{
                    width: `${indexingProgress}%`,
                    height: '100%',
                    background: 'var(--brand-gradient)',
                    transition: 'width 0.3s ease',
                  }}
                />
              </div>
            </div>
          )}

          {/* Trust Checkmarks */}
          <div style={{ display: 'flex', gap: '16px', fontSize: '11.5px', color: '#94a3b8' }}>
            <span>✓ Public repositories only</span>
            <span>✓ Fast Tree-Sitter indexing</span>
            <span>✓ 3D AI-powered graph</span>
          </div>
        </div>
      </div>

      {/* Main Grid: Your Repositories + Right Stats Column */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 310px',
          gap: '32px',
          alignItems: 'flex-start',
        }}
      >
        {/* Left Column: Your Repositories Cards */}
        <div>
          {/* Header & Search */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '20px',
            }}
          >
            <div>
              <h2 style={{ fontSize: '18px', fontWeight: 700, color: '#fff', marginBottom: '4px' }}>
                Your Repositories
              </h2>
              <p style={{ fontSize: '12px', color: '#64748b' }}>
                Access your previously analysed repositories or start exploring.
              </p>
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search repositories…"
                style={{
                  background: 'rgba(15, 23, 42, 0.6)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '8px',
                  padding: '6px 14px',
                  color: '#fff',
                  fontSize: '12.5px',
                  outline: 'none',
                }}
              />
              <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }}>
                All ▾
              </button>
            </div>
          </div>

          {/* Repo Cards Grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: '16px',
            }}
          >
            {filteredRepos.map((repo) => (
              <div
                key={repo.id}
                onClick={() => onSelectRepo(repo)}
                style={{
                  background: 'rgba(15, 23, 42, 0.7)',
                  backdropFilter: 'blur(12px)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '12px',
                  padding: '18px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = 'translateY(-2px)'
                  e.currentTarget.style.borderColor = 'rgba(249, 115, 22, 0.4)'
                  e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.5), 0 0 16px rgba(249, 115, 22, 0.15)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = 'none'
                  e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.08)'
                  e.currentTarget.style.boxShadow = 'none'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '16px' }}>🐙</span>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
                      {repo.owner}/{repo.name}
                    </span>
                  </div>
                  <span
                    style={{
                      fontSize: '10px',
                      padding: '2px 8px',
                      borderRadius: '10px',
                      background: 'rgba(255, 255, 255, 0.06)',
                      color: '#94a3b8',
                    }}
                  >
                    Public
                  </span>
                </div>

                <p style={{ fontSize: '12px', color: '#94a3b8', lineHeight: 1.4, margin: 0, minHeight: '34px' }}>
                  Codebase analysis and 3D celestial repository graph visualization.
                </p>

                {/* Tags */}
                <div style={{ display: 'flex', gap: '6px' }}>
                  {['Python', 'FastAPI', 'Tree-Sitter'].map((tag) => (
                    <span
                      key={tag}
                      style={{
                        fontSize: '10px',
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: 'rgba(56, 189, 248, 0.1)',
                        color: '#38bdf8',
                        fontFamily: 'JetBrains Mono, monospace',
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>

                {/* Footer Stats & Status */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    paddingTop: '8px',
                    borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                    fontSize: '11px',
                    color: '#64748b',
                  }}
                >
                  <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    ● Analysis complete
                  </span>
                  <span style={{ color: '#fb923c', fontWeight: 600 }}>Explore →</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right Column: Quick Stats & Recent Activity */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Quick Stats Card */}
          <div
            style={{
              background: 'rgba(15, 23, 42, 0.7)',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '12px',
              padding: '20px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
              <span style={{ color: '#fb923c' }}>📊</span>
              <h3 style={{ fontSize: '14px', fontWeight: 700, color: '#fff', margin: 0 }}>Quick Stats</h3>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px' }}>
                <div style={{ fontSize: '20px', fontWeight: 800, color: '#fff' }}>{allRepos.length}</div>
                <div style={{ fontSize: '11px', color: '#64748b' }}>Total Repositories</div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px' }}>
                <div style={{ fontSize: '20px', fontWeight: 800, color: '#10b981' }}>{allRepos.length}</div>
                <div style={{ fontSize: '11px', color: '#64748b' }}>Analyzed</div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px' }}>
                <div style={{ fontSize: '20px', fontWeight: 800, color: '#fb923c' }}>139</div>
                <div style={{ fontSize: '11px', color: '#64748b' }}>Passing Tests</div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '10px', borderRadius: '8px' }}>
                <div style={{ fontSize: '20px', fontWeight: 800, color: '#38bdf8' }}>3D</div>
                <div style={{ fontSize: '11px', color: '#64748b' }}>WebGL Celestial</div>
              </div>
            </div>
          </div>

          {/* Explore Callout Card */}
          <div
            style={{
              background: 'linear-gradient(135deg, rgba(249, 115, 22, 0.12) 0%, rgba(168, 85, 247, 0.08) 100%)',
              border: '1px solid rgba(249, 115, 22, 0.3)',
              borderRadius: '12px',
              padding: '20px',
            }}
          >
            <div style={{ fontSize: '24px', marginBottom: '8px' }}>🪐</div>
            <h4 style={{ fontSize: '14px', fontWeight: 700, color: '#fff', marginBottom: '6px' }}>
              Explore the power of graphs
            </h4>
            <p style={{ fontSize: '12px', color: '#94a3b8', lineHeight: 1.5, marginBottom: '14px' }}>
              Visualize relationships, find dependencies, and fly through your codebase galaxy in 3D.
            </p>
            <button
              onClick={onOpenExplorer}
              className="btn-primary"
              style={{ width: '100%', justifyContent: 'center' }}
            >
              Open Graph Explorer →
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
