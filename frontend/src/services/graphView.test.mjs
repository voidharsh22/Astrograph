// Run with: node --test src/services/graphView.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeGraphData } from './graphNormalizer.js';
import { applyFilters, DEFAULT_FILTERS, findPath, isolate, trace, unresolvedFileIds } from './graphView.js';

// Shaped exactly like the backend GraphResponse (ids "file:<path>", edge.type, edge.metadata).
const raw = {
  repository_id: 'repo_x',
  repo_name: 'x',
  nodes: [
    { id: 'repository:x', type: 'repository', name: 'x', label: 'x', metadata: {} },
    { id: 'directory:src', type: 'directory', name: 'src', label: 'src', metadata: { path: 'src' } },
    ...['src/a.js', 'src/b.js', 'src/c.js', 'lib/d.py'].map((p) => ({
      id: `file:${p}`, type: 'file', name: p.split('/').pop(), label: p, metadata: { path: p, language: p.endsWith('.py') ? 'Python' : 'JavaScript' },
    })),
    { id: 'symbol:src/c.js::f:function:1', type: 'function', name: 'f', label: 'f', metadata: { file_path: 'src/c.js', path: 'src/c.js', language: 'JavaScript', lineno: 1, end_lineno: 3 } },
  ],
  edges: [
    { id: 'e1', source: 'file:src/a.js', target: 'file:src/b.js', type: 'IMPORTS', metadata: { line: 2, module: './b', resolution_status: 'resolved' } },
    { id: 'e2', source: 'file:src/b.js', target: 'file:src/c.js', type: 'IMPORTS', metadata: { line: 1 } },
    { id: 'e3', source: 'file:src/a.js', target: 'file:src/c.js', type: 'CALLS', metadata: { lines: [9] } },
    { id: 'e4', source: 'directory:src', target: 'file:src/a.js', type: 'CONTAINS', metadata: {} },
    { id: 'e5', source: 'file:src/c.js', target: 'symbol:src/c.js::f:function:1', type: 'DEFINES', metadata: {} },
  ],
  unresolved_references: [{ kind: 'import', status: 'unresolved', source_file: 'src/b.js', target_name: './nope', lineno: 5 }],
};
const g = normalizeGraphData(raw);

test('normalizer keeps parser edge direction, ids and metadata; drops directory endpoints', () => {
  const e1 = g.edges.find((e) => e.id === 'e1');
  assert.equal(e1.source, 'file:src/a.js');
  assert.equal(e1.target, 'file:src/b.js');
  assert.deepEqual(e1.lines, [2]);
  assert.equal(e1.relation, 'imports');
  assert.ok(!g.edges.some((e) => e.id === 'e4'), 'directory containment edge must not survive');
  assert.ok(g.nodes.every((n) => n.type !== 'directory' && n.type !== 'repository'));
  assert.equal(g.repository_id, 'repo_x');
});

test('normalizer does not invent metrics', () => {
  const n = g.nodes.find((x) => x.id === 'file:src/a.js');
  assert.equal(n.metrics.loc, null);
  assert.equal(n.metrics.centrality, null);
  assert.equal(n.language, 'javascript');
});

test('default filters show dependency edges only and file nodes only', () => {
  const v = applyFilters(g, DEFAULT_FILTERS);
  assert.deepEqual(v.edges.map((e) => e.id).sort(), ['e1', 'e2', 'e3']);
  assert.ok(v.nodes.every((n) => n.type === 'file'));
});

test('relation, language and directory filters', () => {
  const importsOnly = applyFilters(g, { ...DEFAULT_FILTERS, relations: { imports: true, calls: false, structural: false } });
  assert.deepEqual(importsOnly.edges.map((e) => e.id).sort(), ['e1', 'e2']);
  const py = applyFilters(g, { ...DEFAULT_FILTERS, language: 'python' });
  assert.deepEqual(py.nodes.map((n) => n.id), ['file:lib/d.py']);
  const lib = applyFilters(g, { ...DEFAULT_FILTERS, directory: 'lib' });
  assert.equal(lib.nodes.length, 1);
});

test('unresolved filter lists files with unresolved internal imports', () => {
  assert.deepEqual([...unresolvedFileIds(g)], ['file:src/b.js']);
  assert.deepEqual(applyFilters(g, { ...DEFAULT_FILTERS, unresolvedOnly: true }).nodes.map((n) => n.id), ['file:src/b.js']);
});

test('downstream and upstream tracing follow edge direction', () => {
  const down = trace(g, 'file:src/a.js', 'downstream');
  assert.deepEqual(down.nodeIds.sort(), ['file:src/a.js', 'file:src/b.js', 'file:src/c.js']);
  const up = trace(g, 'file:src/c.js', 'upstream');
  assert.deepEqual(up.nodeIds.sort(), ['file:src/a.js', 'file:src/b.js', 'file:src/c.js']);
  assert.deepEqual(trace(g, 'file:src/a.js', 'upstream').nodeIds, ['file:src/a.js']);
  assert.equal(trace(g, 'file:src/a.js', 'downstream', 1).depth.get('file:src/c.js'), 1);
});

test('isolate returns only the immediate neighborhood', () => {
  const iso = isolate(g, 'file:src/b.js');
  assert.deepEqual(iso.nodeIds.sort(), ['file:src/a.js', 'file:src/b.js', 'file:src/c.js']);
  assert.deepEqual(iso.edgeIds.sort(), ['e1', 'e2']);
});

test('path finding is directed and shortest', () => {
  const p = findPath(g, 'file:src/a.js', 'file:src/c.js');
  assert.deepEqual(p.nodeIds, ['file:src/a.js', 'file:src/c.js']); // direct CALLS edge beats a->b->c
  assert.equal(findPath(g, 'file:src/c.js', 'file:src/a.js'), null);
  assert.equal(findPath(g, 'file:src/a.js', 'file:lib/d.py'), null);
});
