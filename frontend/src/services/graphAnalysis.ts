/**
 * Astral AI — pure graph analysis helpers.
 *
 * Works on the *normalized* workspace graph (see services/graphNormalizer.js):
 * file-level nodes with `metrics.centrality` (PageRank), `cluster` (Louvain /
 * directory community), and directed `imports | calls | defines | contains` edges.
 * Used by the Graph-RAG context builder, the 3D bridge, and the offline simulation.
 */

export interface GNode {
  id: string
  label: string
  type?: string
  path?: string
  cluster?: string
  language?: string | null
  ai_summary?: string | null
  metrics?: { loc?: number; centrality?: number; complexity?: number; cluster_id?: number }
  position_hint?: { cluster_id?: number; depth?: number }
}

export interface GEdge {
  id?: string
  source: string
  target: string
  relation?: string
  weight?: number
}

export interface GCluster {
  id?: string
  path: string
  name?: string
  fileCount?: number
  nodeIds?: string[]
  cluster_id?: number
}

export interface GWorkflow {
  id?: string
  name?: string
  description?: string
  nodes?: Array<string | { id?: string }>
  ordered_node_ids?: string[]
  node_ids?: string[]
}

export interface CopilotGraph {
  repo_name?: string
  repo_url?: string
  branch?: string
  is_demo?: boolean
  nodes: GNode[]
  edges: GEdge[]
  clusters?: GCluster[]
  workflows?: GWorkflow[]
}

interface GraphIndex {
  byId: Map<string, GNode>
  out: Map<string, GEdge[]>
  inn: Map<string, GEdge[]>
  byLabel: Map<string, GNode[]>
}

const indexCache = new WeakMap<CopilotGraph, GraphIndex>()

export function getIndex(graph: CopilotGraph): GraphIndex {
  const cached = indexCache.get(graph)
  if (cached) return cached

  const byId = new Map<string, GNode>()
  const byLabel = new Map<string, GNode[]>()
  for (const n of graph.nodes) {
    byId.set(n.id, n)
    const key = n.label.toLowerCase()
    const list = byLabel.get(key)
    if (list) list.push(n)
    else byLabel.set(key, [n])
  }

  const out = new Map<string, GEdge[]>()
  const inn = new Map<string, GEdge[]>()
  for (const e of graph.edges) {
    if (!byId.has(e.source) || !byId.has(e.target) || e.source === e.target) continue
    const o = out.get(e.source)
    if (o) o.push(e)
    else out.set(e.source, [e])
    const i = inn.get(e.target)
    if (i) i.push(e)
    else inn.set(e.target, [e])
  }

  const idx = { byId, out, inn, byLabel }
  indexCache.set(graph, idx)
  return idx
}

export const pagerank = (n: GNode): number => n.metrics?.centrality ?? 0

export function clusterKeyOf(n: GNode): string {
  if (n.cluster) return n.cluster
  const parts = (n.path || '').split('/')
  return parts.length <= 1 ? 'root' : parts[0]
}

export function inDegree(graph: CopilotGraph, id: string): number {
  return getIndex(graph).inn.get(id)?.length ?? 0
}

export function outDegree(graph: CopilotGraph, id: string): number {
  return getIndex(graph).out.get(id)?.length ?? 0
}

export function topByPageRank(graph: CopilotGraph, n: number): GNode[] {
  return [...graph.nodes].sort((a, b) => pagerank(b) - pagerank(a)).slice(0, n)
}

/** Resolve a loose reference (id, path, label, `[[label]]`, `@label`) to a graph node. */
export function resolveNodeRef(graph: CopilotGraph, ref: string | null | undefined): GNode | null {
  if (!ref) return null
  const raw = ref.trim().replace(/^\[\[/, '').replace(/\]\]$/, '').replace(/^@/, '').trim()
  if (!raw) return null
  const idx = getIndex(graph)

  const exact = idx.byId.get(raw)
  if (exact) return exact

  const lower = raw.toLowerCase().replace(/\\/g, '/')
  const cleaned = lower.replace(/\(\)$/, '')
  const best = (list: GNode[]) => list.reduce((a, b) => (pagerank(b) > pagerank(a) ? b : a))

  const byPrefixedId = idx.byId.get(`file::${raw}`)
  if (byPrefixedId) return byPrefixedId

  const pathExact = graph.nodes.filter((n) => n.path?.toLowerCase() === cleaned)
  if (pathExact.length) return best(pathExact)

  const labelExact = idx.byLabel.get(cleaned) || idx.byLabel.get(lower)
  if (labelExact?.length) return best(labelExact)

  const suffix = graph.nodes.filter((n) => n.path && n.path.toLowerCase().endsWith(`/${cleaned}`))
  if (suffix.length) return best(suffix)

  const stem = graph.nodes.filter((n) => n.label.toLowerCase().replace(/\.[a-z0-9]+$/, '') === cleaned.replace(/\.[a-z0-9]+$/, ''))
  if (stem.length) return best(stem)

  const loose = graph.nodes.filter(
    (n) => n.label.toLowerCase().includes(cleaned) || (n.path || '').toLowerCase().includes(cleaned),
  )
  if (loose.length) return best(loose)

  return null
}

/** `[[Node]]` mention tokens, de-duplicated, in order of appearance. */
export function extractMentions(text: string): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  const re = /\[\[([^\[\]\n]+?)\]\]/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    const key = m[1].trim()
    if (key && !seen.has(key)) {
      seen.add(key)
      out.push(key)
    }
  }
  return out
}

/** Label if it is unique in the graph, otherwise the repo-relative path. */
export function mentionToken(graph: CopilotGraph, n: GNode): string {
  const same = getIndex(graph).byLabel.get(n.label.toLowerCase())
  return same && same.length > 1 && n.path ? n.path : n.label
}

export interface BlastResult {
  affected: Array<{ id: string; depth: number }>
  maxDepth: number
}

/** Reverse BFS: everything that (transitively) depends on `sourceId`, up to `depth` hops. */
export function computeBlastRadius(graph: CopilotGraph, sourceId: string, depth = 3): BlastResult {
  const idx = getIndex(graph)
  const seen = new Map<string, number>([[sourceId, 0]])
  let frontier = [sourceId]
  const limit = Math.max(1, Math.min(8, Math.floor(depth) || 3))
  for (let d = 1; d <= limit && frontier.length; d++) {
    const next: string[] = []
    for (const id of frontier) {
      for (const e of idx.inn.get(id) ?? []) {
        if (!seen.has(e.source)) {
          seen.set(e.source, d)
          next.push(e.source)
        }
      }
    }
    frontier = next
  }
  const affected = [...seen.entries()]
    .filter(([id]) => id !== sourceId)
    .map(([id, d]) => ({ id, depth: d }))
    .sort((a, b) => a.depth - b.depth)
  return { affected, maxDepth: affected.length ? affected[affected.length - 1].depth : 0 }
}

/** Tarjan SCC (iterative). Returns strongly connected groups with more than one node, largest first. */
export function findStronglyConnected(graph: CopilotGraph): string[][] {
  const idx = getIndex(graph)
  let counter = 0
  const index = new Map<string, number>()
  const low = new Map<string, number>()
  const onStack = new Set<string>()
  const stack: string[] = []
  const result: string[][] = []

  for (const start of idx.byId.keys()) {
    if (index.has(start)) continue
    const work: Array<{ v: string; i: number }> = [{ v: start, i: 0 }]
    index.set(start, counter)
    low.set(start, counter)
    counter++
    stack.push(start)
    onStack.add(start)

    while (work.length) {
      const frame = work[work.length - 1]
      const outs = idx.out.get(frame.v) ?? []
      if (frame.i < outs.length) {
        const w = outs[frame.i++].target
        if (!index.has(w)) {
          index.set(w, counter)
          low.set(w, counter)
          counter++
          stack.push(w)
          onStack.add(w)
          work.push({ v: w, i: 0 })
        } else if (onStack.has(w)) {
          low.set(frame.v, Math.min(low.get(frame.v)!, index.get(w)!))
        }
      } else {
        if (low.get(frame.v) === index.get(frame.v)) {
          const comp: string[] = []
          let w: string
          do {
            w = stack.pop()!
            onStack.delete(w)
            comp.push(w)
          } while (w !== frame.v)
          if (comp.length > 1) result.push(comp)
        }
        work.pop()
        if (work.length) {
          const parent = work[work.length - 1].v
          low.set(parent, Math.min(low.get(parent)!, low.get(frame.v)!))
        }
      }
    }
  }
  return result.sort((a, b) => b.length - a.length)
}

/** One concrete simple cycle inside a strongly connected group, returned closed (first id repeated at the end). */
export function cyclePathWithin(graph: CopilotGraph, group: string[]): string[] {
  const idx = getIndex(graph)
  const members = new Set(group)
  const start = group[0]
  const path: string[] = [start]
  const visited = new Set<string>([start])

  const dfs = (v: string): boolean => {
    for (const e of idx.out.get(v) ?? []) {
      if (!members.has(e.target)) continue
      if (e.target === start && path.length > 1) return true
      if (visited.has(e.target)) continue
      visited.add(e.target)
      path.push(e.target)
      if (dfs(e.target)) return true
      path.pop()
    }
    return false
  }

  return dfs(start) ? [...path, start] : group.slice(0, Math.min(group.length, 4))
}

/** Greedy highest-PageRank walk along outgoing edges from an entry node. */
export function traceFlow(graph: CopilotGraph, entryId: string, maxLen = 7): string[] {
  const idx = getIndex(graph)
  const path = [entryId]
  const seen = new Set(path)
  let cur = entryId
  while (path.length < maxLen) {
    const candidates = (idx.out.get(cur) ?? [])
      .map((e) => idx.byId.get(e.target)!)
      .filter((n) => n && !seen.has(n.id))
    if (!candidates.length) break
    const next = candidates.reduce((a, b) => (pagerank(b) > pagerank(a) ? b : a))
    path.push(next.id)
    seen.add(next.id)
    cur = next.id
  }
  return path
}

/** Guess the request entry point: app/main/server/router files, weighted by PageRank. */
export function guessEntryNode(graph: CopilotGraph): GNode | null {
  const entryRe = /(^|\/)(main|app|server|index|router|routes|api|gateway|auth|manage|wsgi|asgi)\b/i
  const entries = graph.nodes.filter((n) => entryRe.test(n.path || n.label))
  const pool = entries.length ? entries : graph.nodes
  if (!pool.length) return null
  // Prefer entries that mostly *call out* (high out-degree, few dependents).
  return pool.reduce((a, b) => {
    const score = (n: GNode) => pagerank(n) + outDegree(graph, n.id) * 0.05 - inDegree(graph, n.id) * 0.03
    return score(b) > score(a) ? b : a
  })
}

export interface ClusterSummary {
  key: string
  label: string
  files: number
  loc: number
  avgComplexity: number
  avgPageRank: number
  topNodes: string[]
  nodeIds: string[]
}

export function summarizeClusters(graph: CopilotGraph): ClusterSummary[] {
  const groups = new Map<string, GNode[]>()
  for (const n of graph.nodes) {
    const key = clusterKeyOf(n)
    const list = groups.get(key)
    if (list) list.push(n)
    else groups.set(key, [n])
  }
  return [...groups.entries()]
    .map(([key, nodes]) => {
      const loc = nodes.reduce((s, n) => s + (n.metrics?.loc ?? 0), 0)
      const cx = nodes.reduce((s, n) => s + (n.metrics?.complexity ?? 0), 0) / nodes.length
      const pr = nodes.reduce((s, n) => s + pagerank(n), 0) / nodes.length
      return {
        key,
        label: key === 'root' ? 'root/' : `${key}/`,
        files: nodes.length,
        loc,
        avgComplexity: Math.round(cx * 10) / 10,
        avgPageRank: Math.round(pr * 1000) / 1000,
        topNodes: [...nodes].sort((a, b) => pagerank(b) - pagerank(a)).slice(0, 3).map((n) => n.label),
        nodeIds: nodes.map((n) => n.id),
      }
    })
    .sort((a, b) => b.files - a.files)
}

/** Match a cluster by directory key, display name, Louvain/cluster index, or `cluster::key` id. */
export function resolveCluster(
  graph: CopilotGraph,
  clusterId: string | number,
  label?: string,
): ClusterSummary | null {
  const summaries = summarizeClusters(graph)
  const wanted = String(clusterId).trim().toLowerCase().replace(/^cluster::/, '').replace(/\/$/, '')
  const wantedLabel = (label || '').trim().toLowerCase().replace(/\/$/, '')

  const byKey = summaries.find((s) => s.key.toLowerCase() === wanted)
  if (byKey) return byKey

  const numeric = Number(wanted)
  if (wanted !== '' && Number.isInteger(numeric)) {
    const meta = graph.clusters?.find((c) => c.cluster_id === numeric)
    if (meta) {
      const m = summaries.find((s) => s.key === meta.path)
      if (m) return m
    }
    const ids = graph.nodes.filter((n) => (n.position_hint?.cluster_id ?? n.metrics?.cluster_id) === numeric)
    if (ids.length) {
      return {
        key: String(numeric),
        label: label || `Cluster ${numeric}`,
        files: ids.length,
        loc: ids.reduce((s, n) => s + (n.metrics?.loc ?? 0), 0),
        avgComplexity: 0,
        avgPageRank: 0,
        topNodes: ids.slice(0, 3).map((n) => n.label),
        nodeIds: ids.map((n) => n.id),
      }
    }
  }

  return (
    summaries.find((s) => wantedLabel && s.key.toLowerCase() === wantedLabel) ||
    summaries.find((s) => wantedLabel && s.key.toLowerCase().includes(wantedLabel)) ||
    summaries.find((s) => s.key.toLowerCase().includes(wanted)) ||
    null
  )
}

/** Ordered node ids for a backend-provided workflow (several payload shapes exist). */
export function workflowNodeIds(graph: CopilotGraph, wf: GWorkflow): string[] {
  const raw = wf.ordered_node_ids || wf.node_ids || wf.nodes || []
  const ids: string[] = []
  for (const item of raw) {
    const ref = typeof item === 'string' ? item : item?.id
    const node = resolveNodeRef(graph, ref)
    if (node) ids.push(node.id)
  }
  return ids
}
