// Service layer for workspace, indexing, graph data, and AI interactions.
// Supports both live FastAPI backend and offline fallback mode with normalized mock dataset.

import { normalizeGraphData } from '../services/graphNormalizer.js';
import { DEMO_GRAPH } from '../demo/demoGraph.js';

const BASE = (
  (typeof import.meta !== "undefined" &&
    (import.meta.env?.VITE_API_BASE_URL || import.meta.env?.VITE_API_URL)) ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");

/**
 * Fetch repository graph:
 * - Checks live backend (/api/repositories/{id}/graph or /api/v1/...) with an 800ms timeout
 * - If backend is offline or slow, falls back seamlessly to the rich normalized MOCK_GRAPH
 * - Ensures Workspace NEVER gets stuck loading!
 */
export async function getRepositoryGraph(repoIdOrUrl, options = {}) {
  const isExplicitDemo = repoIdOrUrl === 'cosmic-weather-api' || options?.isDemo;
  if (isExplicitDemo || !repoIdOrUrl) {
    return normalizeGraphData({
      ...DEMO_GRAPH,
      is_demo: true,
    });
  }

  const candidateUrls = [
    `${BASE}/api/repositories/${encodeURIComponent(repoIdOrUrl)}/graph`,
    `${BASE}/api/v1/repositories/${encodeURIComponent(repoIdOrUrl)}/graph`,
  ];

  let lastError = null;
  for (const url of candidateUrls) {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 15000);
      const res = await fetch(url, {
        headers: { Accept: 'application/json' },
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const liveData = await res.json();
        return normalizeGraphData({
          ...liveData,
          is_demo: false,
        });
      } else {
        const errJson = await res.json().catch(() => ({}));
        const err = new Error(
          errJson.detail || `Server returned ${res.status}: Failed to load graph`
        );
        err.status = res.status;
        lastError = err;
      }
    } catch (networkErr) {
      if (networkErr.name === 'AbortError') {
        lastError = new Error('Graph fetch request timed out after 15 seconds');
      } else {
        lastError = new Error(
          `Cannot connect to Astrograph backend at ${BASE}. Ensure server is running.`
        );
      }
    }
  }

  throw (
    lastError ||
    new Error(`Repository '${repoIdOrUrl}' graph could not be loaded`)
  );
}

async function readError(res, fallback) {
  const body = await res.json().catch(() => ({}));
  const d = body.detail;
  return new Error(typeof d === 'string' ? d : d?.message || `${fallback} (HTTP ${res.status})`);
}

function backendDown() {
  return new Error(`Cannot connect to the Astrograph backend at ${BASE}. Ensure the server is running.`);
}

/** Read source file content from the backend. Throws on failure; never returns invented source. */
export async function getSourceFileContent(repoId, filePath) {
  let res;
  try {
    res = await fetch(`${BASE}/api/repositories/${encodeURIComponent(repoId)}/file?path=${encodeURIComponent(filePath)}`);
  } catch {
    throw backendDown();
  }
  if (!res.ok) throw await readError(res, 'Could not read source file');
  const data = await res.json();
  return data.content ?? '';
}

/** Queue repository for indexing. Throws if the backend rejects or is unreachable. */
export async function submitRepositoryIndexing(repoUrl, branch = 'main') {
  let res;
  try {
    res = await fetch(`${BASE}/api/repositories`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: repoUrl, branch }),
    });
  } catch {
    throw backendDown();
  }
  if (!res.ok) throw await readError(res, 'Could not queue repository');
  return res.json();
}

/** Poll real job status. Throws if it cannot be fetched (never reports a fake "completed"). */
export async function getJobStatus(jobId) {
  let res;
  try {
    res = await fetch(`${BASE}/api/jobs/${encodeURIComponent(jobId)}`);
  } catch {
    throw backendDown();
  }
  if (!res.ok) throw await readError(res, 'Could not read job status');
  return res.json();
}

/** Server-Sent Events stream URL for real-time progress events */
export function getJobStreamUrl(jobId) {
  return `${BASE}/api/jobs/${encodeURIComponent(jobId)}/stream`;
}

/** Parser diagnostics of the latest persisted analysis. */
export async function getDiagnostics(repoId) {
  let res;
  try {
    res = await fetch(`${BASE}/api/repositories/${encodeURIComponent(repoId)}/diagnostics`);
  } catch {
    throw backendDown();
  }
  if (!res.ok) throw await readError(res, 'Could not load diagnostics');
  return res.json();
}

/**
 * Upload a ZIP archive to FastAPI backend for analysis
 */
export async function uploadRepositoryZip(zipFile, branch = 'main', projectName = '') {
  const qs = new URLSearchParams({ branch: branch || 'main', filename: zipFile.name || 'repository.zip' });
  if (projectName) qs.set('name', projectName);
  let res;
  try {
    res = await fetch(`${BASE}/api/repositories/upload?${qs}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/zip' },
      body: zipFile,
    });
  } catch {
    throw backendDown();
  }
  if (!res.ok) throw await readError(res, 'ZIP upload failed');
  return res.json();
}
