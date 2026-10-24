/**
 * Astral Cartographer — Execution Workflow Player Bar
 * Controls animated glowing pulses along request lifecycles and business workflows
 */

import React from 'react'
import { Workflow } from '../types/galaxy'

interface WorkflowBarProps {
  workflows: Workflow[]
  activeWorkflow: Workflow | null
  onSelectWorkflow: (wf: Workflow | null) => void
  onFlyToNode: (nodeId: string) => void
}

export const WorkflowBar: React.FC<WorkflowBarProps> = ({
  workflows,
  activeWorkflow,
  onSelectWorkflow,
  onFlyToNode,
}) => {
  if (workflows.length === 0) return null

  return (
    <div
      style={{
        position: 'absolute',
        bottom: '24px',
        left: '50%',
        transform: 'translateX(-50%)',
        background: 'rgba(11, 15, 25, 0.92)',
        backdropFilter: 'blur(16px)',
        border: '1px solid rgba(249, 115, 22, 0.3)',
        boxShadow: '0 8px 32px rgba(0,0,0,0.6), 0 0 20px rgba(249, 115, 22, 0.15)',
        borderRadius: '30px',
        padding: '6px 14px',
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        zIndex: 30,
        maxWidth: '90%',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#fb923c', fontSize: '12px', fontWeight: 700 }}>
        <span>⚡</span> WORKFLOWS:
      </div>

      <div style={{ display: 'flex', gap: '8px', overflowX: 'auto', padding: '2px' }}>
        {workflows.map((wf) => {
          const isActive = activeWorkflow?.id === wf.id
          return (
            <button
              key={wf.id}
              onClick={() => onSelectWorkflow(isActive ? null : wf)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 12px',
                borderRadius: '20px',
                background: isActive ? 'var(--brand-gradient)' : 'rgba(255, 255, 255, 0.05)',
                border: isActive ? 'none' : '1px solid rgba(255, 255, 255, 0.08)',
                color: isActive ? '#fff' : '#cbd5e1',
                fontSize: '11.5px',
                fontWeight: isActive ? 600 : 500,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s ease',
              }}
            >
              <span>{isActive ? '⏸' : '▶'}</span>
              <span>{wf.name}</span>
              <span
                style={{
                  fontSize: '9.5px',
                  padding: '1px 6px',
                  borderRadius: '10px',
                  background: isActive ? 'rgba(0,0,0,0.25)' : 'rgba(255,255,255,0.08)',
                }}
              >
                {wf.ordered_node_ids.length} hops
              </span>
            </button>
          )
        })}
      </div>

      {activeWorkflow && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', borderLeft: '1px solid rgba(255,255,255,0.1)', paddingLeft: '10px' }}>
          <span style={{ fontSize: '11px', color: '#94a3b8' }}>Step:</span>
          {activeWorkflow.ordered_node_ids.slice(0, 4).map((nodeId, i) => (
            <button
              key={nodeId}
              onClick={() => onFlyToNode(nodeId)}
              style={{
                background: 'rgba(255,255,255,0.08)',
                border: 'none',
                borderRadius: '4px',
                padding: '2px 6px',
                color: '#38bdf8',
                fontSize: '10.5px',
                cursor: 'pointer',
              }}
              title={nodeId}
            >
              #{i + 1}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
