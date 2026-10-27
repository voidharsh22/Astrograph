/**
 * Edge Data-Flow model for the Astrograph "Edge Data-Flow Inspector".
 *
 * Everything here is derived from two honest sources:
 *   1. the normalized graph (edge relation, weight, PageRank, cluster membership, degrees), and
 *   2. the *live* source text of the caller (and, for signatures, the target) when the backend can serve it.
 * Nothing is invented silently: fields that cannot be resolved statically are marked as
 * inferred (argument types from names) or unresolved (return types), and the synthetic demo
 * snippets are never presented as real call sites.
 */

import {
  CopilotGraph,
  GEdge,
  GNode,
  clusterKeyOf,
  getIndex,
  inDegree,
  outDegree,
  pagerank,
} from './graphAnalysis'

export type EdgeRelationship = 'FUNCTION_CALL' | 'MODULE_IMPORT' | 'CONTAINMENT' | 'DEFINITION'

/** What kind of construct the caller uses to reach the target. */
export type InvocationKind = 'function-call' | 'class-instantiation' | 'component-render' | 'reference'

/**
 * Where a parameter's type came from:
 *   declared = written in the target's signature, literal = the value at the call site is a literal,
 *   inferred = guessed from a name, unknown = no evidence.
 */
export type TypeSource = 'declared' | 'literal' | 'inferred' | 'unknown'

export interface PayloadField {
  /** Parameter name (from the target signature when matched, otherwise the keyword / prop / arg position). */
  name: string
  /** Expression exactly as written at the call site. */
  value: string
  type: string
  typeSource: TypeSource
  /** How the value was bound: by position, by keyword argument (Python), or by JSX prop. */
  via: 'position' | 'keyword' | 'prop'
  /** True when the parameter was found in the target's signature. */
  matched: boolean
}

export interface ImportRef {
  line: number
  /** The import statement, whitespace-collapsed. */
  statement: string
  /** Imported names, e.g. ["Station", "Reading as R"]. */
  names: string[]
  moduleName: string
}

export interface SignatureParam {
  name: string
  type: string | null
  defaultValue: string | null
}

export interface TargetSignature {
  symbol: string
  kind: 'function' | 'class'
  line: number
  params: SignatureParam[]
  returnType: string | null
  destructured: boolean
}

export interface CallSiteLine {
  n: number
  text: string
  hit: boolean
}

export interface CallSite {
  /** First line of the invocation (1-based). */
  line: number
  /** Last line of the invocation (1-based); equals `line` for single-line calls. */
  endLine: number
  kind: InvocationKind
  callee: string | null
  /** One-line form of the invocation, for the pill. */
  invocation: string
  /** Variable (or "return") the result is bound to, when the call is assigned. */
  assignedTo: string | null
  args: PayloadField[]
  signature: TargetSignature | null
  lines: CallSiteLine[]
  /** Other lines in the caller that also invoke or render the target (1-based, deduplicated). */
  otherLines: number[]
}

export interface EdgeDataFlow {
  edgeId: string
  source: GNode
  target: GNode
  relationship: EdgeRelationship
  relationshipLabel: string
  bidirectional: boolean
  coupling: number
  couplingBand: 'High' | 'Medium' | 'Low'
  callFrequency: 'High (Hot Path)' | 'Medium' | 'Low'
  crossCluster: boolean
  sourceCluster: string
  targetCluster: string
  /** Arguments / props passed at the call site (same as callSite.args). */
  outbound: PayloadField[]
  targetSymbols: string[]
  imports: ImportRef[]
  callSite: CallSite | null
  signature: TargetSignature | null
  /** 'live' = real file text from the backend; 'unavailable' = could not read the caller file. */
  sourceOrigin: 'live' | 'unavailable'
  targetOrigin: 'live' | 'unavailable'
  summary: string
  failureMode: string
}

const RELATION_LABEL: Record<EdgeRelationship, string> = {
  FUNCTION_CALL: 'SYNCHRONOUS CALL',
  MODULE_IMPORT: 'AST MODULE IMPORT',
  CONTAINMENT: 'CONTAINMENT',
  DEFINITION: 'DEFINITION',
}

export const KIND_LABEL: Record<InvocationKind, string> = {
  'function-call': 'Function call',
  'class-instantiation': 'Class instantiation',
  'component-render': 'Component render (JSX)',
  reference: 'Reference only',
}

const stripExt = (s: string) => s.replace(/\.[a-z0-9]+$/i, '')
const bare = (label: string) => label.replace(/\(\)$/, '')
const lastSegment = (s: string) => s.split('.').pop() || s
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const isPythonPath = (p?: string | null) => /\.py$/i.test(p || '')

export function toRelationship(relation?: string): EdgeRelationship {
  switch ((relation || '').toLowerCase()) {
    case 'calls':
      return 'FUNCTION_CALL'
    case 'contains':
      return 'CONTAINMENT'
    case 'defines':
      return 'DEFINITION'
    default:
      return 'MODULE_IMPORT'
  }
}

/** Public-facing symbols that the target file defines (functions, classes). */
function targetSymbolsOf(graph: CopilotGraph, target: GNode): string[] {
  if (target.type === 'function' || target.type === 'class') return [bare(target.label)]
  return graph.nodes
    .filter((n) => n.path && n.path === target.path && (n.type === 'function' || n.type === 'class'))
    .map((n) => bare(n.label))
    .slice(0, 12)
}

function classNamesOf(graph: CopilotGraph, target: GNode): string[] {
  const out = new Set<string>()
  if (target.type === 'class') out.add(bare(target.label))
  for (const n of graph.nodes) {
    if (n.type === 'class' && n.path && n.path === target.path) out.add(bare(n.label))
  }
  return [...out]
}

function guessType(name: string): string {
  const n = name.toLowerCase()
  if (/^(is_|has_|can_|should_)/.test(n) || /^(enabled|flag|force|dry_run|verbose)$/.test(n)) return 'boolean'
  if (/(^|_)(count|len|size|limit|depth|index|idx|n|num|timeout|ms|seconds|offset)$/.test(n)) return 'number'
  if (/(^|_)(id|name|path|url|text|email|key|token|label|msg|message|hash|sensor|slug)$/.test(n) || /_id$/.test(n)) return 'string'
  return 'unknown'
}

/* ────────────────────────── lexical helpers ────────────────────────── */

/**
 * Blank out comments (keeping offsets and newlines identical) so that structural scanning
 * never reads commented-out code. String literals are preserved verbatim.
 */
function maskComments(src: string, hash: boolean): string {
  let out = ''
  let quote: string | null = null
  for (let i = 0; i < src.length; i++) {
    const ch = src[i]
    if (quote) {
      out += ch
      if (ch === '\\' && i + 1 < src.length) {
        out += src[++i]
        continue
      }
      if (ch === quote) quote = null
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch
      out += ch
      continue
    }
    const isComment = (hash && ch === '#') || (!hash && ch === '/' && src[i + 1] === '/')
    if (isComment) {
      while (i < src.length && src[i] !== '\n') {
        out += ' '
        i++
      }
      if (i < src.length) out += '\n'
      continue
    }
    out += ch
  }
  return out
}

/** Index of the bracket closing the one at `openIdx`, or -1. Quote-aware (text must be comment-masked). */
function scanBalanced(text: string, openIdx: number): number {
  const pairs: Record<string, string> = { '(': ')', '[': ']', '{': '}' }
  const stack: string[] = []
  let quote: string | null = null
  const limit = Math.min(text.length, openIdx + 20000)
  for (let i = openIdx; i < limit; i++) {
    const ch = text[i]
    if (quote) {
      if (ch === '\\') i++
      else if (ch === quote) quote = null
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch
      continue
    }
    if (pairs[ch]) stack.push(pairs[ch])
    else if (ch === ')' || ch === ']' || ch === '}') {
      stack.pop()
      if (stack.length === 0) return i
    }
  }
  return -1
}

/** Split on top-level commas (ignores commas inside brackets and strings). */
function splitTop(inner: string): string[] {
  const out: string[] = []
  let depth = 0
  let quote: string | null = null
  let cur = ''
  for (let i = 0; i < inner.length; i++) {
    const ch = inner[i]
    if (quote) {
      cur += ch
      if (ch === '\\' && i + 1 < inner.length) cur += inner[++i]
      else if (ch === quote) quote = null
      continue
    }
    if (ch === '"' || ch === "'" || ch === '`') {
      quote = ch
      cur += ch
      continue
    }
    if (ch === '(' || ch === '[' || ch === '{') depth++
    else if (ch === ')' || ch === ']' || ch === '}') depth--
    if (ch === ',' && depth === 0) {
      if (cur.trim()) out.push(cur.trim())
      cur = ''
      continue
    }
    cur += ch
  }
  if (cur.trim()) out.push(cur.trim())
  return out
}

/** End of a JSX opening tag starting at `from` (the index of the first character after the tag name). */
function jsxTagEnd(text: string, from: number): number {
  let depth = 0
  let quote: string | null = null
  const limit = Math.min(text.length, from + 6000)
  for (let i = from; i < limit; i++) {
    const ch = text[i]
    if (quote) {
      if (ch === quote) quote = null
      continue
    }
    if (ch === '"' || ch === "'") quote = ch
    else if (ch === '{') depth++
    else if (ch === '}') depth--
    else if (ch === '>' && depth === 0) return i
  }
  return -1
}

/** Parse JSX attributes: `name="x"`, `name={expr}`, or a bare boolean `name`. */
function splitJsxProps(inner: string): { name: string; value: string | null }[] {
  const out: { name: string; value: string | null }[] = []
  const s = inner
  let i = 0
  while (i < s.length) {
    while (i < s.length && /\s/.test(s[i])) i++
    const m = /^[A-Za-z_$][\w$:.-]*/.exec(s.slice(i))
    if (!m) {
      i++
      continue
    }
    const name = m[0]
    i += name.length
    let j = i
    while (j < s.length && /\s/.test(s[j])) j++
    if (s[j] !== '=') {
      out.push({ name, value: null })
      i = j
      continue
    }
    j++
    while (j < s.length && /\s/.test(s[j])) j++
    let end: number
    if (s[j] === '{') {
      const c = scanBalanced(s, j)
      end = c < 0 ? s.length : c + 1
    } else if (s[j] === '"' || s[j] === "'") {
      const q = s[j]
      let k = j + 1
      while (k < s.length && s[k] !== q) k++
      end = k + 1
    } else {
      end = j
      while (end < s.length && !/\s/.test(s[end])) end++
    }
    out.push({ name, value: s.slice(j, end) })
    i = end
  }
  return out
}

/** Strip one pair of JSX braces: `{expr}` → `expr`. */
function unwrapBraces(v: string): string {
  const t = v.trim()
  if (t.startsWith('{') && scanBalanced(t, 0) === t.length - 1) return t.slice(1, -1).trim()
  return t
}

function lineStartsOf(text: string): number[] {
  const starts = [0]
  for (let i = 0; i < text.length; i++) if (text[i] === '\n') starts.push(i + 1)
  return starts
}

/** 1-based line number of a character index. */
function lineOf(starts: number[], idx: number): number {
  let lo = 0
  let hi = starts.length - 1
  while (lo < hi) {
    const mid = (lo + hi + 1) >> 1
    if (starts[mid] <= idx) lo = mid
    else hi = mid - 1
  }
  return lo + 1
}

/* ────────────────────────── value classification ────────────────────────── */

type ValueKind = 'string' | 'number' | 'boolean' | 'null' | 'array' | 'object' | 'function' | 'instance' | 'call' | 'identifier' | 'expression'

function classifyValue(expr: string): { kind: ValueKind; type: string } {
  const e = expr.trim()
  if (/^(?:[fbru]{0,2})(['"`])[\s\S]*\1$/i.test(e)) return { kind: 'string', type: 'string' }
  if (/^[-+]?(\d[\d_]*(\.\d+)?|\.\d+)([eE][-+]?\d+)?$/.test(e)) return { kind: 'number', type: 'number' }
  if (/^(True|False|true|false)$/.test(e)) return { kind: 'boolean', type: 'boolean' }
  if (/^(None|null|undefined)$/.test(e)) return { kind: 'null', type: 'null' }
  if (e.startsWith('[') && scanBalanced(e, 0) === e.length - 1) return { kind: 'array', type: 'array' }
  if (e.startsWith('{') && scanBalanced(e, 0) === e.length - 1) return { kind: 'object', type: 'object' }
  if (/=>/.test(e) || /^(function\b|lambda\b)/.test(e)) return { kind: 'function', type: 'function' }
  const nm = /^new\s+([A-Za-z_$][\w$.]*)/.exec(e)
  if (nm) return { kind: 'instance', type: `${lastSegment(nm[1])} instance` }
  const cm = /^([A-Za-z_$][\w$.]*)\s*\(/.exec(e)
  if (cm && e.endsWith(')')) return { kind: 'call', type: `result of ${cm[1]}()` }
  if (/^[A-Za-z_$][\w$.]*$/.test(e)) return { kind: 'identifier', type: 'unknown' }
  return { kind: 'expression', type: 'expression' }
}

/* ────────────────────────── signatures ────────────────────────── */

function parseParams(inner: string): { params: SignatureParam[]; destructured: boolean } {
  const params: SignatureParam[] = []
  let destructured = false
  for (const raw of splitTop(inner)) {
    let p = raw.trim().replace(/^\*{1,2}/, '')
    if (!p) continue
    if (p.startsWith('{')) {
      destructured = true
      const close = scanBalanced(p, 0)
      const body = close > 0 ? p.slice(1, close) : p.slice(1)
      const after = close > 0 ? p.slice(close + 1) : ''
      void after
      for (const part of splitTop(body)) {
        const name = part.split(/[:=]/)[0].trim()
        if (name) params.push({ name, type: null, defaultValue: null })
      }
      continue
    }
    const eq = p.indexOf('=')
    const head = (eq >= 0 ? p.slice(0, eq) : p).trim()
    const defaultValue = eq >= 0 ? p.slice(eq + 1).trim() : null
    const hm = /^([A-Za-z_$][\w$]*)\??\s*(?::\s*([\s\S]+))?$/.exec(head)
    if (!hm) continue
    params.push({ name: hm[1], type: hm[2]?.trim() || null, defaultValue })
  }
  const withoutSelf = params.filter((p, i) => !(i === 0 && ['self', 'cls', 'this'].includes(p.name)))
  return { params: withoutSelf, destructured }
}

/** Locate a definition of `symbol` in the target file and read its parameters and return type. */
export function parseSignature(targetRaw: string, symbol: string, hash: boolean, preferClass: boolean): TargetSignature | null {
  const text = maskComments(targetRaw.replace(/\r\n/g, '\n'), hash)
  const starts = lineStartsOf(text)
  const esc = escapeRe(symbol)

  const findFn = (): { idx: number; open: number } | null => {
    const re = hash
      ? new RegExp(`^[ \\t]*(?:async[ \\t]+)?def[ \\t]+${esc}[ \\t]*\\(`, 'm')
      : new RegExp(
          `(?:function[ \\t*]+${esc}[ \\t]*(?:<[^>\\n]*>)?[ \\t]*\\()|(?:(?:const|let|var)[ \\t]+${esc}[ \\t]*(?::[^=\\n]+)?=[ \\t]*(?:async[ \\t]*)?(?:function[ \\t]*)?\\()`,
        )
    const m = re.exec(text)
    if (!m) return null
    return { idx: m.index, open: m.index + m[0].length - 1 }
  }

  const findClassInit = (): { idx: number; open: number; line: number } | null => {
    const re = new RegExp(hash ? `^[ \\t]*class[ \\t]+${esc}\\b` : `class[ \\t]+${esc}\\b`, 'm')
    const decl = re.exec(text)
    if (!decl) return null
    const window = text.slice(decl.index, decl.index + 4000)
    const init = hash ? /def[ \t]+__init__[ \t]*\(/.exec(window) : /constructor[ \t]*\(/.exec(window)
    if (!init) return { idx: decl.index, open: -1, line: lineOf(starts, decl.index) }
    const open = decl.index + init.index + init[0].length - 1
    return { idx: decl.index, open, line: lineOf(starts, decl.index) }
  }

  const tryClass = (): TargetSignature | null => {
    const c = findClassInit()
    if (!c) return null
    if (c.open < 0) return { symbol, kind: 'class', line: c.line, params: [], returnType: null, destructured: false }
    const close = scanBalanced(text, c.open)
    if (close < 0) return null
    const { params, destructured } = parseParams(text.slice(c.open + 1, close))
    return { symbol, kind: 'class', line: lineOf(starts, c.idx), params, returnType: null, destructured }
  }

  const tryFn = (): TargetSignature | null => {
    const f = findFn()
    if (!f) return null
    const close = scanBalanced(text, f.open)
    if (close < 0) return null
    const { params, destructured } = parseParams(text.slice(f.open + 1, close))
    const rest = text.slice(close + 1, close + 200)
    const ret = hash
      ? /^[ \t]*->[ \t]*([^:\n]+?)[ \t]*:/.exec(rest)?.[1]
      : /^[ \t]*:[ \t]*([^{=\n;]+?)[ \t]*(?:\{|=>|$)/.exec(rest)?.[1]
    return {
      symbol,
      kind: 'function',
      line: lineOf(starts, f.idx),
      params,
      returnType: ret?.trim() || null,
      destructured,
    }
  }

  return preferClass ? tryClass() ?? tryFn() : tryFn() ?? tryClass()
}

/* ────────────────────────── imports ────────────────────────── */

/** Import statements in the caller that bring in the target module (or one of its symbols). */
export function extractImports(sourceText: string, target: GNode, symbols: string[], hash: boolean): ImportRef[] {
  const raw = sourceText.replace(/\r\n/g, '\n')
  const text = maskComments(raw, hash)
  const starts = lineStartsOf(text)
  const stem = stripExt(target.label)
  const out: ImportRef[] = []
  const seen = new Set<number>()

  const consider = (moduleName: string, names: string[], index: number, statement: string) => {
    const modLast = stripExt(lastSegment(moduleName.replace(/^\.+/, '').replace(/\//g, '.')))
    const wanted = [stem, ...symbols]
    const symbolHit = names.some((n) => wanted.includes(n.split(/\s+as\s+/)[0].trim()))
    if (modLast !== stem && !symbolHit) return
    const line = lineOf(starts, index)
    if (seen.has(line)) return
    seen.add(line)
    out.push({
      line,
      statement: statement.replace(/\s+/g, ' ').trim().slice(0, 180),
      names,
      moduleName,
    })
  }

  if (hash) {
    const reFrom = /^[ \t]*from[ \t]+([\w.]+)[ \t]+import[ \t]+(\([^)]*\)|[^\n]+)/gm
    let m: RegExpExecArray | null
    while ((m = reFrom.exec(text))) {
      const names = m[2].replace(/[()]/g, '').split(',').map((s) => s.trim()).filter(Boolean)
      consider(m[1], names, m.index, m[0])
    }
    const reImport = /^[ \t]*import[ \t]+([\w.]+)(?:[ \t]+as[ \t]+\w+)?[ \t]*$/gm
    while ((m = reImport.exec(text))) consider(m[1], [m[1]], m.index, m[0])
  } else {
    const reEs = /import[ \t]+([^'";]*?)[ \t]*from[ \t]*['"]([^'"]+)['"]/g
    let m: RegExpExecArray | null
    while ((m = reEs.exec(text))) {
      const clause = m[1].trim()
      const names: string[] = []
      const brace = /\{([\s\S]*?)\}/.exec(clause)
      if (brace) names.push(...brace[1].split(',').map((s) => s.trim()).filter(Boolean))
      const rest = clause.replace(/\{[\s\S]*?\}/, '').replace(/,/g, ' ').trim()
      if (rest) names.push(...rest.split(/\s+/).filter(Boolean))
      consider(m[2], names, m.index, m[0])
    }
    const reReq = /(?:const|let|var)[ \t]+([\w{}\s,:]+?)[ \t]*=[ \t]*require\([ \t]*['"]([^'"]+)['"][ \t]*\)/g
    while ((m = reReq.exec(text))) {
      const names = m[1].replace(/[{}]/g, '').split(',').map((s) => s.trim()).filter(Boolean)
      consider(m[2], names, m.index, m[0])
    }
  }
  return out.sort((a, b) => a.line - b.line)
}

/* ────────────────────────── call-site location ────────────────────────── */

export interface CallSiteContext {
  hash: boolean
  classNames: string[]
  targetText: string | null
  targetHash: boolean
}

/**
 * Locate the most likely invocation of `target` inside the caller's source.
 * Anchor = best-scoring line (import > call > `module.` access > bare mention); the invocation is the
 * first call/new/JSX render of a target name at or after that line. The full expression is read across
 * lines by balancing brackets, so multi-line calls are shown whole.
 */
export function findCallSite(sourceText: string, target: GNode, symbols: string[], ctx: CallSiteContext): CallSite | null {
  const stem = stripExt(target.label)
  const names = [...new Set([stem, ...symbols])].filter((s) => s.length >= 3)
  if (!names.length || !sourceText) return null

  const raw = sourceText.replace(/\r\n/g, '\n')
  const masked = maskComments(raw, ctx.hash)
  const rawLines = raw.split('\n')
  const maskedLines = masked.split('\n')
  const starts = lineStartsOf(raw)

  // 1. Anchor line by score.
  let best = { idx: -1, score: 0 }
  maskedLines.forEach((line, i) => {
    const t = line.trim()
    if (!t) return
    let score = 0
    for (const name of names) {
      const esc = escapeRe(name)
      if (new RegExp(`(^|\\s)(import|from)\\b.*\\b${esc}\\b`).test(t)) score = Math.max(score, 3)
      else if (new RegExp(`\\b${esc}\\s*\\(`).test(t)) score = Math.max(score, 3)
      else if (new RegExp(`\\b${esc}\\.`).test(t)) score = Math.max(score, 2)
      else if (new RegExp(`\\b${esc}\\b`).test(t)) score = Math.max(score, 1)
    }
    if (score > best.score) best = { idx: i, score }
  })
  if (best.idx < 0) return null
  const anchorStart = starts[best.idx]

  // 2. Every invocation candidate in the file.
  const alt = [...names].sort((a, b) => b.length - a.length).map(escapeRe).join('|')
  type Cand = { index: number; kind: InvocationKind; callee: string; openAt: number; isJsx: boolean }
  const cands: Cand[] = []
  const lineHead = (index: number) => masked.slice(masked.lastIndexOf('\n', index - 1) + 1, index)

  const reNew = new RegExp(`\\bnew\\s+((?:[A-Za-z_$][\\w$]*\\.)*(?:${alt}))\\s*\\(`, 'g')
  const reCall = new RegExp(`(?<![\\w$.])((?:[A-Za-z_$][\\w$]*\\.)*)(${alt})\\s*\\(`, 'g')
  let m: RegExpExecArray | null
  while ((m = reNew.exec(masked))) {
    cands.push({ index: m.index, kind: 'class-instantiation', callee: m[1], openAt: m.index + m[0].length - 1, isJsx: false })
  }
  while ((m = reCall.exec(masked))) {
    if (/\b(def|class|function|async)\s+$/.test(lineHead(m.index))) continue
    const callee = m[1] + m[2]
    const bareName = lastSegment(callee)
    const kind: InvocationKind = /^[A-Z]/.test(bareName) && ctx.classNames.includes(bareName) ? 'class-instantiation' : 'function-call'
    cands.push({ index: m.index, kind, callee, openAt: m.index + m[0].length - 1, isJsx: false })
  }
  // Module-attribute calls: `telemetry.ingest(...)` where the caller imported the module.
  const reModule = new RegExp(`(?<![\\w$.])(${escapeRe(stem)})\\.([A-Za-z_$][\\w$]*)\\s*\\(`, 'g')
  while ((m = reModule.exec(masked))) {
    if (/\b(def|class|function|async)\s+$/.test(lineHead(m.index))) continue
    const attr = m[2]
    const kind: InvocationKind = /^[A-Z]/.test(attr) && ctx.classNames.includes(attr) ? 'class-instantiation' : 'function-call'
    cands.push({ index: m.index, kind, callee: `${m[1]}.${attr}`, openAt: m.index + m[0].length - 1, isJsx: false })
  }
  if (!ctx.hash) {
    const reJsx = new RegExp(`<((?:[A-Za-z_$][\\w$]*\\.)*(?:${alt}))(?=[\\s/>])`, 'g')
    while ((m = reJsx.exec(masked))) {
      if (!/^[A-Z]/.test(lastSegment(m[1]))) continue
      cands.push({ index: m.index, kind: 'component-render', callee: m[1], openAt: m.index + m[0].length, isJsx: true })
    }
  }
  if (cands.length === 0) return referenceSite(rawLines, best.idx)

  cands.sort((a, b) => a.index - b.index)
  const pick = cands.find((c) => c.index >= anchorStart) ?? cands[0]
  const calleeBare = lastSegment(pick.callee)

  // 3. Read the full invocation.
  let closeIdx: number
  let rawArgs: { keyword: string | null; value: string | null; isProp: boolean }[]
  if (pick.isJsx) {
    const end = jsxTagEnd(masked, pick.openAt)
    if (end < 0) return referenceSite(rawLines, best.idx)
    const tag = masked.slice(pick.openAt, end)
    const selfClosing = /\/\s*$/.test(tag)
    closeIdx = end
    if (!selfClosing) {
      const closing = masked.indexOf(`</${calleeBare}`, end)
      if (closing > 0 && closing - end < 6000) {
        const gt = masked.indexOf('>', closing)
        closeIdx = gt > 0 ? gt : end
      }
    }
    rawArgs = splitJsxProps(tag.replace(/\/\s*$/, '')).map((p) => ({
      keyword: p.name,
      value: p.value === null ? null : unwrapBraces(p.value),
      isProp: true,
    }))
  } else {
    const close = scanBalanced(masked, pick.openAt)
    closeIdx = close < 0 ? Math.min(masked.length - 1, pick.openAt + 2000) : close
    const argsText = masked.slice(pick.openAt + 1, closeIdx)
    rawArgs = splitTop(argsText).map((item) => {
      if (ctx.hash) {
        const km = /^([A-Za-z_]\w*)\s*=(?!=)\s*([\s\S]+)$/.exec(item)
        if (km) return { keyword: km[1], value: km[2].trim(), isProp: false }
      }
      return { keyword: null, value: item.trim(), isProp: false }
    })
  }

  const startLine = lineOf(starts, pick.index)
  const endLine = lineOf(starts, closeIdx)
  const expression = masked.slice(pick.index, closeIdx + 1).replace(/\s*\n\s*/g, ' ').replace(/\s+/g, ' ')

  // 4. Assignment target (`x = f(`, `self.x = f(`, `return f(`).
  const prefix = masked.slice(starts[startLine - 1], pick.index).replace(/\bawait\s*$/, '')
  let assignedTo: string | null = null
  if (/\breturn\s*$/.test(prefix)) assignedTo = 'return'
  else {
    const am = /([A-Za-z_$][\w$.]*)\s*(?::[^=\n]+)?=\s*$/.exec(prefix)
    if (am) assignedTo = am[1]
  }

  // 5. Target signature and parameter binding.
  const signature =
    ctx.targetText !== null
      ? parseSignature(ctx.targetText, calleeBare, ctx.targetHash, pick.kind === 'class-instantiation')
      : null
  const params = signature?.params ?? []
  let positional = 0
  const args: PayloadField[] = rawArgs
    .filter((a) => a.value !== null || a.isProp)
    .map((a, i) => {
      const value = a.value ?? 'true'
      let name: string
      let param: SignatureParam | undefined
      let via: PayloadField['via']
      if (a.keyword !== null) {
        name = a.keyword
        param = params.find((p) => p.name === a.keyword)
        via = a.isProp ? 'prop' : 'keyword'
      } else {
        param = params[positional]
        name = param?.name ?? `arg${i + 1}`
        via = 'position'
        positional++
      }
      const cls = a.value === null ? { kind: 'boolean' as ValueKind, type: 'boolean' } : classifyValue(value)
      let type = cls.type
      let typeSource: TypeSource = 'literal'
      if (param?.type) {
        type = param.type
        typeSource = 'declared'
      } else if (cls.kind === 'identifier' || cls.kind === 'expression' || cls.kind === 'call') {
        const hint = guessType(name) !== 'unknown' ? guessType(name) : guessType(value)
        if (cls.kind === 'identifier' && hint !== 'unknown') {
          type = hint
          typeSource = 'inferred'
        } else {
          type = cls.kind === 'call' ? cls.type : 'unknown'
          typeSource = 'unknown'
        }
      }
      return { name, value, type, typeSource, via, matched: !!param }
    })

  const callee = pick.callee
  const invocation = expression
  const lines: CallSiteLine[] = []
  const from = Math.max(1, startLine - 2)
  const to = Math.min(rawLines.length, endLine + 2)
  for (let n = from; n <= to; n++) {
    lines.push({ n, text: rawLines[n - 1], hit: n >= startLine && n <= endLine })
  }

  return {
    line: startLine,
    endLine,
    kind: pick.kind,
    callee,
    invocation: invocation.length > 220 ? `${invocation.slice(0, 217)}...` : invocation,
    assignedTo,
    args,
    signature,
    lines,
    otherLines: [...new Set(cands.filter((c) => c !== pick).map((c) => lineOf(starts, c.index)))]
      .filter((n) => n !== startLine)
      .sort((a, b) => a - b),
  }
}

/** Fallback when the target is only mentioned (import, attribute access) and never invoked. */
function referenceSite(rawLines: string[], idx: number): CallSite {
  const from = Math.max(1, idx + 1 - 2)
  const to = Math.min(rawLines.length, idx + 1 + 2)
  const lines: CallSiteLine[] = []
  for (let n = from; n <= to; n++) lines.push({ n, text: rawLines[n - 1], hit: n === idx + 1 })
  return {
    line: idx + 1,
    endLine: idx + 1,
    kind: 'reference',
    callee: null,
    invocation: rawLines[idx].trim(),
    assignedTo: null,
    args: [],
    signature: null,
    lines,
    otherLines: [],
  }
}

/* ────────────────────────── edge record ────────────────────────── */

/** Build the full data-flow record for an edge. Source/target texts may be null when unavailable. */
export function buildEdgeDataFlow(
  graph: CopilotGraph,
  edge: GEdge,
  sourceText: string | null,
  targetText: string | null = null,
): EdgeDataFlow | null {
  const idx = getIndex(graph)
  const source = idx.byId.get(edge.source)
  const target = idx.byId.get(edge.target)
  if (!source || !target) return null

  const relationship = toRelationship(edge.relation)
  const bidirectional = (idx.out.get(target.id) ?? []).some((e) => e.target === source.id)
  const crossCluster = clusterKeyOf(source) !== clusterKeyOf(target)
  const inT = inDegree(graph, target.id)
  const outS = outDegree(graph, source.id)

  const relScore = relationship === 'FUNCTION_CALL' ? 1 : relationship === 'MODULE_IMPORT' ? 0.6 : 0.25
  const raw =
    0.35 * Math.min(1, pagerank(target) * 2) +
    0.25 * relScore +
    0.2 * (crossCluster ? 1 : 0.35) +
    0.2 * Math.min(1, inT / 8)
  const coupling = Math.round(raw * 100)
  const couplingBand: EdgeDataFlow['couplingBand'] = coupling >= 65 ? 'High' : coupling >= 40 ? 'Medium' : 'Low'
  const callFrequency: EdgeDataFlow['callFrequency'] = inT >= 5 ? 'High (Hot Path)' : inT >= 2 ? 'Medium' : 'Low'

  const symbols = targetSymbolsOf(graph, target)
  const hashSrc = isPythonPath(source.path)
  const hashTgt = isPythonPath(target.path)
  const imports = sourceText ? extractImports(sourceText, target, symbols, hashSrc) : []
  const callSite = sourceText
    ? findCallSite(sourceText, target, symbols, {
        hash: hashSrc,
        classNames: classNamesOf(graph, target),
        targetText,
        targetHash: hashTgt,
      })
    : null

  const relLabel = RELATION_LABEL[relationship]
  const verb = relationship === 'FUNCTION_CALL' ? 'calls into' : relationship === 'MODULE_IMPORT' ? 'imports' : 'is linked to'
  const callPart =
    callSite && callSite.kind !== 'reference' && callSite.callee
      ? ` The call is a ${KIND_LABEL[callSite.kind].toLowerCase()} of ${callSite.callee} with ${callSite.args.length} argument${callSite.args.length === 1 ? '' : 's'}.`
      : ''
  const summary =
    `${source.label} ${verb} ${target.label} (${relLabel.toLowerCase()})` +
    (crossCluster ? `, crossing from the ${clusterKeyOf(source)}/ module into ${clusterKeyOf(target)}/.` : '.') +
    callPart +
    (inT >= 3
      ? ` ${target.label} has ${inT} dependents, so changes to it ripple outward quickly.`
      : ` ${target.label} has ${inT} dependent${inT === 1 ? '' : 's'}.`)

  const failureMode =
    relationship === 'FUNCTION_CALL'
      ? `If ${target.label} raises or stalls, ${source.label} waits on it (synchronous call). ` +
        (outS > 1 ? `${source.label} has ${outS} outgoing dependencies, so the failure can stop the request path.` : 'The failure stays on this path.')
      : `If ${target.label} changes its exported names, ${source.label} breaks at import time, before any request runs.`

  return {
    edgeId: edge.id ?? `${edge.source}->${edge.target}`,
    source,
    target,
    relationship,
    relationshipLabel: relLabel,
    bidirectional,
    coupling,
    couplingBand,
    callFrequency,
    crossCluster,
    sourceCluster: clusterKeyOf(source),
    targetCluster: clusterKeyOf(target),
    outbound: callSite?.args ?? [],
    targetSymbols: symbols,
    imports,
    callSite,
    signature: callSite?.signature ?? null,
    sourceOrigin: sourceText === null ? 'unavailable' : 'live',
    targetOrigin: targetText === null ? 'unavailable' : 'live',
    summary,
    failureMode,
  }
}

/**
 * Read a file's source from the backend only. Returns null when the backend cannot serve it
 * (demo graphs and offline mode), so synthetic snippets are never shown as real code.
 */
export async function fetchLiveSource(repoId: string, filePath: string): Promise<string | null> {
  const base = (
    ((import.meta as any).env?.VITE_API_BASE_URL as string | undefined) ||
    ((import.meta as any).env?.VITE_API_URL as string | undefined) ||
    'http://127.0.0.1:8000'
  ).replace(/\/$/, '')
  try {
    const ctl = new AbortController()
    const t = setTimeout(() => ctl.abort(), 8000)
    const res = await fetch(`${base}/api/repositories/${encodeURIComponent(repoId)}/file?path=${encodeURIComponent(filePath)}`, {
      signal: ctl.signal,
    })
    clearTimeout(t)
    if (!res.ok) return null
    const data = await res.json()
    const text = data.content ?? (Array.isArray(data.lines) ? data.lines.join('\n') : null)
    return typeof text === 'string' ? text : null
  } catch {
    return null
  }
}
