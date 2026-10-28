// Account authentication client. The backend is the only source of truth for "signed in":
// it sets an HttpOnly session cookie, which JavaScript can neither read nor forge.
//
// Requests use same-origin relative URLs (`/api/auth/...`). In development the Vite dev server proxies
// `/api` to the backend; in production serve the UI and API from one origin (reverse proxy).
// That keeps the cookie first-party (SameSite=Lax) and needs no cross-origin credentials.

async function call(path, options = {}) {
  let res;
  try {
    res = await fetch(`/api/auth${path}`, {
      credentials: 'same-origin',
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
  } catch {
    const err = new Error('Cannot reach the Astrograph server. Check that the backend is running.');
    err.code = 'network';
    throw err;
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    const err = new Error(
      (typeof detail === 'string' ? detail : detail?.message) || `Request failed (HTTP ${res.status})`
    );
    err.code = typeof detail === 'object' ? detail?.code : undefined;
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

/** The signed-in user, or null. Used on page load so a refresh keeps a valid session. */
export async function fetchCurrentUser() {
  try {
    return (await call('/me')).user;
  } catch (err) {
    if (err.status === 401) return null;
    throw err;
  }
}

export const signupRequest = (name, email, password) =>
  call('/signup', { method: 'POST', body: JSON.stringify({ name, email, password }) });

export const loginRequest = async (email, password) =>
  (await call('/login', { method: 'POST', body: JSON.stringify({ email, password }) })).user;

export const logoutRequest = () => call('/logout', { method: 'POST' });

/**
 * Starts the real Google flow: a full-page navigation to the backend, which redirects to Google's
 * account chooser. Nothing is signed in until the backend validates Google's response and redirects back.
 */
export async function startGoogleSignIn() {
  const cfg = await call('/config');
  if (!cfg.google) {
    const err = new Error('Google sign-in is not configured on this server yet.');
    err.code = 'google_not_configured';
    throw err;
  }
  window.location.assign('/api/auth/google/start');
}
