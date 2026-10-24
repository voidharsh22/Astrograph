// Accepts https://github.com/owner/repo, github.com/owner/repo, with optional
// .git, trailing slash or extra path (/tree/main/...). Returns null if invalid.
export function parseGithubUrl(input) {
  const raw = (input || '').trim();
  if (!raw) return null;
  const withProtocol = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  let url;
  try {
    url = new URL(withProtocol);
  } catch {
    return null;
  }
  if (!['github.com', 'www.github.com'].includes(url.hostname.toLowerCase())) return null;
  const [owner, nameRaw] = url.pathname.split('/').filter(Boolean);
  const name = nameRaw ? nameRaw.replace(/\.git$/i, '') : '';
  const valid = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/.test(owner || '') && /^[\w.-]+$/.test(name);
  if (!valid) return null;
  return { owner, name, url: `https://github.com/${owner}/${name}` };
}
