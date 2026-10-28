import { createContext, createElement, useCallback, useContext, useEffect, useState } from 'react';
import {
  fetchCurrentUser,
  loginRequest,
  logoutRequest,
  signupRequest,
  startGoogleSignIn,
} from '../api/authService.js';

const MESSAGES = {
  invalid_credentials: 'Invalid email or password.',
  email_exists: 'An account with this email already exists. Please log in instead.',
  rate_limited: 'Too many attempts. Please wait a bit and try again.',
  network: 'Cannot reach the Astrograph server. Check that the backend is running.',
  google_not_configured: 'Google sign-in is not configured on this server yet.',
  google_cancelled: 'Google sign-in was cancelled. You were not signed in.',
  google_invalid_state: 'Google sign-in expired or could not be verified. Please try again.',
  google_invalid_token: 'Google sign-in could not be verified. Please try again.',
  google_token_expired: 'Google sign-in expired. Please try again.',
  google_exchange_failed: 'Google sign-in failed. Please try again.',
  google_email_unverified: 'Your Google email address is not verified, so it cannot be used to sign in.',
  google_email_in_use:
    'An account with this email already exists. Log in with your email and password instead.',
  google_unavailable: 'Google could not be reached. Please try again shortly.',
  google_failed: 'Google sign-in failed. Please try again.',
};

export function friendlyError(err) {
  return MESSAGES[err?.code] || err?.message || 'Something went wrong. Please try again.';
}

/** Message for an `?auth_error=<code>` returned by the backend after a failed Google redirect. */
export function messageForAuthError(code) {
  return MESSAGES[code] || 'Sign-in failed. Please try again.';
}

// Kept for existing consumers: authentication is always the real backend now (no demo mode).
export const isDemoMode = false;
export const authMode = 'server';
export const isFirebaseConfigured = false;

const AuthContext = createContext(null);

// Adapt the backend user to the shape the rest of the UI already reads.
const toUiUser = (u) =>
  u && { uid: u.id, email: u.email, displayName: u.name, photoURL: u.picture || null };

function useAuthState() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  // The UI is "signed out" until the backend confirms a valid session.
  useEffect(() => {
    let cancelled = false;
    fetchCurrentUser()
      .then((u) => !cancelled && setUser(toUiUser(u)))
      .catch(() => !cancelled && setUser(null))
      .finally(() => !cancelled && setReady(true));
    return () => {
      cancelled = true;
    };
  }, []);

  const google = useCallback(() => startGoogleSignIn(), []);

  // Signup never signs the user in; the caller sends them to the login form.
  const signUp = useCallback((email, password, name = '') => signupRequest(name, email, password), []);

  const signIn = useCallback(async (email, password) => {
    const u = toUiUser(await loginRequest(email, password));
    setUser(u);
    return u;
  }, []);

  const reset = useCallback(async () => {
    throw new Error('Password reset by email is not available yet. Contact the administrator.');
  }, []);

  const logout = useCallback(async () => {
    await logoutRequest().catch(() => {});
    setUser(null);
  }, []);

  // Authentication is carried by the HttpOnly session cookie; there is no token for JS to hold.
  const getToken = useCallback(async () => null, []);

  return { user, ready, authMode, isDemoMode, isFirebaseConfigured, google, signUp, signIn, reset, logout, getToken };
}

// One shared auth state for the whole app (wrap <App /> content with this).
export function AuthProvider({ children }) {
  const value = useAuthState();
  return createElement(AuthContext.Provider, { value }, children);
}

export default function useAuth() {
  return useContext(AuthContext);
}
