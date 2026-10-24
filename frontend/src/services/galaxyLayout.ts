/**
 * Astral Cartographer — Celestial Layout Engine
 * Calculates deterministic 3D celestial coordinates (x, y, z) and 2D cluster coordinates (x, y)
 * for galaxies, solar systems, stars (files), planets (classes), and moons (functions).
 */

import { AstralGraph, GraphNode, NodeType } from '../types/galaxy'

export interface CelestialClusterInfo {
  id: number
  name: string
  color: string
  nodeCount: number
  center: { x: number; y: number; z: number }
  summary?: string
}

// Exact taxonomy colors from Astrograph snapshots
export const NODE_TYPE_COLORS: Record<NodeType, string> = {
  directory: '#f59e0b', // Amber
  file: '#38bdf8',      // Blue / Cyan
  class: '#10b981',     // Emerald Green
  function: '#a855f7',  // Purple / Violet
}

export const CLUSTER_PALETTES = [
  { name: 'Core Architecture', color: '#f97316' }, // Amber / Solar
  { name: 'API & Routing', color: '#38bdf8' },     // Cyan
  { name: 'Services & Logic', color: '#a855f7' },  // Purple
  { name: 'Data Models', color: '#10b981' },       // Emerald
  { name: 'Integrations & Web', color: '#ec4899' },// Rose
  { name: 'Utilities & Helpers', color: '#eab308' },// Yellow
  { name: 'Configuration', color: '#6366f1' },     // Indigo
]

/**
 * Enriches graph nodes with 3D celestial coordinates (x, y, z) and 2D layout coordinates (x2d, y2d)
 */
export function computeGalaxyLayout(graph: AstralGraph): {
  nodes: GraphNode[]
  clusters: CelestialClusterInfo[]
} {
  const nodes = graph.nodes.map((n) => ({ ...n }))
  const clusterMap = new Map<number, GraphNode[]>()

  // Group nodes by Louvain cluster_id
  nodes.forEach((node) => {
    const cid = node.position_hint?.cluster_id ?? 0
    if (!clusterMap.has(cid)) {
      clusterMap.set(cid, [])
    }
    clusterMap.get(cid)!.push(node)
  })

  const clusterIds = Array.from(clusterMap.keys()).sort((a, b) => a - b)
  const totalClusters = Math.max(clusterIds.length, 1)

  const clusters: CelestialClusterInfo[] = []

  // Step 1: Compute 3D and 2D centers for each cluster
  const clusterCenters = new Map<number, { x: number; y: number; z: number; x2d: number; y2d: number }>()

  clusterIds.forEach((cid, index) => {
    const angle = (index / totalClusters) * Math.PI * 2
    const orbitRadius = totalClusters === 1 ? 0 : 120 + (index % 2) * 45
    const cx = Math.cos(angle) * orbitRadius
    const cy = Math.sin(angle * 2) * 20
    const cz = Math.sin(angle) * orbitRadius

    // 2D grid coordinates (for the 2D Graph view in Screen 3)
    const cols = Math.ceil(Math.sqrt(totalClusters))
    const col = index % cols
    const row = Math.floor(index / cols)
    const cx2d = (col - (cols - 1) / 2) * 360
    const cy2d = (row - (Math.ceil(totalClusters / cols) - 1) / 2) * 280

    clusterCenters.set(cid, { x: cx, y: cy, z: cz, x2d: cx2d, y2d: cy2d })

    const palette = CLUSTER_PALETTES[cid % CLUSTER_PALETTES.length]
    const customSummary = graph.metadata.cluster_summaries?.[cid]

    clusters.push({
      id: cid,
      name: customSummary ? customSummary.split('.')[0] : `Constellation ${cid + 1}: ${palette.name}`,
      color: palette.color,
      nodeCount: clusterMap.get(cid)!.length,
      center: { x: cx, y: cy, z: cz },
      summary: customSummary,
    })
  })

  // Step 2: Position individual nodes within each cluster
  clusterMap.forEach((clusterNodes, cid) => {
    const center = clusterCenters.get(cid)!
    const palette = CLUSTER_PALETTES[cid % CLUSTER_PALETTES.length]

    // Sort nodes: directories first, then files, then classes, then functions
    const order: Record<NodeType, number> = { directory: 0, file: 1, class: 2, function: 3 }
    clusterNodes.sort((a, b) => order[a.type] - order[b.type])

    // Find directory or high-centrality anchors
    const anchorMap = new Map<string, { x: number; y: number; z: number }>()

    clusterNodes.forEach((node, idx) => {
      const typeColor = NODE_TYPE_COLORS[node.type] || '#38bdf8'
      node.color = typeColor
      node.clusterColor = palette.color
      node.clusterName = palette.name

      // Determine visual size based on type and PageRank centrality
      const pr = node.metrics?.centrality ?? 0.05
      if (node.type === 'directory') {
        node.size = 5.5 + pr * 3.5
      } else if (node.type === 'file') {
        node.size = 3.2 + pr * 3.0
      } else if (node.type === 'class') {
        node.size = 2.4 + pr * 2.0
      } else {
        node.size = 1.6 + pr * 1.5
      }

      // Compute 3D position
      if (node.type === 'directory') {
        // Directory is anchor of its solar system
        const dirOffsetRadius = 25 * Math.sqrt(idx + 1)
        const dirAngle = idx * 2.39996 // Golden angle
        const nx = center.x + Math.cos(dirAngle) * dirOffsetRadius
        const ny = center.y + ((idx % 3) - 1) * 12
        const nz = center.z + Math.sin(dirAngle) * dirOffsetRadius
        node.x = nx
        node.y = ny
        node.z = nz
        anchorMap.set(node.path, { x: nx, y: ny, z: nz })
      } else if (node.type === 'file') {
        // File orbits near its parent directory or cluster center
        const parentDir = node.path.includes('/') ? node.path.substring(0, node.path.lastIndexOf('/')) : ''
        const anchor = anchorMap.get(parentDir) || center
        const fileAngle = idx * 1.61803
        const fileRadius = 15 + (idx % 5) * 5.5
        const nx = anchor.x + Math.cos(fileAngle) * fileRadius
        const ny = anchor.y + Math.sin(idx * 0.7) * 8
        const nz = anchor.z + Math.sin(fileAngle) * fileRadius
        node.x = nx
        node.y = ny
        node.z = nz
        anchorMap.set(node.path, { x: nx, y: ny, z: nz })
      } else {
        // Function / Class orbits its file anchor like moons
        const parentFile = node.path
        const anchor = anchorMap.get(parentFile) || center
        const subAngle = idx * 2.4
        const subRadius = 6.5 + (idx % 3) * 3
        node.x = anchor.x + Math.cos(subAngle) * subRadius
        node.y = anchor.y + Math.sin(subAngle) * 3.5
        node.z = anchor.z + Math.sin(subAngle) * subRadius
      }
    })
  })

  return { nodes, clusters }
}
