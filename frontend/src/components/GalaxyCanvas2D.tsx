/**
 * Astral Cartographer — 2D Knowledge Graph Canvas
 * Replicates the exact 2D module-cluster architecture graph from the Astrograph snapshot:
 * Directory container boxes, color-coded node pills, smooth bezier curve relationships, and zoom/pan.
 */

import React, { useMemo, useRef, useState } from 'react'
import { GraphEdge, GraphNode, NodeType, Workflow } from '../types/galaxy'

interface GalaxyCanvas2DProps {
  nodes: GraphNode[]
  edges: GraphEdge[]
  selectedNodeId: string | null
  activeWorkflow: Workflow | null
  activeTypeFilter: string
  onSelectNode: (node: GraphNode | null) => void
}

export const GalaxyCanvas2D: React.FC<GalaxyCanvas2DProps> = ({
  nodes,
  edges,
  selectedNodeId,
  activeWorkflow,
  activeTypeFilter,
  onSelectNode,
}) => {
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const [zoom, setZoom] = useState(0.85)
  const isDraggingRef = useRef(false)
  const lastMousePosRef = useRef({ x: 0, y: 0 })

  // Group nodes by directory or cluster to create module cards
  const { clusters, nodePosMap } = useMemo(() => {
    const clusterMap = new Map<string, GraphNode[]>()
    const posMap = new Map<string, { x: number; y: number }>()

    nodes.forEach((n) => {
      if (activeTypeFilter !== 'all' && n.type !== activeTypeFilter) return

      // Determine container directory
      let dirKey = 'root'
      if (n.path.includes('/')) {
        const parts = n.path.split('/')
        dirKey = parts[0] === 'backend' && parts.length > 2 ? parts[1] : parts[0]
      }
      if (!clusterMap.has(dirKey)) clusterMap.set(dirKey, [])
      clusterMap.get(dirKey)!.push(n)
    })

    const clusterKeys = Array.from(clusterMap.keys()).sort()
    const cols = Math.min(Math.max(Math.ceil(Math.sqrt(clusterKeys.length)), 2), 4)

    const clusterBoxes = clusterKeys.map((key, idx) => {
      const col = idx % cols
      const row = Math.floor(idx / cols)
      const boxX = col * 340 - (cols * 340) / 2 + 170
      const boxY = row * 260 - (Math.ceil(clusterKeys.length / cols) * 260) / 2 + 130
      const cNodes = clusterMap.get(key) || []

      // Position node pills in grid inside the cluster box
      cNodes.forEach((node, nodeIdx) => {
        const nCol = nodeIdx % 2
        const nRow = Math.floor(nodeIdx / 2)
        const nx = boxX - 110 + nCol * 130
        const ny = boxY - 70 + nRow * 42
        posMap.set(node.id, { x: nx, y: ny })
      })

      return {
        key,
        x: boxX,
        y: boxY,
        width: 300,
        height: Math.max(160, Math.ceil(cNodes.length / 2) * 44 + 50),
        nodes: cNodes,
      }
    })

    return { clusters: clusterBoxes, nodePosMap: posMap }
  }, [nodes, activeTypeFilter])

  // Mouse pan handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button === 0) {
      isDraggingRef.current = true
      lastMousePosRef.current = { x: e.clientX, y: e.clientY }
    }
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDraggingRef.current) {
      const dx = e.clientX - lastMousePosRef.current.x
      const dy = e.clientY - lastMousePosRef.current.y
      lastMousePosRef.current = { x: e.clientX, y: e.clientY }
      setPan((prev) => ({ x: prev.x + dx, y: prev.y + dy }))
    }
  }

  const handleMouseUp = () => {
    isDraggingRef.current = false
  }

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault()
    const newZoom = Math.max(0.3, Math.min(2.5, zoom - e.deltaY * 0.001))
    setZoom(newZoom)
  }

  const edgeColors: Record<string, string> = {
    calls: '#a855f7',
    imports: '#38bdf8',
    contains: '#f59e0b',
    inherits: '#10b981',
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        position: 'relative',
        overflow: 'hidden',
        background: '#070a13',
        cursor: isDraggingRef.current ? 'grabbing' : 'grab',
        userSelect: 'none',
      }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onWheel={handleWheel}
    >
      {/* Zoom / Pan Controls Overlay */}
      <div
        style={{
          position: 'absolute',
          bottom: '24px',
          left: '24px',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
          zIndex: 20,
        }}
      >
        <button
          onClick={() => setZoom((z) => Math.min(2.5, z + 0.15))}
          style={controlBtnStyle}
          title="Zoom In"
        >
          +
        </button>
        <button
          onClick={() => setZoom((z) => Math.max(0.3, z - 0.15))}
          style={controlBtnStyle}
          title="Zoom Out"
        >
          -
        </button>
        <button
          onClick={() => {
            setZoom(0.85)
            setPan({ x: 0, y: 0 })
          }}
          style={controlBtnStyle}
          title="Fit to Screen"
        >
          ⛶
        </button>
      </div>

      <svg
        style={{
          width: '100%',
          height: '100%',
          overflow: 'visible',
        }}
      >
        <g
          transform={`translate(${window.innerWidth / 2 + pan.x}, ${
            window.innerHeight / 2 + pan.y
          }) scale(${zoom})`}
        >
          {/* Cluster Module Background Containers */}
          {clusters.map((cluster) => (
            <g key={cluster.key} transform={`translate(${cluster.x - cluster.width / 2}, ${cluster.y - cluster.height / 2})`}>
              <rect
                width={cluster.width}
                height={cluster.height}
                rx={12}
                fill="rgba(15, 23, 42, 0.65)"
                stroke="rgba(255, 255, 255, 0.08)"
                strokeWidth={1}
                filter="drop-shadow(0 8px 24px rgba(0,0,0,0.5))"
              />
              <path
                d="M 16 0 L 120 0 L 130 18 L 16 18 Z"
                fill="rgba(245, 158, 11, 0.12)"
              />
              <text
                x={18}
                y={13}
                fill="#f59e0b"
                fontSize={11}
                fontWeight={700}
                fontFamily="Outfit, sans-serif"
                letterSpacing={0.5}
              >
                📁 {cluster.key}
              </text>
            </g>
          ))}

          {/* Directed Bezier Dependency Edges */}
          {edges.map((edge, idx) => {
            const p1 = nodePosMap.get(edge.source)
            const p2 = nodePosMap.get(edge.target)
            if (!p1 || !p2) return null

            const isWorkflowEdge = activeWorkflow?.edge_ids.includes(edge.id)
            const color = isWorkflowEdge ? '#ffedd5' : edgeColors[edge.relation] || '#38bdf8'
            const strokeWidth = isWorkflowEdge ? 2.5 : 1.2
            const opacity = isWorkflowEdge ? 0.9 : 0.28

            // Smooth cubic bezier curve
            const dx = p2.x - p1.x
            const dy = p2.y - p1.y
            const cx1 = p1.x + dx * 0.4
            const cy1 = p1.y + dy * 0.1
            const cx2 = p1.x + dx * 0.6
            const cy2 = p2.y - dy * 0.1

            return (
              <path
                key={edge.id || idx}
                d={`M ${p1.x} ${p1.y} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${p2.x} ${p2.y}`}
                fill="none"
                stroke={color}
                strokeWidth={strokeWidth}
                strokeOpacity={opacity}
              />
            )
          })}

          {/* Node Pills matching Astrograph design */}
          {nodes.map((node) => {
            const pos = nodePosMap.get(node.id)
            if (!pos) return null

            const isSelected = selectedNodeId === node.id
            const typeColor = node.color || '#38bdf8'

            return (
              <g
                key={node.id}
                transform={`translate(${pos.x}, ${pos.y})`}
                onClick={(e) => {
                  e.stopPropagation()
                  onSelectNode(node)
                }}
                style={{ cursor: 'pointer' }}
              >
                {/* Node Pill Shape */}
                <rect
                  x={-52}
                  y={-14}
                  width={104}
                  height={28}
                  rx={6}
                  fill={isSelected ? 'rgba(30, 41, 59, 0.95)' : 'rgba(15, 23, 42, 0.85)'}
                  stroke={isSelected ? '#ffffff' : typeColor}
                  strokeWidth={isSelected ? 2 : 1}
                  filter={isSelected ? `drop-shadow(0 0 10px ${typeColor})` : undefined}
                />
                {/* Node Type Indicator Dot */}
                <circle cx={-40} cy={0} r={4} fill={typeColor} />
                {/* Node Label */}
                <text
                  x={-30}
                  y={3.5}
                  fill="#f8fafc"
                  fontSize={10.5}
                  fontWeight={500}
                  fontFamily="Outfit, sans-serif"
                >
                  {node.label.length > 11 ? node.label.substring(0, 10) + '…' : node.label}
                </text>
              </g>
            )
          })}
        </g>
      </svg>
    </div>
  )
}

const controlBtnStyle: React.CSSProperties = {
  width: '32px',
  height: '32px',
  borderRadius: '8px',
  background: 'rgba(15, 23, 42, 0.85)',
  border: '1px solid rgba(255, 255, 255, 0.1)',
  color: '#fff',
  fontSize: '16px',
  fontWeight: 'bold',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  cursor: 'pointer',
  backdropFilter: 'blur(8px)',
  transition: 'all 0.15s ease',
}
