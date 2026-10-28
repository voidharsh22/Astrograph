/**
 * Astral Cartographer — Graph Normalization Service
 * Converts backend GraphResponse, demo datasets, or custom repository payloads
 * into a canonical, normalized graph structure suitable for both 2D Cytoscape
 * and 3D Three.js rendering.
 *
 * GUARANTEES:
 * 1. File-to-file dependency edges are preserved directly.
 * 2. Directory clusters are derived dynamically from file paths as visual containers only.
 * 3. Clusters are NEVER treated as edge endpoints.
 * 4. Stable, unique node and edge IDs.
 * 5. Generic across any repository, directory structure, or language.
 */

// Distinct neon accent palette for visual directory clusters
const CLUSTER_PALETTES = [
  { name: 'pink', border: '#f43f5e', bg: 'rgba(244, 63, 94, 0.08)', text: '#fda4af' },
  { name: 'cyan', border: '#0ea5e9', bg: 'rgba(14, 165, 233, 0.08)', text: '#7dd3fc' },
  { name: 'amber', border: '#f59e0b', bg: 'rgba(245, 158, 11, 0.08)', text: '#fcd34d' },
  { name: 'emerald', border: '#10b981', bg: 'rgba(16, 185, 129, 0.08)', text: '#6ee7b7' },
  { name: 'purple', border: '#8b5cf6', bg: 'rgba(139, 92, 246, 0.08)', text: '#c4b5fd' },
  { name: 'teal', border: '#06b6d4', bg: 'rgba(6, 182, 212, 0.08)', text: '#67e8f9' },
  { name: 'violet', border: '#a855f7', bg: 'rgba(168, 85, 247, 0.08)', text: '#d8b4fe' },
  { name: 'orange', border: '#fb923c', bg: 'rgba(251, 146, 60, 0.08)', text: '#fdba74' },
];

/**
 * Deterministically pick a palette for a cluster directory name.
 */
export function getClusterPalette(clusterName, clusterIndex = 0) {
  const knownMapping = {
    src: CLUSTER_PALETTES[0],
    services: CLUSTER_PALETTES[1],
    solarfluxengine: CLUSTER_PALETTES[2],
    models: CLUSTER_PALETTES[3],
    api: CLUSTER_PALETTES[4],
    utils: CLUSTER_PALETTES[5],
  };

  const key = clusterName.toLowerCase().replace(/\/$/, '');
  if (knownMapping[key]) {
    return knownMapping[key];
  }

  // Hash-based color selection for arbitrary repo folder structures
  let hash = 0;
  for (let i = 0; i < clusterName.length; i++) {
    hash = (hash << 5) - hash + clusterName.charCodeAt(i);
    hash |= 0;
  }
  const idx = Math.abs(hash) % CLUSTER_PALETTES.length;
  return CLUSTER_PALETTES[idx] || CLUSTER_PALETTES[clusterIndex % CLUSTER_PALETTES.length];
}

/**
 * Extract parent folder path from a file path.
 * Examples:
 *   "src/main.py" -> "src"
 *   "src/api/routes.py" -> "src/api" (or top "src" if collapsed)
 *   "SolarFluxEngine/engine.py" -> "SolarFluxEngine"
 *   "README.md" -> "root"
 */
export function extractClusterPath(filePath) {
  if (!filePath || typeof filePath !== 'string') return 'root';
  const clean = filePath.replace(/^\/+/, '').replace(/\\/g, '/');
  const parts = clean.split('/');
  if (parts.length <= 1) {
    return 'root';
  }
  // Return direct parent folder name (e.g. "src" or "SolarFluxEngine")
  return parts[0];
}

/**
 * Normalizes raw repository graph data into canonical nodes, edges, and clusters.
 * Works seamlessly with both backend GraphResponse and mock demo data.
 */
export function normalizeGraphData(rawData) {
  if (!rawData || !Array.isArray(rawData.nodes)) {
    return {
      repo_name: 'unknown-repo',
      repo_url: '',
      branch: 'main',
      is_demo: false,
      nodes: [],
      edges: [],
      clusters: [],
      summary: { totalFiles: 0, totalDependencies: 0 },
      workflows: []
    };
  }

  const isDemo = rawData.is_demo !== undefined ? rawData.is_demo : (rawData.repo_name === 'cosmic-weather-api');

  // Filter out directory and repository root nodes (directories become compound visual containers)
  const nonDirRawNodes = rawData.nodes.filter((n) => n.type !== 'directory' && n.type !== 'repository');

  // If all nodes were directories (rare edge case), fallback to all
  const sourceNodes = nonDirRawNodes.length > 0 ? nonDirRawNodes : rawData.nodes;

  const nodeMap = new Map();
  const clusterFileMap = new Map();

  sourceNodes.forEach((raw, idx) => {
    // Determine path and clean label
    // Symbol nodes carry `file_path` (the file that defines them); files carry `path`.
    const rawPath = raw.metadata?.path || raw.metadata?.file_path || raw.path || raw.name || raw.label || `file_${idx}`;
    const cleanPath = rawPath.replace(/\\/g, '/');
    const pathParts = cleanPath.split('/');
    const defaultLabel = raw.name || pathParts[pathParts.length - 1] || raw.label || cleanPath;

    // Determine cluster
    const clusterPath = raw.position_hint?.cluster_name || extractClusterPath(cleanPath);

    // Canonical node ID
    const canonicalId = raw.id || `file::${cleanPath}`;

    // Extract metrics safely
    const metrics = {
      // Real values only; missing metrics stay null (never invented defaults).
      loc: raw.metrics?.loc ?? raw.metadata?.loc ?? null,
      centrality: raw.metrics?.centrality ?? raw.metadata?.centrality ?? null,
      complexity: raw.metrics?.complexity ?? raw.metadata?.complexity ?? null,
      cluster_id: raw.position_hint?.cluster_id ?? raw.metadata?.cluster_id ?? 0,
    };

    const node = {
      id: canonicalId,
      raw_id: raw.id,
      label: raw.label || defaultLabel,
      path: cleanPath,
      cluster: clusterPath,
      type: raw.type || 'file',
      language: String(raw.language || raw.metadata?.language || 'unknown').toLowerCase(),
      line: raw.metadata?.lineno ?? null,
      end_line: raw.metadata?.end_lineno ?? null,
      metrics,
      ai_summary: raw.ai_summary || raw.metadata?.ai_summary || null,
      position_hint: raw.position_hint || { cluster_id: metrics.cluster_id, depth: 1 },
      source_code: raw.source_code || null,
    };

    nodeMap.set(canonicalId, node);
    if (raw.id && raw.id !== canonicalId) {
      nodeMap.set(raw.id, node);
    }

    if (!clusterFileMap.has(clusterPath)) {
      clusterFileMap.set(clusterPath, []);
    }
    clusterFileMap.get(clusterPath).push(node);
  });

  // Build cluster containers with palettes and dynamic file counts
  const clusterList = [];
  let clusterIdx = 0;
  for (const [cPath, files] of clusterFileMap.entries()) {
    const palette = getClusterPalette(cPath, clusterIdx);
    clusterList.push({
      id: `cluster::${cPath}`,
      path: cPath,
      name: cPath === 'root' ? 'root/' : `${cPath}/`,
      fileCount: files.length,
      color: palette.border,
      bg: palette.bg,
      textColor: palette.text,
      nodeIds: files.map((f) => f.id),
      cluster_id: clusterIdx++,
    });
  }

  // Canonicalize edges (file-to-file only!)
  const normalizedEdges = [];
  const rawEdges = Array.isArray(rawData.edges) ? rawData.edges : [];

  rawEdges.forEach((rawEdge, edgeIdx) => {
    // Resolve source and target nodes
    let sourceNode = nodeMap.get(rawEdge.source);
    let targetNode = nodeMap.get(rawEdge.target);

    // If source or target was a raw ID or path
    if (!sourceNode) {
      sourceNode = Array.from(nodeMap.values()).find(
        (n) => n.path === rawEdge.source || n.raw_id === rawEdge.source
      );
    }
    if (!targetNode) {
      targetNode = Array.from(nodeMap.values()).find(
        (n) => n.path === rawEdge.target || n.raw_id === rawEdge.target
      );
    }

    // Discard edges if endpoints are invalid or if an endpoint is a directory container
    if (!sourceNode || !targetNode) return;
    if (sourceNode.id === targetNode.id) return; // ignore self-loops unless desired

    const relation = (rawEdge.relation || rawEdge.type || 'imports').toLowerCase();
    // Normalize relation types: 'imports', 'calls', 'defines', 'contains'
    let normRelation = 'imports';
    if (relation.includes('call')) normRelation = 'calls';
    else if (relation.includes('extend')) normRelation = 'extends';
    else if (relation.includes('implement')) normRelation = 'implements';
    else if (relation.includes('render')) normRelation = 'renders';
    else if (relation.includes('define')) normRelation = 'defines';
    else if (relation.includes('contain')) normRelation = 'contains';
    else if (relation.includes('import')) normRelation = 'imports';
    else normRelation = relation;
    const meta = rawEdge.metadata || {};

    const isCrossCluster = sourceNode.cluster !== targetNode.cluster;

    normalizedEdges.push({
      id: rawEdge.id || `edge-${edgeIdx}-${sourceNode.id}-${targetNode.id}`,
      source: sourceNode.id,
      target: targetNode.id,
      sourcePath: sourceNode.path,
      targetPath: targetNode.path,
      relation: normRelation,
      weight: rawEdge.weight ?? 1.0,
      is_cross_cluster: isCrossCluster,
      // Parser-provided facts, preserved for hover/inspector display.
      lines: meta.lines || (meta.line ? [meta.line] : []),
      module: meta.module ?? null,
      imported_name: meta.imported_name ?? meta.callee ?? null,
      resolution_status: meta.resolution_status || (rawEdge.metadata ? 'resolved' : 'unknown'),
      structural: normRelation === 'defines' || normRelation === 'contains',
    });
  });

  // Calculate distinct node list (deduplicated)
  const uniqueNodes = Array.from(new Set(Array.from(nodeMap.values())));

  return {
    repo_name: rawData.repo_name || (rawData.repository_id ? rawData.repository_id : (isDemo ? 'cosmic-weather-api' : 'analyzed-repository')),
    repo_url: rawData.repo_url || '',
    branch: rawData.branch || 'main',
    commit_sha: rawData.commit_sha || null,
    generated_at: rawData.generated_at || new Date().toISOString(),
    is_demo: isDemo,
    nodes: uniqueNodes,
    edges: normalizedEdges,
    clusters: clusterList,
    repository_id: rawData.repository_id || null,
    unresolved_references: Array.isArray(rawData.unresolved_references) ? rawData.unresolved_references : [],
    summary: {
      totalFiles: uniqueNodes.length,
      totalDependencies: normalizedEdges.length,
      totalClusters: clusterList.length,
    },
    workflows: rawData.workflows || [],
  };
}

