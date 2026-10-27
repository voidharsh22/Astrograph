/**
 * AstralAiAssistant — Graph-aware spatial copilot powered by Claude Sonnet 5.5.
 *
 * One mounted instance serves both access modes so the conversation survives switching:
 *   • variant="docked": the right 35% column of the "Astral AI Assistant" workspace tab.
 *   • variant="drawer": a glass slide-over opened with Ctrl/Cmd+K or the sparkle launcher.
 */

import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Check,
  ChevronRight,
  Copy,
  Crosshair,
  Filter,
  Navigation,
  Play,
  Radar,
  Radio,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  X,
} from 'lucide-react'
import {
  AssistantStatus,
  AstralAiError,
  ChatSource,
  ChatTurn,
  ToolCall,
  getAssistantStatus,
  runAstralTurn,
} from '../services/astralAiService'
import { CopilotGraph, GNode, pagerank } from '../services/graphAnalysis'
import type { GalaxyCopilotBridge } from '../hooks/useGalaxyCopilotBridge'
import '../styles/astralAi.css'

// ─── Types ────────────────────────────────────────────────────────────────────

interface ToolPart {
  kind: 'tool'
  id: string
  name: string
  input: Record<string, unknown>
  status: 'running' | 'done' | 'error' | 'skipped'
  summary: string
  content: string
}
interface TextPart {
  kind: 'text'
  text: string
}
type Part = TextPart | ToolPart

interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  text?: string
  attached?: string[]
  parts: Part[]
  streaming?: boolean
  sources?: ChatSource[]
  model?: string
  truncated?: boolean
  error?: { code: string; message: string; retryable: boolean }
  question?: string
}

export interface AstralAiAssistantProps {
  graph: CopilotGraph | null
  selectedNodeId: string | null
  bridge: GalaxyCopilotBridge
  variant: 'docked' | 'drawer'
  /** Drawer only: whether the slide-over is visible. */
  open?: boolean
  onOpen?: () => void
  onClose?: () => void
  /** A prompt to send into the copilot (token changes per request). */
  request?: { text: string; token: number } | null
  /** Drawer only: px from the viewport's right edge (shifts left while the edge inspector is open). */
  drawerOffset?: number
  /** Backend repository id the conversation is scoped to. */
  repoId: string | null
}

const STARTERS = [
  { icon: '🪐', text: 'Explain the architecture of this repository' },
  { icon: '🧭', text: 'Which files should I read first to understand this project?' },
  { icon: '🔍', text: 'Where is authentication handled?' },
  { icon: '🔗', text: 'How does data move through this codebase?' },
]

let uid = 0
const nextId = () => `m${Date.now().toString(36)}${uid++}`

function prettyModel(id: string): string {
  const parts = id.split('-').filter((p) => !/^\d{8}$/.test(p))
  const words: string[] = []
  const nums: string[] = []
  for (const p of parts) (/^\d+$/.test(p) ? nums : words).push(p)
  return [...words.map((w) => w.toUpperCase()), nums.join('.')].filter(Boolean).join(' ')
}

// ─── Syntax highlighting (tiny, dependency-free) ──────────────────────────────

const KEYWORDS = new Set(
  (
    'import from export default const let var function return if else for while class extends new async await try catch finally throw ' +
    'def self None True False lambda with as in not and or is pass yield raise elif except interface type enum public private static void ' +
    'null undefined true false this super typeof instanceof of struct impl fn pub use mod package func go defer chan'
  ).split(' '),
)

function highlight(code: string, lang: string): ReactNode[] {
  const l = lang.toLowerCase()
  const hashFamily = ['py', 'python', 'sh', 'bash', 'shell', 'yaml', 'yml', 'toml', 'rb', 'ruby'].includes(l)
  const slashFamily = ['js', 'jsx', 'ts', 'tsx', 'javascript', 'typescript', 'java', 'go', 'rust', 'rs', 'c', 'cpp', 'cs', 'json', 'css', 'kotlin', 'swift', 'php'].includes(l)
  if (!hashFamily && !slashFamily) return [code]

  const comment = hashFamily ? '#[^\\n]*' : '\\/\\/[^\\n]*|\\/\\*[\\s\\S]*?\\*\\/'
  const re = new RegExp(
    `(${comment})|("(?:\\\\.|[^"\\\\\\n])*"|'(?:\\\\.|[^'\\\\\\n])*'|\`(?:\\\\.|[^\`\\\\])*\`)|(\\b\\d+(?:\\.\\d+)?\\b)|([A-Za-z_$][\\w$]*)`,
    'g',
  )
  const out: ReactNode[] = []
  let last = 0
  let m: RegExpExecArray | null
  let k = 0
  while ((m = re.exec(code))) {
    if (m.index > last) out.push(code.slice(last, m.index))
    const [tok, com, str, num, word] = m
    if (com) out.push(<span key={k++} className="tok-com">{tok}</span>)
    else if (str) out.push(<span key={k++} className="tok-str">{tok}</span>)
    else if (num) out.push(<span key={k++} className="tok-num">{tok}</span>)
    else if (word) {
      if (KEYWORDS.has(word)) out.push(<span key={k++} className="tok-kw">{word}</span>)
      else if (code[m.index + word.length] === '(') out.push(<span key={k++} className="tok-fn">{word}</span>)
      else if (/^[A-Z]/.test(word)) out.push(<span key={k++} className="tok-type">{word}</span>)
      else out.push(word)
    }
    last = m.index + tok.length
  }
  if (last < code.length) out.push(code.slice(last))
  return out
}

function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false)
  const label = /^(mermaid)$/i.test(lang) ? 'MERMAID' : /^(text|ascii|txt|)$/i.test(lang) ? 'CALL FLOW' : lang.toUpperCase()
  const copy = () => {
    navigator.clipboard?.writeText(code).then(
      () => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1400)
      },
      () => undefined,
    )
  }
  return (
    <div className="astral-code">
      <div className="astral-code__bar">
        <span>{label}</span>
        <button type="button" onClick={copy} aria-label="Copy code">
          {copied ? <Check size={12} /> : <Copy size={12} />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre>
        <code>{highlight(code, lang)}</code>
      </pre>
    </div>
  )
}

// ─── Rich text: markdown subset + [[Node]] chips ──────────────────────────────

type Block =
  | { type: 'code'; lang: string; code: string }
  | { type: 'h'; level: number; text: string }
  | { type: 'ul' | 'ol'; items: string[] }
  | { type: 'p'; text: string }

function parseBlocks(src: string): Block[] {
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    const fence = /^\s*```\s*([\w+-]*)\s*$/.exec(line)
    if (fence) {
      const code: string[] = []
      i++
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) code.push(lines[i++])
      i++ // closing fence (or end of stream)
      blocks.push({ type: 'code', lang: fence[1] || '', code: code.join('\n') })
      continue
    }
    const h = /^(#{1,4})\s+(.*)$/.exec(line)
    if (h) {
      blocks.push({ type: 'h', level: h[1].length, text: h[2] })
      i++
      continue
    }
    if (/^\s*[-*•]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*•]\s+/, ''))
      blocks.push({ type: 'ul', items })
      continue
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+[.)]\s+/, ''))
      blocks.push({ type: 'ol', items })
      continue
    }
    if (!line.trim()) {
      i++
      continue
    }
    const para: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^\s*```/.test(lines[i]) &&
      !/^#{1,4}\s/.test(lines[i]) &&
      !/^\s*[-*•]\s+/.test(lines[i]) &&
      !/^\s*\d+[.)]\s+/.test(lines[i])
    ) {
      para.push(lines[i++])
    }
    blocks.push({ type: 'p', text: para.join('\n') })
  }
  return blocks
}

const FILE_REF_RE = /^[\w@./-]+\.[A-Za-z0-9]+(:\d+(-\d+)?)?$/
const INLINE_RE = /(\[\[[^\[\]\n]+\]\]|`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\s][^*\n]*\*)/g

function NodeChip({ reference, bridge }: { reference: string; bridge: GalaxyCopilotBridge }) {
  const node = bridge.resolve(reference.replace(/:\d+(-\d+)?$/, ''))
  if (!node) {
    return (
      <span className="astral-chip astral-chip--missing" title="Not found in this graph">
        {reference}
      </span>
    )
  }
  return (
    <button
      type="button"
      className="astral-chip"
      title={`${node.path || node.id} — click to warp the camera here`}
      onClick={() => bridge.focusNode(node.id)}
    >
      <Crosshair size={11} />
      {reference}
    </button>
  )
}

function Inline({ text, bridge }: { text: string; bridge: GalaxyCopilotBridge }) {
  const out: ReactNode[] = []
  let last = 0
  let k = 0
  for (const m of text.matchAll(INLINE_RE)) {
    const idx = m.index ?? 0
    if (idx > last) out.push(text.slice(last, idx))
    const tok = m[0]
    if (tok.startsWith('[[')) out.push(<NodeChip key={k++} reference={tok.slice(2, -2).trim()} bridge={bridge} />)
    else if (tok.startsWith('**')) out.push(<strong key={k++}>{tok.slice(2, -2)}</strong>)
    else if (tok.startsWith('`') && FILE_REF_RE.test(tok.slice(1, -1)) && bridge.resolve(tok.slice(1, -1).replace(/:\d+(-\d+)?$/, ''))) {
      out.push(<NodeChip key={k++} reference={tok.slice(1, -1)} bridge={bridge} />)
    } else if (tok.startsWith('`')) out.push(<code key={k++} className="astral-inline-code">{tok.slice(1, -1)}</code>)
    else out.push(<em key={k++}>{tok.slice(1, -1)}</em>)
    last = idx + tok.length
  }
  if (last < text.length) out.push(text.slice(last))
  return <>{out}</>
}

const RichText = memo(function RichText({ text, bridge }: { text: string; bridge: GalaxyCopilotBridge }) {
  const blocks = useMemo(() => parseBlocks(text), [text])
  return (
    <div className="astral-rich">
      {blocks.map((b, i) => {
        switch (b.type) {
          case 'code':
            return <CodeBlock key={i} lang={b.lang} code={b.code} />
          case 'h':
            return (
              <div key={i} className={`astral-h astral-h--${Math.min(b.level, 3)}`}>
                <Inline text={b.text} bridge={bridge} />
              </div>
            )
          case 'ul':
            return (
              <ul key={i}>
                {b.items.map((it, j) => (
                  <li key={j}>
                    <Inline text={it} bridge={bridge} />
                  </li>
                ))}
              </ul>
            )
          case 'ol':
            return (
              <ol key={i}>
                {b.items.map((it, j) => (
                  <li key={j}>
                    <Inline text={it} bridge={bridge} />
                  </li>
                ))}
              </ol>
            )
          default:
            return (
              <p key={i}>
                <Inline text={b.text} bridge={bridge} />
              </p>
            )
        }
      })}
    </div>
  )
})

// ─── Tool telemetry badge ────────────────────────────────────────────────────

const TOOL_ICON: Record<string, ReactNode> = {
  focusCameraOnNode: <Navigation size={13} />,
  highlightExecutionWorkflow: <Radio size={13} />,
  showBlastRadius: <Radar size={13} />,
  filterGalaxyByCluster: <Filter size={13} />,
}

function ToolBadge({ part, bridge }: { part: ToolPart; bridge: GalaxyCopilotBridge }) {
  const [open, setOpen] = useState(false)
  const [replayed, setReplayed] = useState(false)
  const label =
    part.status === 'running'
      ? `Executing ${part.name}…`
      : part.name === 'focusCameraOnNode' && part.status === 'done'
        ? `Executed: ${part.summary}`
        : part.summary

  const replay = () => {
    const call: ToolCall = { id: part.id, name: part.name, input: part.input }
    bridge.executeTool(call, { force: true })
    setReplayed(true)
  }

  return (
    <div className={`astral-tool astral-tool--${part.status}`}>
      <button type="button" className="astral-tool__head" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <span className="astral-tool__icon">{part.status === 'running' ? <span className="astral-spinner" /> : TOOL_ICON[part.name] ?? <Sparkles size={13} />}</span>
        <span className="astral-tool__label">{label}</span>
        <ChevronRight size={13} className={`astral-tool__chev ${open ? 'is-open' : ''}`} />
      </button>
      {part.status === 'skipped' && (
        <button type="button" className="astral-tool__replay" onClick={replay} disabled={replayed}>
          <Play size={11} /> {replayed ? 'Replayed' : 'Replay in 3D'}
        </button>
      )}
      {open && (
        <div className="astral-tool__body">
          <div className="astral-tool__kv">
            <span>tool</span>
            <code>{part.name}</code>
          </div>
          <pre>{JSON.stringify(part.input, null, 2)}</pre>
          {part.content && (
            <>
              <div className="astral-tool__kv">
                <span>result</span>
              </div>
              <pre>{part.content}</pre>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Message ─────────────────────────────────────────────────────────────────

const Message = memo(function Message({
  msg,
  bridge,
  graph,
  onRetry,
}: {
  msg: UiMessage
  bridge: GalaxyCopilotBridge
  graph: CopilotGraph | null
  onRetry?: (question: string) => void
}) {
  if (msg.role === 'user') {
    const attached = (msg.attached ?? [])
      .map((id) => graph?.nodes.find((n) => n.id === id))
      .filter((n): n is GNode => Boolean(n))
    return (
      <div className="astral-msg astral-msg--user">
        <div className="astral-bubble">
          {attached.length > 0 && (
            <div className="astral-attached astral-attached--sent">
              {attached.map((n) => (
                <span key={n.id} className="astral-pill">
                  @{n.label}
                </span>
              ))}
            </div>
          )}
          <div className="astral-user-text">{msg.text}</div>
        </div>
      </div>
    )
  }

  const empty = msg.parts.length === 0
  return (
    <div className="astral-msg astral-msg--ai">
      <div className="astral-avatar" aria-hidden>
        <Sparkles size={13} />
      </div>
      <div className="astral-ai-body">
        {empty && msg.streaming && (
          <div className="astral-thinking">
            <span className="astral-dots">
              <i />
              <i />
              <i />
            </span>
            Traversing graph topology…
          </div>
        )}
        {msg.parts.map((p, i) =>
          p.kind === 'text' ? (
            <RichText key={i} text={p.text} bridge={bridge} />
          ) : (
            <ToolBadge key={p.id + i} part={p} bridge={bridge} />
          ),
        )}
        {msg.streaming && !empty && <span className="astral-caret" />}
        {msg.error && (
          <div className="astral-error" role="alert">
            <strong>{msg.error.code === 'ai_not_configured' || msg.error.code === 'ai_key_rejected' || msg.error.code === 'ai_quota_exceeded' ? 'AI is not available' : 'Request failed'}</strong>
            <p>{msg.error.message}</p>
            {msg.error.retryable && msg.question && onRetry && (
              <button type="button" onClick={() => onRetry(msg.question as string)}>
                Retry
              </button>
            )}
          </div>
        )}
        {msg.sources && msg.sources.length > 0 && !msg.streaming && (
          <div className="astral-sources">
            <span>Context used (parser facts):</span>
            {msg.sources.map((src, i) => (
              <NodeChip key={i} reference={src.line_start ? `${src.path}:${src.line_start}` : src.path} bridge={bridge} />
            ))}
            {msg.truncated && <em>context truncated to fit the limit</em>}
          </div>
        )}
      </div>
    </div>
  )
})

// ─── Main component ──────────────────────────────────────────────────────────

export default function AstralAiAssistant({
  graph,
  selectedNodeId,
  bridge,
  variant,
  open = true,
  onOpen,
  onClose,
  request = null,
  drawerOffset = 16,
  repoId,
}: AstralAiAssistantProps) {
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [input, setInput] = useState('')
  const [attached, setAttached] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<AssistantStatus | null>(null)
  const [mention, setMention] = useState<{ query: string; start: number; active: number } | null>(null)

  const historyRef = useRef<ChatTurn[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickRef = useRef(true)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const visible = variant === 'docked' || open

  useEffect(() => {
    let alive = true
    getAssistantStatus().then((s) => alive && setStatus(s))
    return () => {
      alive = false
    }
  }, [])

  // Fresh conversation for each repository.
  const repoKey = `${repoId ?? ''}|${graph?.repo_name ?? ''}|${graph?.nodes.length ?? 0}`
  useEffect(() => {
    abortRef.current?.abort()
    historyRef.current = []
    setMessages([])
    setAttached([])
    setBusy(false)
  }, [repoKey])

  useEffect(() => () => abortRef.current?.abort(), [])

  // Auto-scroll while streaming unless the user scrolled up.
  useEffect(() => {
    const el = scrollRef.current
    if (el && stickRef.current) el.scrollTop = el.scrollHeight
  }, [messages])

  useEffect(() => {
    if (variant === 'drawer' && open) inputRef.current?.focus()
  }, [variant, open])

  const selectedNode = useMemo(
    () => (graph && selectedNodeId ? graph.nodes.find((n) => n.id === selectedNodeId) ?? null : null),
    [graph, selectedNodeId],
  )

  const aiReady = Boolean(status?.configured)
  const modelName = status?.model ? prettyModel(status.model) : 'UNAVAILABLE'

  const updateMsg = useCallback((id: string, fn: (m: UiMessage) => UiMessage) => {
    setMessages((ms) => ms.map((m) => (m.id === id ? fn(m) : m)))
  }, [])

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim()
      if (!text || busy) return
      const attachedIds = [...new Set(attached)]
      const aid = nextId()
      setMessages((ms) => [
        ...ms,
        { id: nextId(), role: 'user', text, attached: attachedIds, parts: [] },
        { id: aid, role: 'assistant', parts: [], streaming: true },
      ])
      setInput('')
      setAttached([])
      setMention(null)
      setBusy(true)
      stickRef.current = true

      const ctl = new AbortController()
      abortRef.current = ctl
      let streamed = ''

      try {
        await runAstralTurn({
          repoId,
          selectedNodeId,
          history: historyRef.current,
          userText: text,
          signal: ctl.signal,
          onMeta: (meta) => {
            updateMsg(aid, (m) => ({ ...m, sources: meta.sources, model: meta.model, truncated: meta.context_truncated }))
            if (bridge.autoPilot && meta.highlighted_node_ids.length) {
              bridge.showSet('Retrieved context', meta.highlighted_node_ids)
            }
          },
          onTextDelta: (d) => {
            streamed += d
            updateMsg(aid, (m) => {
              const parts = m.parts.slice()
              const last = parts[parts.length - 1]
              if (last && last.kind === 'text') parts[parts.length - 1] = { kind: 'text', text: last.text + d }
              else parts.push({ kind: 'text', text: d })
              return { ...m, parts }
            })
          },
        })
        historyRef.current = [...historyRef.current, { role: 'user', content: text }, { role: 'assistant', content: streamed }]
      } catch (err) {
        const aborted = (err as Error)?.name === 'AbortError'
        if (aborted) {
          updateMsg(aid, (m) => ({ ...m, parts: [...m.parts, { kind: 'text', text: '\n\n*(stopped)*' }] }))
        } else {
          const e = err as AstralAiError
          updateMsg(aid, (m) => ({
            ...m,
            question: text,
            error: { code: e.code || 'ai_error', message: e.message || 'Astral AI request failed.', retryable: e.retryable !== false },
          }))
        }
      } finally {
        updateMsg(aid, (m) => ({ ...m, streaming: false }))
        setBusy(false)
        abortRef.current = null
      }
    },
    [attached, busy, bridge, repoId, selectedNodeId, updateMsg],
  )

  const stop = () => abortRef.current?.abort()

  // External prompts (e.g. the edge inspector's "Ask Astral AI to Trace Full Path")
  useEffect(() => {
    if (!request) return
    void send(request.text)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.token])

  const reset = () => {
    abortRef.current?.abort()
    historyRef.current = []
    setMessages([])
    setAttached([])
    setInput('')
    bridge.clearOverlay()
  }

  // ── @node mention autocomplete ─────────────────────────────────────────────

  const mentionResults = useMemo(() => {
    if (!mention || !graph) return []
    const q = mention.query.toLowerCase()
    return graph.nodes
      .filter((n) => !q || n.label.toLowerCase().includes(q) || (n.path || '').toLowerCase().includes(q))
      .sort((a, b) => {
        const as = a.label.toLowerCase().startsWith(q) ? 1 : 0
        const bs = b.label.toLowerCase().startsWith(q) ? 1 : 0
        return bs - as || pagerank(b) - pagerank(a)
      })
      .slice(0, 6)
  }, [mention, graph])

  const onInputChange = (value: string, caret: number) => {
    setInput(value)
    const before = value.slice(0, caret)
    const m = /(^|\s)@([\w./-]*)$/.exec(before)
    if (m) setMention({ query: m[2], start: caret - m[2].length - 1, active: 0 })
    else setMention(null)
  }

  const pickMention = (n: GNode) => {
    if (!mention) return
    const el = inputRef.current
    const caret = el?.selectionStart ?? input.length
    const next = `${input.slice(0, mention.start)}@${n.label} ${input.slice(caret)}`
    setInput(next)
    setAttached((a) => (a.includes(n.id) ? a : [...a, n.id]))
    setMention(null)
    requestAnimationFrame(() => {
      el?.focus()
      const pos = mention.start + n.label.length + 2
      el?.setSelectionRange(pos, pos)
    })
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (mention && mentionResults.length) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        const d = e.key === 'ArrowDown' ? 1 : -1
        setMention({ ...mention, active: (mention.active + d + mentionResults.length) % mentionResults.length })
        return
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault()
        pickMention(mentionResults[mention.active])
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        setMention(null)
        return
      }
    }
    if (e.key === 'Escape' && variant === 'drawer') {
      onClose?.()
      return
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send(input)
    }
  }

  // Grow the textarea with its content.
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }, [input])

  const attachedNodes = attached
    .map((id) => graph?.nodes.find((n) => n.id === id))
    .filter((n): n is GNode => Boolean(n))

  const noGraph = !graph || graph.nodes.length === 0

  return (
    <>
      {variant === 'drawer' && !open && (
        <button type="button" className="astral-launcher" onClick={onOpen} aria-label="Open Astral AI Copilot (Ctrl+K)" title="Astral AI Copilot  ·  Ctrl/Cmd + K">
          <Sparkles size={20} />
          <span className="astral-launcher__ring" />
        </button>
      )}

      <section
        className={`astral-copilot astral-copilot--${variant} ${visible ? '' : 'is-closed'}`}
        style={variant === 'drawer' ? { right: drawerOffset } : undefined}
        aria-label="Astral AI Copilot"
        aria-hidden={!visible}
      >
        {/* Header */}
        <header className="astral-header">
          <div className="astral-header__top">
            <div className="astral-core" aria-hidden>
              <i />
              <i />
              <b />
            </div>
            <div className="astral-header__title">
              <h2>Astral AI Copilot</h2>
              <span>Graph-aware spatial architect</span>
            </div>
            <div className="astral-header__actions">
              <button type="button" onClick={reset} title="New conversation" aria-label="New conversation">
                <RotateCcw size={15} />
              </button>
              {variant === 'drawer' && (
                <button type="button" onClick={onClose} title="Close (Esc)" aria-label="Close copilot">
                  <X size={16} />
                </button>
              )}
            </div>
          </div>

          <div
            className={`astral-model-pill astral-model-pill--${aiReady ? 'claude' : 'simulation'}`}
            title={aiReady ? `${status?.provider} via the Astrograph backend` : status?.reason || 'AI status unknown'}
          >
            <span className="astral-dot" />
            {aiReady ? `[ MODEL: ${modelName} · ${String(status?.provider).toUpperCase()} · GRAPH-GROUNDED ]` : '[ AI UNAVAILABLE ]'}
          </div>
          {status && !aiReady && (
            <div className="astral-ai-banner" role="alert">
              {status.reason}
            </div>
          )}

          <div className="astral-context">
            <span className="astral-context__repo">
              {graph ? `${graph.repo_name || 'repository'} · ${graph.nodes.length} Nodes · ${graph.edges.length} Edges` : 'No repository loaded'}
            </span>
            {selectedNode && (
              <button type="button" className="astral-context__node" onClick={() => bridge.focusNode(selectedNode.id)} title="Re-center camera on the selected star">
                <Crosshair size={11} /> {selectedNode.label}
              </button>
            )}
          </div>
        </header>

        {/* Transcript */}
        <div
          className="astral-scroll"
          ref={scrollRef}
          onScroll={(e) => {
            const el = e.currentTarget
            stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
          }}
        >
          {messages.length === 0 ? (
            <div className="astral-empty">
              <div className="astral-empty__orb" aria-hidden />
              <h3>Ask about {graph?.repo_name || 'this repository'}</h3>
              <p>Answers use only this repository's parsed files, symbols and dependencies, and cite file paths and lines.</p>
              <div className="astral-starters">
                {STARTERS.map((s) => (
                  <button key={s.text} type="button" className="astral-starter" disabled={noGraph || busy || !aiReady} onClick={() => void send(s.text.replace(/`/g, ''))}>
                    <span>{s.icon}</span>
                    <em>{s.text.replace(/`/g, '')}</em>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m) => <Message key={m.id} msg={m} bridge={bridge} graph={graph} onRetry={(q) => void send(q)} />)
          )}
        </div>

        {/* Overlay status */}
        {bridge.hasOverlay && (
          <div className="astral-overlay-bar">
            <Radio size={12} />
            <span>{bridge.overlayLabel}</span>
            <button type="button" onClick={bridge.clearOverlay}>
              Clear overlay
            </button>
          </div>
        )}

        {/* Input bar */}
        <footer className="astral-input">
          {mention && mentionResults.length > 0 && (
            <ul className="astral-mentions" role="listbox">
              {mentionResults.map((n, i) => (
                <li key={n.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={i === mention.active}
                    className={i === mention.active ? 'is-active' : ''}
                    onMouseDown={(e) => {
                      e.preventDefault()
                      pickMention(n)
                    }}
                  >
                    <Crosshair size={11} />
                    <strong>{n.label}</strong>
                    <small>{n.path}</small>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {attachedNodes.length > 0 && (
            <div className="astral-attached">
              {attachedNodes.map((n) => (
                <span key={n.id} className="astral-pill">
                  @{n.label}
                  <button type="button" aria-label={`Remove ${n.label}`} onClick={() => setAttached((a) => a.filter((x) => x !== n.id))}>
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
          )}

          <div className="astral-input__box">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              disabled={noGraph || !aiReady}
              placeholder={noGraph ? 'Load a repository to start…' : 'Ask about architecture, flows, impact…  (type @ to attach a node)'}
              onChange={(e) => onInputChange(e.target.value, e.target.selectionStart)}
              onKeyDown={onKeyDown}
              aria-label="Message Astral AI"
            />
            {busy ? (
              <button type="button" className="astral-send astral-send--stop" onClick={stop} aria-label="Stop generating">
                <Square size={14} fill="currentColor" />
              </button>
            ) : (
              <button type="button" className="astral-send" onClick={() => void send(input)} disabled={!input.trim() || noGraph} aria-label="Send">
                <Send size={16} />
              </button>
            )}
          </div>

          <label className="astral-autopilot">
            <input type="checkbox" checked={bridge.autoPilot} onChange={(e) => bridge.setAutoPilot(e.target.checked)} />
            <span className="astral-switch" aria-hidden />
            <span>
              Auto-Pilot Camera <small>(Follow AI explanations in 3D)</small>
            </span>
          </label>
        </footer>
      </section>
    </>
  )
}
