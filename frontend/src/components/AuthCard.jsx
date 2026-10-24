import { useState } from 'react';
import { friendlyError } from '../hooks/useAuth.js';
import { isFirebaseConfigured } from '../firebase.js';

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.5l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.8 6.1C12.3 13.5 17.7 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.6 5.9c4.4-4.1 7-10.1 7-17.6z" />
      <path fill="#FBBC05" d="M10.4 28.7A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.2.8-4.7l-7.8-6.1A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.8l7.8-6.1z" />
      <path fill="#34A853" d="M24 48c6.2 0 11.5-2 15.3-5.600l-7.600-5.900c-2.100 1.400-4.800 2.300-7.700 2.300-6.300 0-11.700-4-13.600-9.800l-7.800 6.100C6.500 42.600 14.600 48 24 48z" />
    </svg>
  );
}

export default function AuthCard({ auth }) {
  const [mode, setMode] = useState('signin'); // signin | signup
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  const run = async (fn) => {
    setError('');
    setInfo('');
    setBusy(true);
    try {
      await fn();
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (e) => {
    e.preventDefault();
    run(() =>
      mode === 'signup' ? auth.signUp(email.trim(), password) : auth.signIn(email.trim(), password)
    );
  };

  const onForgot = () => {
    if (!email.trim()) {
      setError('Enter your email above first, then press “Forgot password”.');
      return;
    }
    run(async () => {
      await auth.reset(email.trim());
      setInfo('Password reset email sent. Check your inbox.');
    });
  };

  const disabled = busy || !isFirebaseConfigured;

  return (
    <section className="card" aria-labelledby="auth-title">
      <div className="card__head">
        <span className="mono">[ access ]</span>
        <span className="mono">( 01 )</span>
      </div>

      <h2 id="auth-title" className="card__title">
        {mode === 'signin' ? 'Sign in to map your repos' : 'Create your Astrograph account'}
      </h2>

      {!isFirebaseConfigured && (
        <p className="notice" role="alert">
          Sign-in isn’t configured yet. Copy <code>.env.example</code> to <code>.env</code>, add your
          Firebase web-app keys, and restart the dev server.
        </p>
      )}

      <button type="button" className="btn btn--google" disabled={disabled} onClick={() => run(auth.google)}>
        <GoogleIcon />
        <span>Continue with Google</span>
      </button>

      <div className="divider" role="separator">
        <span className="mono">or with email</span>
      </div>

      <form onSubmit={onSubmit} noValidate>
        <label className="field">
          <span className="mono">email</span>
          <input
            type="email"
            autoComplete="email"
            placeholder="you@domain.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={disabled}
            required
          />
        </label>
        <label className="field">
          <span className="mono">password</span>
          <input
            type="password"
            autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={disabled}
            required
            minLength={6}
          />
        </label>

        {error && (
          <p className="msg msg--error" role="alert">
            {error}
          </p>
        )}
        {info && <p className="msg msg--ok">{info}</p>}

        <button type="submit" className="btn btn--primary" disabled={disabled}>
          {busy ? 'One moment…' : mode === 'signin' ? 'Sign in' : 'Create account'}
          <span aria-hidden="true">↗</span>
        </button>
      </form>

      <div className="card__foot">
        <button
          type="button"
          className="link"
          onClick={() => {
            setMode(mode === 'signin' ? 'signup' : 'signin');
            setError('');
            setInfo('');
          }}
        >
          {mode === 'signin' ? 'New here? Create an account' : 'Have an account? Sign in'}
        </button>
        {mode === 'signin' && (
          <button type="button" className="link" onClick={onForgot} disabled={disabled}>
            Forgot password
          </button>
        )}
      </div>
    </section>
  );
}
