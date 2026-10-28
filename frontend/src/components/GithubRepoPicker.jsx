import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Lock, ExternalLink } from 'lucide-react';
import {
  analyzeGithubRepository,
  completeGithubLogin,
  disconnectGithub,
  getGithubStatus,
  listGithubBranches,
  listGithubRepositories,
  startGithubConnect,
} from '../api/githubService.js';

const ERROR_TEXT = {
  access_denied: 'GitHub authorization was cancelled.',
  invalid_state: 'The GitHub sign-in expired. Please try again.',
};

/**
 * "Connect GitHub" flow for private repositories: sign in through the GitHub App, pick an
 * authorized repository (and optionally a branch / commit), then hand off to the normal
 * /analyze progress page. Rendered inside the existing New Analysis card.
 */
export default function GithubRepoPicker() {
  const navigate = useNavigate();
  const [status, setStatus] = useState(null); // null = loading
  const [repos, setRepos] = useState([]);
  const [selected, setSelected] = useState('');
  const [branches, setBranches] = useState([]);
  const [ref, setRef] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refresh = async () => {
    try {
      const s = await getGithubStatus();
      setStatus(s);
      if (s.connected) setRepos(await listGithubRepositories());
    } catch (err) {
      setStatus({ configured: false, connected: false });
      setError(err.message);
    }
  };

  // Finish the redirect round trip (?gh_ticket / ?gh_error), then load state.
  useEffect(() => {
    (async () => {
      const params = new URLSearchParams(window.location.search);
      const ticket = params.get('gh_ticket');
      const ghError = params.get('gh_error');
      if (ticket || ghError || params.get('gh_installed')) {
        ['gh_ticket', 'gh_error', 'gh_installed'].forEach((k) => params.delete(k));
        const qs = params.toString();
        window.history.replaceState({}, '', window.location.pathname + (qs ? `?${qs}` : ''));
      }
      if (ghError) setError(ERROR_TEXT[ghError] || 'GitHub sign-in failed. Please try again.');
      if (ticket) {
        try {
          await completeGithubLogin(ticket);
        } catch (err) {
          setError(err.message);
        }
      }
      await refresh();
    })();
  }, []);

  const handleSelect = async (fullName) => {
    setSelected(fullName);
    setRef('');
    setBranches([]);
    setError('');
    if (!fullName) return;
    const repo = repos.find((r) => r.full_name === fullName);
    try {
      const data = await listGithubBranches(repo.owner, repo.name);
      setBranches(data.items);
      setRef(data.default_branch);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleAnalyze = async (e) => {
    e.preventDefault();
    const repo = repos.find((r) => r.full_name === selected);
    if (!repo) return;
    setBusy(true);
    setError('');
    try {
      const res = await analyzeGithubRepository(repo.owner, repo.name, ref.trim());
      navigate(
        `/analyze?repo_id=${encodeURIComponent(res.repository_id)}&job_id=${encodeURIComponent(res.job_id)}` +
          `&name=${encodeURIComponent(repo.full_name)}&branch=${encodeURIComponent(ref.trim())}`
      );
    } catch (err) {
      setError(err.message);
      if (err.status === 401) await refresh();
    } finally {
      setBusy(false);
    }
  };

  const handleConnect = async () => {
    setBusy(true);
    setError('');
    try {
      await startGithubConnect();
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  };

  const handleDisconnect = async () => {
    await disconnectGithub().catch(() => {});
    setRepos([]);
    setSelected('');
    await refresh();
  };

  const errorBox = error && (
    <div style={{ color: '#f87171', fontSize: '0.8rem', textAlign: 'left' }}>{error}</div>
  );

  if (!status) {
    return <p className="new-analysis-sub">Checking GitHub connection...</p>;
  }

  if (!status.configured) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <p className="new-analysis-sub">
          Private repository access is not configured on this server. Public repositories and ZIP uploads still work.
        </p>
        {errorBox}
      </div>
    );
  }

  if (!status.connected) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <button type="button" className="analysis-submit-btn" onClick={handleConnect} disabled={busy}>
          <span>{busy ? 'Redirecting...' : 'Connect GitHub'}</span>
          <ArrowRight size={15} />
        </button>
        <p className="new-analysis-sub" style={{ margin: 0 }}>
          Read-only access to only the repositories you choose. Your code is not made public.
        </p>
        {errorBox}
      </div>
    );
  }

  return (
    <form onSubmit={handleAnalyze} className="new-analysis-form" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#9CA3AF' }}>
        <span>Connected as @{status.login}</span>
        <button type="button" onClick={handleDisconnect} style={{ background: 'none', border: 'none', color: '#FB923C', cursor: 'pointer', fontSize: '0.8rem' }}>
          Disconnect
        </button>
      </div>

      <select
        className="analysis-text-input"
        style={{ paddingLeft: '14px', fontSize: '0.85rem' }}
        value={selected}
        onChange={(e) => handleSelect(e.target.value)}
        required
      >
        <option value="">{repos.length ? 'Select an authorized repository' : 'No repositories authorized yet'}</option>
        {repos.map((r) => (
          <option key={r.id} value={r.full_name}>
            {r.private ? '🔒 ' : ''}{r.full_name} ({r.private ? 'private' : 'public'})
          </option>
        ))}
      </select>

      {selected && (
        <>
          <input
            className="analysis-text-input"
            style={{ paddingLeft: '14px', fontSize: '0.85rem' }}
            list="gh-branch-options"
            value={ref}
            onChange={(e) => setRef(e.target.value)}
            placeholder="Branch or commit SHA"
            maxLength={100}
          />
          <datalist id="gh-branch-options">
            {branches.map((b) => <option key={b.name} value={b.name} />)}
          </datalist>
        </>
      )}

      {errorBox}

      <button type="submit" className="analysis-submit-btn" disabled={busy || !selected}>
        <span>{busy ? 'Queueing...' : 'Analyse'}</span>
        <ArrowRight size={15} />
      </button>

      {status.install_url && (
        <a href={status.install_url} target="_blank" rel="noreferrer" style={{ color: '#9CA3AF', fontSize: '0.75rem', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
          Missing a repository? Add it to the GitHub App <ExternalLink size={11} />
        </a>
      )}
      {!status.ai_on_private_repos && (
        <span style={{ color: '#9CA3AF', fontSize: '0.72rem' }}>
          <Lock size={11} style={{ verticalAlign: 'middle' }} /> AI features are off for private repositories; source never leaves this server.
        </span>
      )}
    </form>
  );
}
