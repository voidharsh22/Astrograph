// Backend API client. The backend (SQLite/PostgreSQL) is built by teammates.
//
// Set VITE_API_URL in .env (e.g. http://localhost:8000) once it exists.
// Every request sends the user's Firebase ID token:  Authorization: Bearer <token>
// The backend should verify it with Firebase Admin SDK to know which user it is.
//
// CONTRACT the frontend expects
//   GET {VITE_API_URL}/api/repos
//     -> 200 JSON array of the repos THIS USER SAVED (only saved ones):
//        [{ "id": "123", "owner": "facebook", "name": "react",
//           "url": "https://github.com/facebook/react",
//           "savedAt": "2026-10-21T10:00:00Z" }]
//     -> empty array [] when nothing is saved.

const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

export const isApiConfigured = Boolean(BASE);

export async function listSavedRepos(getToken) {
  // Backend not connected yet: behave as "no saved repos".
  if (!isApiConfigured) return [];

  const token = await getToken();
  const res = await fetch(`${BASE}/api/repos`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
  });
  if (!res.ok) throw new Error(`Could not load repos (${res.status})`);
  const data = await res.json();
  return Array.isArray(data) ? data : [];
}
