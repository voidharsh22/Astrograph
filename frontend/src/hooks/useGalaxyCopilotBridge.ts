/**
 * useGalaxyCopilotBridge — connects Astral AI tool calls to the 3D Galaxy canvas.
 *
 * The hook owns the "overlay" state (execution workflow, blast radius, cluster spotlight,
 * camera zoom/focus pulses) that <GalaxyGraph3D copilotFx={fx} /> renders, and exposes
 * `executeTool` which the assistant calls for every Claude `tool_use` block. Selecting a node
 * goes through the Workspace's normal `onSelectNode`, so the camera flight and the Node
 * Inspector open exactly as if the user had clicked the star.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  BlastRadiusInput,
  FilterClusterInput,
  FocusCameraInput,
  HighlightWorkflowInput,
  ToolCall,
  ToolOutcome,
} from '../services/astralAiService'
import {
  CopilotGraph,
  GNode,
  clusterKeyOf,
  computeBlastRadius,
  getIndex,
  inDegree,
  outDegree,
  resolveCluster,
  resolveNodeRef,
} from '../services/graphAnalysis'

export interface WorkflowFx {
  name: string
  nodeIds: string[]
  token: number
}
export interface BlastFx {
  sourceId: string
  affected: Array<{ id: string; depth: number }>
  depth: number
  token: number
}
export interface ClusterFx {
  key: string
  label: string
  nodeIds: string[]
  token: number
}

/** Consumed by GalaxyGraph3D. Only one of workflow / blast / cluster is active at a time. */
export interface CopilotFx {
  workflow: WorkflowFx | null
  blast: BlastFx | null
  cluster: ClusterFx | null
  /** Camera zoom multiplier for the next node flight (1 = default). */
  zoom: number
  /** Bumped to force a camera flight to `focusNodeId` even if it is already selected. */
  focusToken: number
  focusNodeId: string | null
}

export const EMPTY_FX: CopilotFx = {
  workflow: null,
  blast: null,
  cluster: null,
  zoom: 1,
  focusToken: 0,
  focusNodeId: null,
}

export interface GalaxyCopilotBridge {
  fx: CopilotFx
  hasOverlay: boolean
  overlayLabel: string | null
  autoPilot: boolean
  setAutoPilot: (on: boolean) => void
  /** Run a Claude tool call. When auto-pilot is off the facts are returned but the scene is not touched. */
  executeTool: (call: ToolCall, opts?: { force?: boolean }) => ToolOutcome
  /** Fly the camera to a node (id, path or label) and open its inspector. Always works. */
  focusNode: (ref: string, zoom?: number) => boolean
  clearOverlay: () => void
  /** Show server-computed overlays (no client-side recomputation). */
  showImpact: (sourceId: string, affected: Array<{ id: string; depth: number }>) => void
  showPath: (name: string, nodeIds: string[]) => void
  showSet: (label: string, nodeIds: string[]) => void
  resolve: (ref: string) => GNode | null
}

interface Options {
  graph: CopilotGraph | null
  onSelectNode: (id: string | null) => void
  /** Called before a scene action so the Workspace can switch to a tab that shows the galaxy. */
  onRevealGalaxy?: () => void
}

type Evaluated = { outcome: ToolOutcome; commit?: () => void }

const token = () => Date.now() + Math.random()
const asString = (v: unknown): string => (typeof v === 'string' ? v : v == null ? '' : String(v))

export function useGalaxyCopilotBridge({ graph, onSelectNode, onRevealGalaxy }: Options): GalaxyCopilotBridge {
  const [fx, setFx] = useState<CopilotFx>(EMPTY_FX)
  const [autoPilot, setAutoPilot] = useState(true)

  const graphRef = useRef(graph)
  const autoRef = useRef(autoPilot)
  const selectRef = useRef(onSelectNode)
  const revealRef = useRef(onRevealGalaxy)
  useEffect(() => {
    graphRef.current = graph
    autoRef.current = autoPilot
    selectRef.current = onSelectNode
    revealRef.current = onRevealGalaxy
  })

  // A new repository invalidates every overlay.
  useEffect(() => {
    setFx(EMPTY_FX)
  }, [graph])

  const resolve = useCallback((ref: string) => (graphRef.current ? resolveNodeRef(graphRef.current, ref) : null), [])

  const flyTo = useCallback((node: GNode, zoom = 1) => {
    revealRef.current?.()
    setFx((prev) => ({ ...prev, zoom, focusToken: token(), focusNodeId: node.id }))
    selectRef.current(node.id)
  }, [])

  const focusNode = useCallback(
    (ref: string, zoom = 1) => {
      const node = resolve(ref)
      if (!node) return false
      flyTo(node, zoom)
      return true
    },
    [resolve, flyTo],
  )

  const clearOverlay = useCallback(() => {
    setFx((prev) => ({ ...prev, workflow: null, blast: null, cluster: null }))
  }, [])

  const showImpact = useCallback((sourceId: string, affected: Array<{ id: string; depth: number }>) => {
    revealRef.current?.()
    setFx((prev) => ({ ...prev, blast: { sourceId, affected, depth: Math.max(1, ...affected.map((a) => a.depth)), token: token() }, workflow: null, cluster: null }))
  }, [])

  const showPath = useCallback((name: string, nodeIds: string[]) => {
    revealRef.current?.()
    setFx((prev) => ({ ...prev, workflow: { name, nodeIds, token: token() }, blast: null, cluster: null }))
  }, [])

  const showSet = useCallback((label: string, nodeIds: string[]) => {
    revealRef.current?.()
    setFx((prev) => ({ ...prev, cluster: { key: `set:${label}`, label, nodeIds, token: token() }, workflow: null, blast: null }))
  }, [])

  const evaluate = useCallback(
    (call: ToolCall): Evaluated => {
      const g = graphRef.current
      if (!g || g.nodes.length === 0) {
        return {
          outcome: { status: 'error', content: 'No repository graph is loaded.', summary: 'No graph loaded' },
        }
      }
      const idx = getIndex(g)
      const miss = (ref: string): Evaluated => ({
        outcome: {
          status: 'error',
          content: `Node not found: "${ref}". Use an exact node id from the graph context nodeIndex.`,
          summary: `Node not found: ${ref}`,
        },
      })

      switch (call.name) {
        case 'focusCameraOnNode': {
          const input = call.input as Partial<FocusCameraInput>
          const node = resolveNodeRef(g, asString(input.nodeId))
          if (!node) return miss(asString(input.nodeId))
          const zoom = Math.max(0.5, Math.min(4, Number(input.zoomLevel) || 1))
          return {
            outcome: {
              status: 'done',
              summary: `flyToNode("${node.path || node.label}")`,
              content: `Camera is flying to ${node.label} (${node.id}) and the Node Inspector is open. It has ${inDegree(g, node.id)} dependents and ${outDegree(g, node.id)} dependencies.`,
            },
            commit: () => flyTo(node, zoom),
          }
        }

        case 'highlightExecutionWorkflow': {
          const input = call.input as Partial<HighlightWorkflowInput>
          const refs = Array.isArray(input.orderedNodeIds) ? input.orderedNodeIds.map(asString) : []
          const nodes: GNode[] = []
          const missing: string[] = []
          for (const r of refs) {
            const n = resolveNodeRef(g, r)
            if (!n) missing.push(r)
            else if (nodes[nodes.length - 1]?.id !== n.id) nodes.push(n)
          }
          if (nodes.length < 2) {
            return {
              outcome: {
                status: 'error',
                content: `Need at least 2 resolvable node ids to draw a workflow${missing.length ? `; unresolved: ${missing.join(', ')}` : ''}.`,
                summary: 'Workflow needs ≥ 2 nodes',
              },
            }
          }
          const name = asString(input.workflowName) || 'Execution workflow'
          const pathLabel = nodes.map((n) => n.label).join(' → ')
          return {
            outcome: {
              status: 'done',
              summary: `Pulsing execution path: ${pathLabel}`,
              content: `Highlighted "${name}" across ${nodes.length} nodes with data pulses: ${pathLabel}.${missing.length ? ` Skipped unresolved ids: ${missing.join(', ')}.` : ''}`,
            },
            commit: () => {
              revealRef.current?.()
              setFx((prev) => ({
                ...prev,
                workflow: { name, nodeIds: nodes.map((n) => n.id), token: token() },
                blast: null,
                cluster: null,
              }))
            },
          }
        }

        case 'showBlastRadius': {
          const input = call.input as Partial<BlastRadiusInput>
          const src = resolveNodeRef(g, asString(input.sourceNodeId))
          if (!src) return miss(asString(input.sourceNodeId))
          const depth = Math.max(1, Math.min(5, Math.round(Number(input.depth)) || 3))
          const result = computeBlastRadius(g, src.id, depth)
          const claimed = new Set(
            (Array.isArray(input.affectedNodeIds) ? input.affectedNodeIds : [])
              .map((r) => resolveNodeRef(g, asString(r))?.id)
              .filter((x): x is string => Boolean(x)),
          )
          const confirmed = result.affected.filter((a) => claimed.has(a.id)).length
          const lines = result.affected
            .slice(0, 40)
            .map((a) => `d${a.depth}: ${idx.byId.get(a.id)?.label ?? a.id} (${a.id})`)
          return {
            outcome: {
              status: 'done',
              summary: `Blast radius of ${src.label}: ${result.affected.length} dependents (depth ≤ ${depth})`,
              content:
                `Computed from the real dependency graph: changing ${src.label} affects ${result.affected.length} of ${g.nodes.length} nodes within ${depth} hops ` +
                `(${confirmed} of your ${claimed.size} estimated ids were correct).` +
                (lines.length ? `\n${lines.join('\n')}` : ' No other node depends on it.'),
            },
            commit: () => {
              revealRef.current?.()
              setFx((prev) => ({
                ...prev,
                blast: { sourceId: src.id, affected: result.affected, depth, token: token() },
                workflow: null,
                cluster: null,
              }))
            },
          }
        }

        case 'filterGalaxyByCluster': {
          const input = call.input as Partial<FilterClusterInput>
          const cluster = resolveCluster(g, input.clusterId as string | number, asString(input.label))
          if (!cluster) {
            const keys = [...new Set(g.nodes.map(clusterKeyOf))].slice(0, 20).join(', ')
            return {
              outcome: {
                status: 'error',
                content: `Cluster not found: "${asString(input.clusterId)}". Available cluster keys: ${keys}.`,
                summary: `Cluster not found: ${asString(input.clusterId)}`,
              },
            }
          }
          return {
            outcome: {
              status: 'done',
              summary: `Isolated cluster ${cluster.label} (${cluster.files} stars)`,
              content: `Dimmed all other stars; ${cluster.label} (${cluster.files} files, ${cluster.loc} LOC) is illuminated.`,
            },
            commit: () => {
              revealRef.current?.()
              setFx((prev) => ({
                ...prev,
                cluster: { key: cluster.key, label: asString(input.label) || cluster.label, nodeIds: cluster.nodeIds, token: token() },
                workflow: null,
                blast: null,
              }))
            },
          }
        }

        default:
          return {
            outcome: { status: 'error', content: `Unknown tool: ${call.name}`, summary: `Unknown tool ${call.name}` },
          }
      }
    },
    [flyTo],
  )

  const executeTool = useCallback(
    (call: ToolCall, opts?: { force?: boolean }): ToolOutcome => {
      const { outcome, commit } = evaluate(call)
      if (outcome.status === 'error' || !commit) return outcome
      if (!autoRef.current && !opts?.force) {
        return {
          status: 'skipped',
          summary: outcome.summary,
          content: `${outcome.content}\n(Auto-pilot is OFF, so the 3D scene was not changed. The user can replay this action manually.)`,
        }
      }
      commit()
      return outcome
    },
    [evaluate],
  )

  const hasOverlay = Boolean(fx.workflow || fx.blast || fx.cluster)
  const overlayLabel = useMemo(() => {
    if (fx.workflow) return `Workflow · ${fx.workflow.name}`
    if (fx.blast) {
      const src = graph ? getIndex(graph).byId.get(fx.blast.sourceId) : undefined
      return `Blast radius · ${src?.label ?? fx.blast.sourceId} (${fx.blast.affected.length})`
    }
    if (fx.cluster) return `Cluster · ${fx.cluster.label}`
    return null
  }, [fx, graph])

  return { fx, hasOverlay, overlayLabel, autoPilot, setAutoPilot, executeTool, focusNode, clearOverlay, showImpact, showPath, showSet, resolve }
}
