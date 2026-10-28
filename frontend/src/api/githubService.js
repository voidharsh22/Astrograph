// GitHub App (private repository) client.
//
// The browser only ever holds an opaque Astrograph session token (sessionStorage, cleared with the tab).
// GitHub user tokens, installation tokens and the App private key stay on the backend.
// The token is sent as `Authorization: Bearer` (not a cookie), so it works across the dev ports/hosts
// and cannot be replayed by a cross-site request.

const BASE = (
  (typeof import.meta !== 'undefined' &&
    (import.meta.env?.VITE_API_BASE_URL || import.meta.env?.VITE_API_URL)) ||
  'http://127.0.0.1:8000'
).replace(/\/$/, '');

export const GITHUB_SESSION_KEY = 'astrograph_gh_session';
const NONCE_KEY = 'astrograph_gh_nonce';

function readStore(key) {
  try {
    return sessionStorage.getItem(key) || '';
  } catch {
    return '';
  }
}

function writeStore(key, value) {
  try {
    if (value) sessionStorage.setItem(key, value);
    else sessionStorage.removeItem(key);
  } catch {
    // storage unavailable: the user simply has to reconnect
  }
}

/** Headers to attach to backend calls so private repositories are readable by their owner. */
export function githubAuthHeaders() {
  const token = readStore(GITHUB_SESSION_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function hasGithubSession() {
  return Boolean(readStore(GITHUB_SESSION_KEY));
}

async function call(path, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE}/api/github${path}`, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...githubAuthHeaders(), ...(options.headers || {}) },
    });
  } catch {
    throw new Error(`Cannot connect to the Astrograph backend at ${BASE}. Ensure the server is running.`);
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    const err = new Error(
      (typeof detail === 'string' ? detail : detail?.message) || `Request failed (HTTP ${res.status})`
    );
    err.status = res.status;
    err.code = typeof detail === 'object' ? detail?.code : undefined;
    if (res.status === 401 || err.code === 'github_auth_expired') writeStore(GITHUB_SESSION_KEY, '');
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

export function getGithubStatus() {
  return call('/status');
}

/** Redirects the browser to GitHub. The nonce binds the sign-in to this browser tab. */
export async function startGithubConnect() {
  const { authorize_url: url, nonce } = await call('/connect', { method: 'POST' });
  writeStore(NONCE_KEY, nonce);
  window.location.assign(url);
}

/** Finish sign-in after GitHub redirects back with a one-time ticket. */
export async function completeGithubLogin(ticket) {
  const nonce = readStore(NONCE_KEY);
  writeStore(NONCE_KEY, '');
  const data = await call('/session', { method: 'POST', body: JSON.stringify({ ticket, nonce }) });
  writeStore(GITHUB_SESSION_KEY, data.session_token);
  return data;
}

export async function disconnectGithub() {
  try {
    await call('/session', { method: 'DELETE' });
  } finally {
    writeStore(GITHUB_SESSION_KEY, '');
  }
}

export async function listGithubRepositories() {
  return (await call('/repositories')).items;
}

export async function listGithubBranches(owner, repo) {
  return call(`/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/branches`);
}

/** Queue analysis; resolves with { repository_id, job_id } for the existing /analyze progress page. */
export function analyzeGithubRepository(owner, repo, ref) {
  return call('/analyze', { method: 'POST', body: JSON.stringify({ owner, repo, ref: ref || null }) });
}
