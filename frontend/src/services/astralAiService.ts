/**
 * Astrograph AI client.
 *
 * All AI calls go to the Astrograph backend, which holds the provider key (from backend/.env),
 * retrieves repository-specific context from the persisted analysis, and streams the answer.
 * There is no client-side prompt building and no simulated fallback: when AI is unavailable the
 * backend's actionable error is surfaced as an `AstralAiError`.
 */

export { resolveNodeRef } from './graphAnalysis'

const API_BASE = (
  (import.meta.env?.VITE_API_BASE_URL as string | undefined) ||
  (import.meta.env?.VITE_API_URL as string | undefined) ||
  'http://127.0.0.1:8000'
).replace(/\/$/, '')

// ─── Types shared with the 3D bridge ──────────────────────────────────────────

export type AstralToolName =
  | 'focusCameraOnNode'
  | 'highlightExecutionWorkflow'
  | 'showBlastRadius'
  | 'filterGalaxyByCluster'

export interface FocusCameraInput {
  nodeId: string
  zoomLevel?: number
  reason: string
}
export interface HighlightWorkflowInput {
  orderedNodeIds: string[]
  workflowName: string
}
export interface BlastRadiusInput {
  sourceNodeId: string
  depth: number
  affectedNodeIds: string[]
}
export interface FilterClusterInput {
  clusterId: number | string
  label: string
}
export interface ToolCall {
  id: string
  name: string
  input: Record<string, unknown>
}
export interface ToolOutcome {
  status: 'done' | 'error' | 'skipped'
  content: string
  summary: string
}

// ─── Chat types ───────────────────────────────────────────────────────────────

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface AssistantStatus {
  configured: boolean
  provider: string | null
  model: string | null
  reason: string | null
  reachable: boolean
}

export interface ChatSource {
  path: string
  line_start: number | null
  line_end: number | null
  node_id: string
}

export interface ChatMeta {
  repository: string
  provider: string
  model: string
  sources: ChatSource[]
  highlighted_node_ids: string[]
  context_truncated: boolean
}

export class AstralAiError extends Error {
  code: string
  retryable: boolean
  constructor(code: string, message: string, retryable = false) {
    super(message)
    this.name = 'AstralAiError'
    this.code = code
    this.retryable = retryable
  }
}

/** Convert a FastAPI error payload ({detail: string | {code,message,retryable}}) into an AstralAiError. */
async function errorFromResponse(res: Response): Promise<AstralAiError> {
  try {
    const body = await res.json()
    const d = body?.detail
    if (d && typeof d === 'object' && d.message) return new AstralAiError(d.code || 'ai_error', d.message, Boolean(d.retryable))
    if (typeof d === 'string') return new AstralAiError('request_failed', d, res.status >= 500)
  } catch {
    // fall through
  }
  return new AstralAiError('request_failed', `Request failed with HTTP ${res.status}`, res.status >= 500)
}

function networkError(): AstralAiError {
  return new AstralAiError('backend_unreachable', `Cannot reach the Astrograph backend at ${API_BASE}. Start it and retry.`, true)
}

// ─── Status ───────────────────────────────────────────────────────────────────

export async function getAssistantStatus(): Promise<AssistantStatus> {
  try {
    const ctl = new AbortController()
    const t = setTimeout(() => ctl.abort(), 4000)
    const res = await fetch(`${API_BASE}/api/ai/status`, { signal: ctl.signal })
    clearTimeout(t)
    if (res.ok) {
      const d = await res.json()
      return { configured: Boolean(d.configured), provider: d.provider ?? null, model: d.model ?? null, reason: d.reason ?? null, reachable: true }
    }
  } catch {
    // reported below
  }
  return {
    configured: false,
    provider: null,
    model: null,
    reason: `Cannot reach the Astrograph backend at ${API_BASE}.`,
    reachable: false,
  }
}

// ─── Streaming chat ───────────────────────────────────────────────────────────

const MAX_HISTORY_TURNS = 8

export function trimHistory(turns: ChatTurn[], maxTurns = MAX_HISTORY_TURNS): ChatTurn[] {
  return turns.slice(-maxTurns * 2)
}

export interface TurnOptions {
  repoId: string | null
  selectedNodeId: string | null
  history: ChatTurn[]
  userText: string
  signal?: AbortSignal
  onMeta?: (meta: ChatMeta) => void
  onTextDelta: (delta: string) => void
}

/** Stream one answer. Resolves with the full text; throws AstralAiError on any failure. */
export async function runAstralTurn(opts: TurnOptions): Promise<string> {
  if (!opts.repoId) throw new AstralAiError('no_repository', 'Open an analysed repository to ask questions about it.')
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/repositories/${encodeURIComponent(opts.repoId)}/ai/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({
        question: opts.userText,
        history: trimHistory(opts.history),
        selected_node_id: opts.selectedNodeId,
      }),
      signal: opts.signal,
    })
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') throw err
    throw networkError()
  }
  if (!res.ok || !res.body) throw await errorFromResponse(res)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let full = ''
  let finished = false
  try {
    while (!finished) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let sep: number
      while ((sep = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, sep)
        buffer = buffer.slice(sep + 2)
        const line = frame.split('\n').find((l) => l.startsWith('data:'))
        if (!line) continue
        let evt: Record<string, unknown>
        try {
          evt = JSON.parse(line.slice(5).trim())
        } catch {
          continue
        }
        if (evt.type === 'meta') opts.onMeta?.(evt as unknown as ChatMeta)
        else if (evt.type === 'delta') {
          const text = String(evt.text ?? '')
          full += text
          opts.onTextDelta(text)
        } else if (evt.type === 'error') {
          throw new AstralAiError(String(evt.code ?? 'ai_error'), String(evt.message ?? 'AI request failed'), Boolean(evt.retryable))
        } else if (evt.type === 'done') finished = true
      }
    }
  } catch (err) {
    if (err instanceof AstralAiError || (err as Error)?.name === 'AbortError') throw err
    throw new AstralAiError('stream_interrupted', 'The connection to the backend was interrupted.', true)
  } finally {
    reader.cancel().catch(() => undefined)
  }
  if (!full.trim()) throw new AstralAiError('ai_empty_response', 'The AI returned an empty answer. Try again.', true)
  return full
}

// ─── Feature endpoints (deterministic facts + AI text kept separate by the backend) ──

async function postJson<T>(path: string, body: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  } catch {
    throw networkError()
  }
  if (!res.ok) throw await errorFromResponse(res)
  return res.json() as Promise<T>
}

async function getJson<T>(path: string): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`)
  } catch {
    throw networkError()
  }
  if (!res.ok) throw await errorFromResponse(res)
  return res.json() as Promise<T>
}

const repo = (id: string) => `/api/repositories/${encodeURIComponent(id)}`

export interface ImpactFacts {
  target: { id: string; path: string; type: string; name: string }
  direct_dependents: Array<{ id: string; path: string; kinds: string[]; lines: number[]; depth: number }>
  transitive_dependents: Array<{ id: string; path: string; kinds: string[]; lines: number[]; depth: number }>
  counts: { direct: number; transitive: number; depth_reached: number }
  importers_of_defining_file: Array<{ id: string; path: string }>
  affected_node_ids: string[]
  affected_edge_ids: string[]
  basis: string
}
export interface HealthFinding {
  id: string
  category: string
  severity: string
  title: string
  rule: string
  evidence: Record<string, unknown>
  node_ids: string[]
  paths: string[]
}
export interface GraphQueryResult {
  node_ids: string[]
  edge_ids: string[]
  matched: number
  needs_clarification: string | null
  explanation: string
  request: string
}
export interface Diagnostics {
  status: string
  files: Record<string, any>
  syntax_errors: Array<{ file_path: string; errors: Array<{ line: number | null; message: string }> }>
  symbols: Record<string, number>
  dependencies: Record<string, number>
  unresolved_internal_imports: Array<{ source_file: string; target: string; line: number | null; reason: string }>
  warnings: string[]
  timings_ms: Record<string, number>
}

export const aiApi = {
  impactFacts: (id: string, nodeId: string) => getJson<ImpactFacts>(`${repo(id)}/insights/impact?node_id=${encodeURIComponent(nodeId)}`),
  impactAssessment: (id: string, nodeId: string) => postJson<{ facts: ImpactFacts; assessment: string; model: string }>(`${repo(id)}/ai/impact`, { node_id: nodeId }),
  path: (id: string, source: string, target: string) =>
    getJson<{ found: boolean; node_ids: string[]; edge_ids: string[]; steps: Array<{ from: string; to: string; kinds: string[]; lines: number[] }> }>(
      `${repo(id)}/insights/path?source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`,
    ),
  health: (id: string) => getJson<{ thresholds: Record<string, number>; counts: Record<string, number>; findings: HealthFinding[]; disclaimer: string }>(`${repo(id)}/insights/health`),
  architecture: (id: string, regenerate: boolean) => postJson<{ facts: any; narrative: string; model: string; cached: boolean; generated_at: string }>(`${repo(id)}/ai/architecture`, { regenerate }),
  onboarding: (id: string) =>
    postJson<{ overview?: string; note?: string; steps: Array<{ step: number; node_id: string; path: string; evidence: string; why: string; look_for: string; prerequisites: string[]; used_by: string[] }> }>(`${repo(id)}/ai/onboarding`, {}),
  graphQuery: (id: string, text: string) => postJson<GraphQueryResult>(`${repo(id)}/ai/graph-query`, { text }),
  advice: (id: string, nodeId: string, focus: string) => postJson<{ advice: string; facts: any; model: string }>(`${repo(id)}/ai/advice`, { node_id: nodeId, focus }),
  diagnostics: (id: string) => getJson<{ analysis_id: string; created_at: string; diagnostics: Diagnostics }>(`${repo(id)}/diagnostics`),
}
