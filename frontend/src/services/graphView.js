/**
 * Pure graph-view helpers shared by the 2D and 3D canvases.
 *
 * Input is the normalized graph (graphNormalizer.js). Edges are parser-generated; directory
 * clusters are visual containers only and are never edge endpoints. Nothing here invents
 * relationships: it only filters, traverses and highlights existing edges.
 */

export const DEPENDENCY_RELATIONS = ['imports', 'calls'];
export const STRUCTURAL_RELATIONS = ['defines', 'contains'];

export const DEFAULT_FILTERS = {
  relations: { imports: true, calls: true, structural: false },
  language: 'all',
  directory: 'all',
  nodeKinds: 'files', // 'files' | 'all'
  unresolvedOnly: false,
};

export function buildAdjacency(edges) {
  const out = new Map();
  const inc = new Map();
  for (const e of edges) {
    if (!out.has(e.source)) out.set(e.source, []);
    if (!inc.has(e.target)) inc.set(e.target, []);
    out.get(e.source).push(e);
    inc.get(e.target).push(e);
  }
  return { out, inc };
}

/** Files that have at least one unresolved internal import (status 'unresolved'). */
export function unresolvedFileIds(graph) {
  const byPath = new Map(graph.nodes.filter((n) => n.type === 'file').map((n) => [n.path, n.id]));
  const ids = new Set();
  for (const u of graph.unresolved_references || []) {
    if (u.kind === 'import' && u.status === 'unresolved' && byPath.has(u.source_file)) ids.add(byPath.get(u.source_file));
  }
  return ids;
}

export function edgeAllowed(edge, filters) {
  const r = filters.relations;
  if (edge.structural) return Boolean(r.structural);
  return Boolean(r[edge.relation]);
}

/** Apply type/language/directory/relationship filters. Returns a new graph object (same shape). */
export function applyFilters(graph, filters = DEFAULT_FILTERS) {
  if (!graph) return graph;
  const unresolved = filters.unresolvedOnly ? unresolvedFileIds(graph) : null;
  const nodes = graph.nodes.filter((n) => {
    if (filters.nodeKinds === 'files' && n.type !== 'file') return false;
    if (filters.language !== 'all' && n.language !== filters.language) return false;
    if (filters.directory !== 'all' && n.cluster !== filters.directory) return false;
    if (unresolved && !unresolved.has(n.id)) return false;
    return true;
  });
  const ids = new Set(nodes.map((n) => n.id));
  const edges = graph.edges.filter((e) => ids.has(e.source) && ids.has(e.target) && edgeAllowed(e, filters));
  return { ...graph, nodes, edges };
}

/** Breadth-first trace. direction: 'downstream' (what X depends on) or 'upstream' (what depends on X). */
export function trace(graph, startId, direction, maxDepth = 6) {
  const { out, inc } = buildAdjacency(graph.edges.filter((e) => !e.structural));
  const next = direction === 'upstream' ? inc : out;
  const depth = new Map([[startId, 0]]);
  const edgeIds = new Set();
  let frontier = [startId];
  while (frontier.length) {
    const upcoming = [];
    for (const id of frontier) {
      const d = depth.get(id);
      if (d >= maxDepth) continue;
      for (const e of next.get(id) || []) {
        edgeIds.add(e.id);
        const other = direction === 'upstream' ? e.source : e.target;
        if (!depth.has(other)) {
          depth.set(other, d + 1);
          upcoming.push(other);
        }
      }
    }
    frontier = upcoming;
  }
  return { nodeIds: [...depth.keys()], edgeIds: [...edgeIds], depth };
}

/** Immediate (1-hop) neighborhood, both directions, dependency edges only. */
export function isolate(graph, nodeId) {
  const ids = new Set([nodeId]);
  const edgeIds = new Set();
  for (const e of graph.edges) {
    if (e.structural) continue;
    if (e.source === nodeId || e.target === nodeId) {
      ids.add(e.source);
      ids.add(e.target);
      edgeIds.add(e.id);
    }
  }
  return { nodeIds: [...ids], edgeIds: [...edgeIds] };
}

/** Shortest directed dependency path from -> to (BFS). Returns null when none exists. */
export function findPath(graph, fromId, toId) {
  if (fromId === toId) return { nodeIds: [fromId], edgeIds: [] };
  const { out } = buildAdjacency(graph.edges.filter((e) => !e.structural));
  const prev = new Map([[fromId, null]]);
  const queue = [fromId];
  while (queue.length) {
    const cur = queue.shift();
    for (const e of out.get(cur) || []) {
      if (prev.has(e.target)) continue;
      prev.set(e.target, { id: cur, edge: e.id });
      if (e.target === toId) {
        const nodeIds = [toId];
        const edgeIds = [];
        let step = prev.get(toId);
        while (step) {
          nodeIds.unshift(step.id);
          edgeIds.unshift(step.edge);
          step = prev.get(step.id);
        }
        return { nodeIds, edgeIds };
      }
      queue.push(e.target);
    }
  }
  return null;
}

/** Relationship encoding shared by the legend and both canvases (color + dash + label). */
export const RELATION_STYLES = {
  imports: { label: 'Imports', color: '#f97316', hex: 0xf97316, dash: 'solid', description: 'File imports another file (arrow points to the imported file)' },
  calls: { label: 'Calls', color: '#38bdf8', hex: 0x38bdf8, dash: 'dashed', description: 'Function/method calls a resolved definition in another file' },
  defines: { label: 'Defines', color: '#a855f7', hex: 0xa855f7, dash: 'dotted', description: 'File defines a symbol (structural, hidden by default)' },
  contains: { label: 'Contains', color: '#10b981', hex: 0x10b981, dash: 'dotted', description: 'Structural containment (hidden by default)' },
};

export function directoriesOf(graph) {
  return [...new Set((graph?.nodes || []).map((n) => n.cluster).filter(Boolean))].sort();
}

export function languagesOf(graph) {
  return [...new Set((graph?.nodes || []).map((n) => n.language).filter((l) => l && l !== 'unknown'))].sort();
}
