import { createContext, createElement, useCallback, useContext, useEffect, useState } from 'react';
import {
  onAuthStateChanged,
  signInWithPopup,
  signInWithRedirect,
  getRedirectResult,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  sendPasswordResetEmail,
  sendEmailVerification,
  signOut,
} from 'firebase/auth';
import { auth, googleProvider, isFirebaseConfigured } from '../firebase.js';

const MESSAGES = {
  'auth/invalid-email': 'That email address looks invalid.',
  'auth/missing-password': 'Enter your password.',
  'auth/weak-password': 'Password must be at least 6 characters.',
  'auth/email-already-in-use': 'An account with this email already exists. Try signing in.',
  'auth/invalid-credential': 'Wrong email or password.',
  'auth/user-not-found': 'No account found for this email.',
  'auth/wrong-password': 'Wrong email or password.',
  'auth/too-many-requests': 'Too many attempts. Please wait a bit and try again.',
  'auth/network-request-failed': 'Network error. Check your connection.',
  'auth/popup-closed-by-user': 'Google sign-in was closed before finishing.',
  'auth/cancelled-popup-request': 'Google sign-in was cancelled.',
  'auth/unauthorized-domain':
    'This domain is not authorised in Firebase. Add it under Authentication → Settings → Authorized domains.',
  'auth/operation-not-allowed':
    'This sign-in method is not enabled in the Firebase console yet.',
};

export function friendlyError(err) {
  return MESSAGES[err?.code] || err?.message || 'Something went wrong. Please try again.';
}

const AuthContext = createContext(null);

function useAuthState() {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(!isFirebaseConfigured);

  useEffect(() => {
    if (!auth) return undefined;
    getRedirectResult(auth).catch(() => {});
    return onAuthStateChanged(auth, (u) => {
      setUser(u);
      setReady(true);
    });
  }, []);

  const google = useCallback(async () => {
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err) {
      if (err?.code === 'auth/popup-blocked') {
        await signInWithRedirect(auth, googleProvider);
        return;
      }
      throw err;
    }
  }, []);

  const signUp = useCallback(async (email, password) => {
    const cred = await createUserWithEmailAndPassword(auth, email, password);
    sendEmailVerification(cred.user).catch(() => {});
  }, []);

  const signIn = useCallback(
    (email, password) => signInWithEmailAndPassword(auth, email, password),
    []
  );

  const reset = useCallback((email) => sendPasswordResetEmail(auth, email), []);
  const logout = useCallback(() => signOut(auth), []);
  // Fresh Firebase ID token, sent to the backend so it can tell who the user is.
  const getToken = useCallback(() => (auth?.currentUser ? auth.currentUser.getIdToken() : null), []);

  return { user, ready, google, signUp, signIn, reset, logout, getToken };
}

// One shared auth state for the whole app (wrap <App /> content with this).
export function AuthProvider({ children }) {
  const value = useAuthState();
  return createElement(AuthContext.Provider, { value }, children);
}

export default function useAuth() {
  return useContext(AuthContext);
}
