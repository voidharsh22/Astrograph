import { useCallback, useEffect, useMemo, useState } from 'react';
import { Wrench, X, RotateCcw, ArrowUpFromLine, ArrowDownToLine, Route, Crosshair, Sparkles, ShieldAlert, Compass, BookOpen, Stethoscope, Search } from 'lucide-react';
import { aiApi } from '../services/astralAiService.ts';
import {
  DEFAULT_FILTERS,
  RELATION_STYLES,
  directoriesOf,
  findPath,
  isolate,
  languagesOf,
  trace,
  unresolvedFileIds,
} from '../services/graphView.js';
import '../styles/graphTools.css';

const FILE_REF = /`([\w@./-]+\.[A-Za-z0-9]+)(?::(\d+)(?:-\d+)?)?`/g;

/** Minimal markdown: headings, bullets, fenced code, bold, inline code; `path:line` becomes a clickable file link. */
function Md({ text, onOpenPath }) {
  const blocks = String(text || '').split(/```/);
  return (
    <div className="gt-md">
      {blocks.map((chunk, i) => {
        if (i % 2 === 1) return <pre key={i}><code>{chunk.replace(/^\w*\n/, '')}</code></pre>;
        return chunk.split('\n').map((line, j) => {
          if (!line.trim()) return null;
          const heading = /^(#{1,4})\s+(.*)/.exec(line);
          const bullet = /^\s*[-*]\s+(.*)|^\s*\d+\.\s+(.*)/.exec(line);
          const body = heading ? heading[2] : bullet ? bullet[1] || bullet[2] : line;
          const parts = [];
          let last = 0;
          let k = 0;
          const re = new RegExp(`${FILE_REF.source}|\\*\\*([^*]+)\\*\\*|\`([^\`]+)\``, 'g');
          for (const m of body.matchAll(re)) {
            if (m.index > last) parts.push(body.slice(last, m.index));
            if (m[1]) parts.push(<button key={k++} type="button" className="gt-fileref" onClick={() => onOpenPath(m[1])}>{m[1]}{m[2] ? `:${m[2]}` : ''}</button>);
            else if (m[3]) parts.push(<strong key={k++}>{m[3]}</strong>);
            else parts.push(<code key={k++}>{m[4]}</code>);
            last = m.index + m[0].length;
          }
          if (last < body.length) parts.push(body.slice(last));
          const key = `${i}-${j}`;
          if (heading) return <h4 key={key}>{parts}</h4>;
          if (bullet) return <p key={key} className="gt-li">• {parts}</p>;
          return <p key={key}>{parts}</p>;
        });
      })}
    </div>
  );
}

function ErrorBox({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="gt-error" role="alert">
      <strong>{error.code ? error.code.replace(/_/g, ' ') : 'Error'}</strong>
      <p>{error.message}</p>
      {onRetry && error.retryable !== false && <button type="button" onClick={onRetry}>Retry</button>}
    </div>
  );
}

function useAsync() {
  const [state, setState] = useState({ loading: false, error: null, data: null });
  const run = useCallback(async (fn) => {
    setState({ loading: true, error: null, data: null });
    try {
      setState({ loading: false, error: null, data: await fn() });
    } catch (e) {
      setState({ loading: false, error: { code: e.code, message: e.message, retryable: e.retryable }, data: null });
    }
  }, []);
  return [state, run];
}

export default function GraphToolsPanel({
  repoId,
  graph,
  viewGraph,
  filters,
  setFilters,
  selectedNodeId,
  isolated,
  setIsolated,
  showEdgeLabels,
  setShowEdgeLabels,
  onHighlight, // ({nodeIds, edgeIds, label, kind, sourceId, depths})
  onClearHighlight,
  onResetView,
  onOpenPath, // (path) => select + reveal in explorer
  diagnostics,
  diagnosticsError,
  aiStatus,
  open,
  onToggle,
}) {
  const [tab, setTab] = useState('explore');
  const selected = useMemo(() => graph?.nodes.find((n) => n.id === selectedNodeId) || null, [graph, selectedNodeId]);
  const dirs = useMemo(() => directoriesOf(graph), [graph]);
  const langs = useMemo(() => languagesOf(graph), [graph]);
  const unresolved = useMemo(() => (graph?.unresolved_references || []).filter((u) => u.kind === 'import' && u.status === 'unresolved'), [graph]);

  const [depth, setDepth] = useState(4);
  const [pathTarget, setPathTarget] = useState('');
  const [pathMsg, setPathMsg] = useState('');
  const [query, setQuery] = useState('');
  const [queryState, runQuery] = useAsync();
  const [archState, runArch] = useAsync();
  const [onbState, runOnb] = useAsync();
  const [healthState, runHealth] = useAsync();
  const [impactState, runImpact] = useAsync();
  const [adviceState, runAdvice] = useAsync();
  const [nodeAdvice, runNodeAdvice] = useAsync();
  const [focus, setFocus] = useState('responsibility');
  const aiReady = Boolean(aiStatus?.configured);

  useEffect(() => {
    setPathMsg('');
  }, [selectedNodeId]);

  const fileTargets = useMemo(() => (graph?.nodes || []).filter((n) => n.type === 'file' && n.id !== selectedNodeId).slice(0, 800), [graph, selectedNodeId]);

  const doTrace = (direction) => {
    if (!selected || !graph) return;
    const r = trace(graph, selected.id, direction, depth);
    onHighlight({ nodeIds: r.nodeIds, edgeIds: r.edgeIds, kind: 'set', label: `${direction === 'upstream' ? 'Upstream of' : 'Downstream of'} ${selected.label} (${r.nodeIds.length - 1})` });
  };

  const doPath = () => {
    if (!selected || !pathTarget || !graph) return;
    const r = findPath(graph, selected.id, pathTarget);
    if (!r) {
      setPathMsg(`No directed dependency path from ${selected.path} to ${graph.nodes.find((n) => n.id === pathTarget)?.path}.`);
      onClearHighlight();
      return;
    }
    setPathMsg(`${r.nodeIds.length - 1} hop(s).`);
    onHighlight({ nodeIds: r.nodeIds, edgeIds: r.edgeIds, kind: 'path', label: `Path ${selected.label} → ${graph.nodes.find((n) => n.id === pathTarget)?.label}` });
  };

  const setRel = (key, value) => setFilters({ ...filters, relations: { ...filters.relations, [key]: value } });

  const doImpact = () => selected && runImpact(async () => {
    const res = await aiApi.impactFacts(repoId, selected.id);
    onHighlight({
      kind: 'impact',
      sourceId: selected.id,
      depths: [...res.direct_dependents, ...res.transitive_dependents].map((d) => ({ id: d.id, depth: d.depth })),
      nodeIds: res.affected_node_ids,
      edgeIds: res.affected_edge_ids,
      label: `Impact of ${selected.label}`,
    });
    return res;
  });

  if (!open) {
    return (
      <button type="button" className="gt-launcher" onClick={onToggle} aria-label="Open graph tools" title="Graph tools">
        <Wrench size={16} /> Graph tools
      </button>
    );
  }

  return (
    <aside className="gt-panel" aria-label="Graph tools">
      <header className="gt-head">
        <nav className="gt-tabs">
          {[['explore', Compass, 'Explore'], ['insights', Sparkles, 'AI insights'], ['health', Stethoscope, 'Health'], ['parser', ShieldAlert, 'Parser']].map(([id, Icon, label]) => (
            <button key={id} type="button" className={tab === id ? 'is-active' : ''} onClick={() => setTab(id)}><Icon size={13} /> {label}</button>
          ))}
        </nav>
        <button type="button" className="gt-icon" onClick={onToggle} aria-label="Close graph tools"><X size={15} /></button>
      </header>

      <div className="gt-body">
        {tab === 'explore' && (
          <>
            <section>
              <h5>Relationships</h5>
              {['imports', 'calls', 'extends', 'implements', 'renders'].map((k) => (
                <label key={k} className="gt-check">
                  <input type="checkbox" checked={filters.relations[k]} onChange={(e) => setRel(k, e.target.checked)} />
                  <span style={{ color: RELATION_STYLES[k].color }}>{RELATION_STYLES[k].dash === 'solid' ? '━━▶' : RELATION_STYLES[k].dash === 'dotted' ? '┄┄▶' : '╌╌▶'}</span> {RELATION_STYLES[k].label}
                  <small>{RELATION_STYLES[k].description}</small>
                </label>
              ))}
              <label className="gt-check">
                <input type="checkbox" checked={filters.relations.structural} onChange={(e) => setRel('structural', e.target.checked)} />
                Structural (defines / contains)<small>Includes symbol nodes</small>
              </label>
              <label className="gt-check">
                <input type="checkbox" checked={showEdgeLabels} onChange={(e) => setShowEdgeLabels(e.target.checked)} /> Edge labels
              </label>
            </section>

            <section className="gt-row">
              <label>Language
                <select value={filters.language} onChange={(e) => setFilters({ ...filters, language: e.target.value })}>
                  <option value="all">All</option>{langs.map((l) => <option key={l} value={l}>{l}</option>)}
                </select>
              </label>
              <label>Directory
                <select value={filters.directory} onChange={(e) => setFilters({ ...filters, directory: e.target.value })}>
                  <option value="all">All</option>{dirs.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </label>
            </section>

            <label className="gt-check">
              <input type="checkbox" checked={filters.unresolvedOnly} onChange={(e) => setFilters({ ...filters, unresolvedOnly: e.target.checked })} />
              Only files with unresolved internal imports ({unresolvedFileIds(graph || { nodes: [] }).size})
            </label>

            <section>
              <h5>Selected: {selected ? selected.path : 'none — click a node'}</h5>
              <div className="gt-row">
                <label>Depth <input type="number" min="1" max="10" value={depth} onChange={(e) => setDepth(Math.max(1, Math.min(10, Number(e.target.value) || 1)))} /></label>
              </div>
              <div className="gt-btns">
                <button type="button" disabled={!selected} onClick={() => doTrace('upstream')} title="Files that depend on the selection"><ArrowUpFromLine size={13} /> Upstream</button>
                <button type="button" disabled={!selected} onClick={() => doTrace('downstream')} title="Files the selection depends on"><ArrowDownToLine size={13} /> Downstream</button>
                <button type="button" disabled={!selected} className={isolated ? 'is-on' : ''} onClick={() => setIsolated(!isolated)}><Crosshair size={13} /> {isolated ? 'Show all' : 'Isolate'}</button>
              </div>
              <div className="gt-row">
                <select value={pathTarget} onChange={(e) => setPathTarget(e.target.value)} aria-label="Path target">
                  <option value="">Path to…</option>{fileTargets.map((n) => <option key={n.id} value={n.id}>{n.path}</option>)}
                </select>
                <button type="button" disabled={!selected || !pathTarget} onClick={doPath}><Route size={13} /> Trace path</button>
              </div>
              {pathMsg && <p className="gt-note">{pathMsg}</p>}
            </section>

            <section>
              <h5>Ask the graph</h5>
              <div className="gt-row">
                <input value={query} placeholder='e.g. "files connected to authentication"' onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && query.trim() && runQuery(async () => {
                    const r = await aiApi.graphQuery(repoId, query.trim());
                    if (r.node_ids.length) onHighlight({ nodeIds: r.node_ids, edgeIds: r.edge_ids, kind: 'set', label: `Query: ${query.trim()}` });
                    return r;
                  })} />
                <button type="button" disabled={!aiReady || !query.trim() || queryState.loading} onClick={() => runQuery(async () => {
                  const r = await aiApi.graphQuery(repoId, query.trim());
                  if (r.node_ids.length) onHighlight({ nodeIds: r.node_ids, edgeIds: r.edge_ids, kind: 'set', label: `Query: ${query.trim()}` });
                  return r;
                })}><Search size={13} /> Run</button>
              </div>
              {!aiReady && <p className="gt-note">AI unavailable: {aiStatus?.reason}</p>}
              {queryState.loading && <p className="gt-note">Interpreting request…</p>}
              <ErrorBox error={queryState.error} />
              {queryState.data && (
                <p className="gt-note">
                  {queryState.data.needs_clarification || `${queryState.data.explanation}. ${queryState.data.node_ids.length} nodes highlighted (validated query, executed on the parsed graph).`}
                </p>
              )}
            </section>

            {unresolved.length > 0 && (
              <section>
                <h5>Unresolved internal imports ({unresolved.length})</h5>
                <p className="gt-note">Not drawn as edges: the parser could not find these targets.</p>
                <ul className="gt-list">
                  {unresolved.slice(0, 50).map((u, i) => (
                    <li key={i}><button type="button" className="gt-fileref" onClick={() => onOpenPath(u.source_file)}>{u.source_file}{u.lineno ? `:${u.lineno}` : ''}</button> → <code>{u.target_name}</code></li>
                  ))}
                </ul>
              </section>
            )}

            <div className="gt-btns">
              <button type="button" onClick={() => { onClearHighlight(); setPathMsg(''); }}><RotateCcw size={13} /> Reset selection</button>
              <button type="button" onClick={onResetView}>Reset camera</button>
            </div>
            <p className="gt-note">Showing {viewGraph?.nodes.length ?? 0} nodes, {viewGraph?.edges.length ?? 0} edges.</p>
          </>
        )}

        {tab === 'insights' && (
          <>
            {!aiReady && <div className="gt-error" role="alert"><strong>AI unavailable</strong><p>{aiStatus?.reason}</p></div>}
            <section>
              <h5>Change impact {selected ? `— ${selected.label}` : ''}</h5>
              <button type="button" disabled={!selected || impactState.loading} onClick={doImpact}>Show confirmed dependents on graph</button>
              <ErrorBox error={impactState.error} />
              {impactState.data && (
                <div>
                  <p className="gt-badge gt-badge--fact">Verified graph relationships</p>
                  <p className="gt-note">{impactState.data.counts.direct} direct, {impactState.data.counts.transitive} transitive dependents. {impactState.data.basis}</p>
                  <ul className="gt-list">
                    {impactState.data.direct_dependents.slice(0, 15).map((d) => (
                      <li key={d.id}><button type="button" className="gt-fileref" onClick={() => onOpenPath(d.path)}>{d.path}</button> <small>{d.kinds.join('/')}{d.lines?.length ? ` L${d.lines.slice(0, 3).join(',')}` : ''}</small></li>
                    ))}
                  </ul>
                  <button type="button" disabled={!aiReady || adviceState.loading} onClick={() => runAdvice(async () => aiApi.impactAssessment(repoId, selected.id))}>Ask AI for a risk assessment</button>
                  {adviceState.loading && <p className="gt-note">Assessing…</p>}
                  <ErrorBox error={adviceState.error} />
                  {adviceState.data?.assessment && (<><p className="gt-badge gt-badge--ai">AI assessment (not verified)</p><Md text={adviceState.data.assessment} onOpenPath={onOpenPath} /></>)}
                </div>
              )}
            </section>

            <section>
              <h5>Debug / refactor advice {selected ? `— ${selected.label}` : ''}</h5>
              <div className="gt-row">
                <select value={focus} onChange={(e) => setFocus(e.target.value)}>
                  <option value="responsibility">Responsibility</option><option value="maintainability">Maintainability issues</option>
                  <option value="refactor">Refactoring opportunities</option><option value="tests">Tests to add/inspect</option><option value="review">Review before changing</option>
                </select>
                <button type="button" disabled={!aiReady || !selected || nodeAdvice.loading} onClick={() => runNodeAdvice(() => aiApi.advice(repoId, selected.id, focus))}>Advise</button>
              </div>
              {nodeAdvice.loading && <p className="gt-note">Reading source and graph context…</p>}
              <ErrorBox error={nodeAdvice.error} />
              {nodeAdvice.data && (<><p className="gt-badge gt-badge--ai">AI suggestion — advisory only, nothing is modified</p><Md text={nodeAdvice.data.advice} onOpenPath={onOpenPath} /></>)}
            </section>

            <section>
              <h5>Architecture overview</h5>
              <div className="gt-btns">
                <button type="button" disabled={!aiReady || archState.loading} onClick={() => runArch(() => aiApi.architecture(repoId, false))}>Generate</button>
                <button type="button" disabled={!aiReady || archState.loading} onClick={() => runArch(() => aiApi.architecture(repoId, true))}>Regenerate</button>
              </div>
              {archState.loading && <p className="gt-note">Generating from parsed facts…</p>}
              <ErrorBox error={archState.error} />
              {archState.data && (
                <>
                  <p className="gt-badge gt-badge--fact">Parser facts</p>
                  <p className="gt-note">{archState.data.facts.modules.length} top-level modules, {archState.data.facts.entry_points.length} entry points, {archState.data.facts.external_packages.length} external packages, {archState.data.facts.cycles.length} cycles.</p>
                  <p className="gt-badge gt-badge--ai">AI narrative {archState.data.cached ? '(cached for this analysis)' : ''}</p>
                  <Md text={archState.data.narrative} onOpenPath={onOpenPath} />
                </>
              )}
            </section>

            <section>
              <h5>Reading path for new contributors</h5>
              <button type="button" disabled={!aiReady || onbState.loading} onClick={() => runOnb(() => aiApi.onboarding(repoId))}><BookOpen size={13} /> Build reading path</button>
              <ErrorBox error={onbState.error} />
              {onbState.data && (
                <>
                  {onbState.data.overview && <p>{onbState.data.overview}</p>}
                  {onbState.data.note && <p className="gt-note">{onbState.data.note}</p>}
                  <ol className="gt-steps">
                    {onbState.data.steps.map((s) => (
                      <li key={s.node_id}>
                        <button type="button" className="gt-fileref" onClick={() => onOpenPath(s.path)}>{s.path}</button>
                        <small className="gt-fact">Fact: {s.evidence}</small>
                        {s.why && <span className="gt-ai">AI: {s.why} {s.look_for && `Look for: ${s.look_for}`}</span>}
                        {s.prerequisites.length > 0 && <small>Depends on: {s.prerequisites.join(', ')}</small>}
                      </li>
                    ))}
                  </ol>
                </>
              )}
            </section>
          </>
        )}

        {tab === 'health' && (
          <section>
            <button type="button" disabled={healthState.loading} onClick={() => runHealth(() => aiApi.health(repoId))}>Compute architecture health</button>
            <ErrorBox error={healthState.error} />
            {healthState.data && (
              <>
                <p className="gt-badge gt-badge--fact">Deterministic metrics — not security findings</p>
                <p className="gt-note">{Object.entries(healthState.data.counts).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`).join(' · ') || 'No findings.'}</p>
                <ul className="gt-findings">
                  {healthState.data.findings.slice(0, 60).map((f) => (
                    <li key={f.id} className={`sev-${f.severity}`}>
                      <strong>{f.title}</strong>
                      <small>Rule: {f.rule}</small>
                      <div className="gt-btns">
                        {f.node_ids.length > 0 && <button type="button" onClick={() => onHighlight({ nodeIds: f.node_ids, edgeIds: [], kind: 'set', label: f.title })}>Show on graph</button>}
                        {f.paths.slice(0, 3).map((p) => <button key={p} type="button" className="gt-fileref" onClick={() => onOpenPath(p)}>{p}</button>)}
                      </div>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
        )}

        {tab === 'parser' && (
          <section>
            {diagnosticsError && <div className="gt-error"><p>{diagnosticsError}</p></div>}
            {!diagnostics && !diagnosticsError && <p className="gt-note">No diagnostics for this graph (demo data has none).</p>}
            {diagnostics && (
              <>
                <p className={`gt-badge ${diagnostics.status === 'complete' ? 'gt-badge--fact' : 'gt-badge--warn'}`}>Analysis {diagnostics.status}</p>
                <table className="gt-table"><tbody>
                  <tr><td>Files discovered</td><td>{diagnostics.files.discovered}</td></tr>
                  <tr><td>Parsed successfully</td><td>{diagnostics.files.parsed_successfully} / {diagnostics.files.parseable_discovered}</td></tr>
                  <tr><td>With syntax errors</td><td>{diagnostics.files.with_syntax_errors}</td></tr>
                  <tr><td>Unsupported files</td><td>{diagnostics.files.unsupported}</td></tr>
                  <tr><td>Skipped (sensitive/symlink/…)</td><td>{diagnostics.files.skipped?.total ?? 0}</td></tr>
                  <tr><td>Symbols extracted</td><td>{diagnostics.symbols.extracted}</td></tr>
                  <tr><td>Imports resolved</td><td>{diagnostics.dependencies.imports_resolved}</td></tr>
                  <tr><td>External packages</td><td>{diagnostics.dependencies.imports_external}</td></tr>
                  <tr><td>Unresolved internal imports</td><td>{diagnostics.dependencies.imports_unresolved}</td></tr>
                  <tr><td>Calls resolved / ambiguous / unresolved</td><td>{diagnostics.dependencies.calls_resolved} / {diagnostics.dependencies.calls_ambiguous} / {diagnostics.dependencies.calls_unresolved}</td></tr>
                  <tr><td>Parsing duration</td><td>{diagnostics.timings_ms.total} ms</td></tr>
                </tbody></table>
                {diagnostics.warnings.map((w, i) => <p key={i} className="gt-note">⚠ {w}</p>)}
                {diagnostics.syntax_errors.length > 0 && (
                  <ul className="gt-list">{diagnostics.syntax_errors.map((e) => (
                    <li key={e.file_path}><button type="button" className="gt-fileref" onClick={() => onOpenPath(e.file_path)}>{e.file_path}</button> <small>{e.errors[0]?.message}</small></li>
                  ))}</ul>
                )}
              </>
            )}
          </section>
        )}
      </div>
    </aside>
  );
}

