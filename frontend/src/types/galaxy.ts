/**
 * Astral Cartographer — 3D Galaxy Graph TypeScript Contract
 * Mirrors backend Pydantic models in app.schemas.graph_schema
 */

export type NodeType = 'directory' | 'file' | 'function' | 'class'

export type EdgeRelation = 'imports' | 'calls' | 'contains' | 'inherits'

export interface NodeMetrics {
  loc: number
  centrality: number
  complexity: number
}

export interface PositionHint {
  cluster_id: number
  depth: number
}

export interface GraphNode {
  id: string
  label: string
  type: NodeType
  language: string | null
  path: string
  metrics: NodeMetrics
  position_hint: PositionHint
  ai_summary: string | null

  // Runtime 3D properties populated by galaxyLayout
  x?: number
  y?: number
  z?: number
  vx?: number
  vy?: number
  vz?: number
  size?: number
  color?: string
  glowColor?: string
  clusterColor?: string
  clusterName?: string
}

export interface GraphEdge {
  id: string
  source: string
  target: string
  relation: EdgeRelation
  weight: number
}

export interface Workflow {
  id: string
  name: string
  description: string
  ordered_node_ids: string[]
  edge_ids: string[]
}

export interface GraphMetadata {
  total_files: number
  total_functions: number
  total_classes: number
  languages: string[]
  analysis_duration_ms: number | null
  cluster_summaries: Record<number, string>
}

export interface AstralGraph {
  repo_url: string
  repo_name: string
  branch: string
  commit_sha: string | null
  generated_at: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  workflows: Workflow[]
  metadata: GraphMetadata
}

export interface QAResponse {
  answer: string
  highlighted_node_ids: string[]
}

export interface RepositoryItem {
  id: string
  url: string
  owner: string
  name: string
  branch: string
  created_at: string
  last_indexed_at: string | null
  status: string
}

export interface JobStatus {
  id: string
  repository_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  stage: string | null
  progress: number
  error: string | null
}

export interface ImpactAnalysisResult {
  target_node_id: string
  blast_radius_score: number
  affected_nodes_count: number
  affected_nodes: Array<{
    node_id: string
    depth: number
    relation: string
  }>
}
