/**
 * EdgeDataFlowInspector — right-hand panel opened when a dependency beam is clicked.
 * Shows the origin → destination pipeline, the imports that link the two files, the exact call
 * (function, class instantiation or JSX render), every argument / prop passed with its type,
 * the target's signature, the payload contract, and the AI flow summary with actions.
 */

import { useEffect, useMemo, useState } from 'react'
import type { CSSProperties } from 'react'
import { ArrowRight, ArrowLeftRight, Crosshair, FileCode, Link2, Radar, Sparkles, X } from 'lucide-react'
import { CopilotGraph, GEdge } from '../services/graphAnalysis'
import {
  KIND_LABEL,
  PayloadField,
  TargetSignature,
  buildEdgeDataFlow,
  fetchLiveSource,
} from '../services/edgeDataFlow'
import '../styles/edgeFlow.css'

export interface EdgeDataFlowInspectorProps {
  edge: GEdge
  graph: CopilotGraph
  repoId: string
  onClose: () => void
  onFocusNode: (id: string) => void
  onAskAstral: (text: string) => void
  onSimulateBreak: (sourceId: string) => void
}

const TYPE_BADGE = (n: { type?: string; language?: string | null; label: string }) => {
  if (n.type === 'class') return 'Class'
  if (n.type === 'function') return 'Function'
  if (n.type === 'directory') return 'Directory'
  if (/controller|router|route|api|handler|endpoint/i.test(n.label)) return 'Controller / File'
  if (/service/i.test(n.label)) return 'Service / File'
  return n.language ? `${n.language} module` : 'Module'
}

const SOURCE_LABEL: Record<PayloadField['typeSource'], string> = {
  declared: 'from signature',
  literal: 'literal',
  inferred: 'inferred from name',
  unknown: 'unresolved',
}

function signatureText(sig: TargetSignature): string {
  const params = sig.params.map((p) => `  ${p.name}${p.type ? `: ${p.type}` : ''}${p.defaultValue ? ` = ${p.defaultValue}` : ''}`)
  const head = `${sig.kind === 'class' ? 'class ' : ''}${sig.symbol}(`
  const body = params.length ? `\n${params.join(',\n')}\n` : ''
  const ret = sig.kind === 'class' ? '' : sig.returnType ? ` -> ${sig.returnType}` : ''
  return `${head}${body})${ret}`
}

function PayloadBlock({ title, fields, footer }: { title: string; fields: PayloadField[]; footer?: string }) {
  return (
    <div className="edf-block">
      <div className="edf-block__title">{title}</div>
      <pre className="edf-code">
        <code>
          {fields.length === 0
            ? '// no arguments detected at this call site'
            : '{\n' +
              fields
                .map((f) => `  ${f.name}: ${f.type}${f.typeSource === 'inferred' ? ' (inferred)' : ''},  // = ${f.value}`)
                .join('\n') +
              '\n}'}
          {footer ? `\n${footer}` : ''}
        </code>
      </pre>
    </div>
  )
}

export default function EdgeDataFlowInspector({
  edge,
  graph,
  repoId,
  onClose,
  onFocusNode,
  onAskAstral,
  onSimulateBreak,
}: EdgeDataFlowInspectorProps) {
  const [sourceText, setSourceText] = useState<string | null>(null)
  const [targetText, setTargetText] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  const { sourcePath, targetPath } = useMemo(() => {
    const s = graph.nodes.find((n) => n.id === edge.source)
    const t = graph.nodes.find((n) => n.id === edge.target)
    return { sourcePath: s?.path || null, targetPath: t?.path || null }
  }, [graph, edge.source, edge.target])

  useEffect(() => {
    let alive = true
    setLoaded(false)
    setSourceText(null)
    setTargetText(null)
    if (!repoId || (!sourcePath && !targetPath)) {
      setLoaded(true)
      return
    }
    Promise.all([
      sourcePath ? fetchLiveSource(repoId, sourcePath) : Promise.resolve(null),
      targetPath && targetPath !== sourcePath ? fetchLiveSource(repoId, targetPath) : Promise.resolve(undefined),
    ]).then(([src, tgt]) => {
      if (!alive) return
      setSourceText(src)
      // Same file on both ends: reuse the source text as the target text.
      setTargetText(tgt === undefined ? src : tgt)
      setLoaded(true)
    })
    return () => {
      alive = false
    }
  }, [sourcePath, targetPath, repoId])

  const flow = useMemo(
    () => buildEdgeDataFlow(graph, edge, sourceText, targetText),
    [graph, edge, sourceText, targetText],
  )

  if (!flow) {
    return (
      <aside className="workspace-drawer edf">
        <div className="edf-head">
          <span className="kicker-glow">GRAVITATIONAL DEPENDENCY BEAM</span>
          <button type="button" className="edf-close" onClick={onClose} aria-label="Close"><X size={16} /></button>
        </div>
        <p className="edf-muted">This beam's endpoints are not in the current graph.</p>
      </aside>
    )
  }

  const { source, target, callSite, imports, signature } = flow
  const bandColor = flow.couplingBand === 'High' ? '#fb923c' : flow.couplingBand === 'Medium' ? '#fdba74' : '#9ca3af'
  const hasCall = !!callSite && callSite.kind !== 'reference'
  const sourceUnavailable = flow.sourceOrigin === 'unavailable'

  return (
    <aside className="workspace-drawer edf" aria-label="Edge Data-Flow Inspector">
      {/* Header & relationship badge */}
      <div className="edf-head">
        <span className="kicker-glow">[ GRAVITATIONAL DEPENDENCY BEAM ]</span>
        <button type="button" className="edf-close" onClick={onClose} aria-label="Close inspector"><X size={16} /></button>
      </div>

      <div className="edf-badges">
        <span className="edf-pill">{flow.relationshipLabel}</span>
        <span className="edf-pill edf-pill--ghost">{flow.bidirectional ? 'Bidirectional' : 'Unidirectional'}</span>
        {callSite && <span className="edf-pill edf-pill--ghost">{KIND_LABEL[callSite.kind]}</span>}
      </div>

      <div className="edf-metrics">
        <div className="edf-metric" style={{ '--band': bandColor } as CSSProperties}>
          <span>Coupling</span>
          <strong>{flow.couplingBand} ({flow.coupling}%)</strong>
        </div>
        <div className="edf-metric">
          <span>Call frequency</span>
          <strong>{flow.callFrequency}</strong>
        </div>
        <div className="edf-metric">
          <span>Edge weight</span>
          <strong>{edge.weight ?? 1}</strong>
        </div>
      </div>

      {/* Vertical pipeline */}
      <div className="edf-pipeline">
        <div className="edf-card">
          <div className="edf-card__icon"><FileCode size={15} /></div>
          <div className="edf-card__body">
            <div className="edf-card__name">{source.label}</div>
            <span className="edf-tag">{TYPE_BADGE(source)}</span>
            <div className="edf-path">{source.path}{callSite ? `:L${callSite.line}` : ''}</div>
          </div>
          <button type="button" className="edf-focus" onClick={() => onFocusNode(source.id)}>
            Focus Source Star <Crosshair size={11} />
          </button>
        </div>

        <div className="edf-conduit">
          <div className="edf-conduit__line"><i /><i /><i /></div>
          <div className="edf-conduit__info">
            <code className="edf-invocation">
              {hasCall ? callSite!.invocation : `${flow.relationshipLabel.toLowerCase()} → ${target.label}`}
            </code>
            <span className="edf-direction">
              {flow.bidirectional ? <ArrowLeftRight size={12} /> : <ArrowRight size={12} />}
              {flow.bidirectional ? 'Bidirectional Request/Response (A ⇄ B)' : 'Unidirectional Flow (A → B)'}
            </span>
          </div>
        </div>

        <div className="edf-card">
          <div className="edf-card__icon"><Link2 size={15} /></div>
          <div className="edf-card__body">
            <div className="edf-card__name">{target.label}</div>
            <span className="edf-tag">{TYPE_BADGE(target)}</span>
            <div className="edf-path">{target.path}</div>
          </div>
          <button type="button" className="edf-focus" onClick={() => onFocusNode(target.id)}>
            Focus Target Star <Crosshair size={11} />
          </button>
        </div>
      </div>

      {/* Imports linking the two files */}
      <section className="edf-section">
        <div className="edf-section__title">Imports in {source.label}</div>
        {imports.length > 0 ? (
          imports.map((imp) => (
            <div className="edf-import" key={`${imp.line}-${imp.statement}`}>
              <div className="edf-import__head">L{imp.line} · module <code>{imp.moduleName}</code></div>
              <pre className="edf-code edf-code--site"><code>{imp.statement}</code></pre>
              <div className="edf-names">
                {imp.names.map((n) => (
                  <span className="edf-name" key={n}>{n}</span>
                ))}
              </div>
            </div>
          ))
        ) : (
          <p className="edf-muted">
            {sourceUnavailable
              ? `Live source for ${source.path} is not available from the backend, so imports are not shown.`
              : `No import statement in ${source.path} brings in ${target.label}. The link comes from the graph's ${flow.relationshipLabel.toLowerCase()} data.`}
          </p>
        )}
      </section>

      {/* The call itself */}
      <section className="edf-section">
        <div className="edf-section__title">Call-site in {source.label}</div>
        {!loaded ? (
          <p className="edf-muted">Reading source…</p>
        ) : callSite ? (
          <>
            <div className="edf-callhead">
              <span className="edf-kind">{KIND_LABEL[callSite.kind]}</span>
              {callSite.callee && <code className="edf-callee">{callSite.callee}</code>}
              {callSite.assignedTo && (
                <span className="edf-muted edf-assign">
                  {callSite.assignedTo === 'return' ? 'returned' : `assigned to ${callSite.assignedTo}`}
                </span>
              )}
              <span className="edf-muted">
                {callSite.endLine > callSite.line ? `lines ${callSite.line}–${callSite.endLine}` : `line ${callSite.line}`}
              </span>
            </div>
            <div className="edf-code edf-code--site">
              {callSite.lines.map((ln) => (
                <div key={ln.n} className={`edf-codeline ${ln.hit ? 'is-hit' : ''}`}>
                  <span className="edf-ln">{ln.n}</span>
                  <span>{ln.text || ' '}</span>
                </div>
              ))}
            </div>
            {callSite.otherLines.length > 0 && (
              <p className="edf-muted">
                Also used in {source.label} at line{callSite.otherLines.length > 1 ? 's' : ''} {callSite.otherLines.join(', ')}.
              </p>
            )}
          </>
        ) : (
          <p className="edf-muted">
            {sourceUnavailable
              ? `Live source for ${source.path} is not available from the backend, so no call-site is shown.`
              : `No line in ${source.path} calls or renders ${target.label}.`}
          </p>
        )}
      </section>

      {/* Parameters and props passed */}
      {callSite && callSite.kind !== 'reference' && (
        <section className="edf-section">
          <div className="edf-section__title">
            {callSite.kind === 'component-render' ? 'Props passed' : 'Arguments passed'} ({callSite.args.length})
          </div>
          {callSite.args.length === 0 ? (
            <p className="edf-muted">
              {callSite.kind === 'component-render' ? 'No props on this element.' : 'Called with no arguments.'}
            </p>
          ) : (
            <table className="edf-tbl">
              <thead>
                <tr>
                  <th>{callSite.kind === 'component-render' ? 'Prop' : 'Parameter'}</th>
                  <th>Value passed</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {callSite.args.map((a, i) => (
                  <tr key={`${a.name}-${i}`}>
                    <td>
                      <code>{a.name}</code>
                      <div className="edf-via">{a.matched ? 'signature' : a.via === 'position' ? `position ${i + 1}` : a.via}</div>
                    </td>
                    <td><code>{a.value}</code></td>
                    <td>
                      <code>{a.type}</code>
                      <span className={`edf-src edf-src--${a.typeSource}`}>{SOURCE_LABEL[a.typeSource]}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {callSite.kind === 'class-instantiation' && (
            <p className="edf-muted">
              Creates an object of class {callSite.callee}
              {callSite.assignedTo && callSite.assignedTo !== 'return' ? `, bound to ${callSite.assignedTo}` : ''}.
            </p>
          )}
        </section>
      )}

      {/* Target signature */}
      <section className="edf-section">
        <div className="edf-section__title">Signature in {target.label}</div>
        {signature ? (
          <pre className="edf-code edf-code--site"><code>{signatureText(signature)}</code></pre>
        ) : targetText === null && flow.targetOrigin === 'unavailable' ? (
          <p className="edf-muted">Live source for {target.path} is not available, so the parameter list cannot be read.</p>
        ) : hasCall ? (
          <p className="edf-muted">
            {callSite?.callee ?? target.label} is not defined in {target.path}, so the arguments are numbered by position.
          </p>
        ) : (
          <p className="edf-muted">No call found, so there is no signature to match.</p>
        )}
      </section>

      {/* Payload contract */}
      <section className="edf-section">
        <div className="edf-section__title">Data payload & parameter contract</div>
        <PayloadBlock
          title={`1. Outbound payload (${source.label} → ${target.label})`}
          fields={flow.outbound}
          footer={flow.outbound.some((f) => f.typeSource === 'inferred') ? '// types inferred from argument names' : undefined}
        />
        <div className="edf-block">
          <div className="edf-block__title">2. Return / response stream ({target.label} → {source.label})</div>
          <pre className="edf-code">
            <code>
              {signature?.returnType
                ? `// returns: ${signature.returnType}  (declared)`
                : flow.targetSymbols.length
                  ? `// exposes: ${flow.targetSymbols.map((s) => `${s}()`).join(', ')}\n// return type not declared in ${target.path}`
                  : `// no exported symbols found; return type not statically resolved`}
              {callSite?.assignedTo && callSite.assignedTo !== 'return' ? `\n// received into ${callSite.assignedTo}` : ''}
            </code>
          </pre>
        </div>
      </section>

      {/* AI insight & actions */}
      <section className="edf-section">
        <div className="edf-ai">
          <div className="edf-ai__title"><Sparkles size={12} /> AI flow summary</div>
          <p>{flow.summary}</p>
          <p className="edf-ai__risk"><strong>Failure mode (inferred):</strong> {flow.failureMode}</p>
        </div>
        <div className="edf-actions">
          <button
            type="button"
            className="edf-btn edf-btn--primary"
            onClick={() =>
              onAskAstral(
                `Trace the full upstream and downstream path through the dependency [[${source.label}]] → [[${target.label}]]. Show where this edge sits in the request flow, and what breaks if it fails.`,
              )
            }
          >
            <Sparkles size={13} /> Ask Astral AI to Trace Full Path
          </button>
          <button type="button" className="edf-btn" onClick={() => onSimulateBreak(source.id)}>
            <Radar size={13} /> Simulate Breaking This Edge
          </button>
        </div>
      </section>
    </aside>
  )
}
