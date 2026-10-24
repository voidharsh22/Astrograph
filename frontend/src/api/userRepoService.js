/**
 * User-Scoped Repository Service
 * 
 * Provides strict multi-tenant isolation so each authenticated account
 * (e.g. namishg9@gmail.com vs another account) has its own independent
 * set of analyzed repositories.
 * 
 * Prioritizes instant, synchronous user-scoped storage so the UI never hangs
 * or waits on network/database handshakes, and asynchronously syncs to Cloud Firestore.
 */

import { db } from '../firebase.js';
import {
  collection,
  doc,
  getDocs,
  setDoc,
  deleteDoc,
  query,
  orderBy
} from 'firebase/firestore';

/**
 * Returns a unique storage key tied strictly to the authenticated user ID/email.
 */
export function getUserStorageKey(user) {
  if (user?.uid) {
    return `astrograph_repos_${user.uid}`;
  }
  if (user?.email) {
    return `astrograph_repos_${user.email.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
  }
  return 'astrograph_repos_guest';
}

/**
 * Clean up legacy global storage key so it never leaks between accounts.
 */
export function cleanupLegacyStorage(user) {
  try {
    const legacyKey = 'astrograph_analyzed_repos';
    const legacyData = localStorage.getItem(legacyKey);
    if (legacyData) {
      const userKey = getUserStorageKey(user);
      const existingUserData = localStorage.getItem(userKey);
      
      // If user storage is empty, migrate to current user once
      if (!existingUserData && user?.email && user.email.toLowerCase().includes('namish')) {
        localStorage.setItem(userKey, legacyData);
      }
      // Permanently remove the legacy un-scoped key
      localStorage.removeItem(legacyKey);
    }
  } catch (err) {
    console.warn('Storage cleanup notice:', err);
  }
}

/**
 * Synchronous instant read from the authenticated user's isolated local partition.
 * Never blocks the UI.
 */
export function getUserRepositoriesSync(user) {
  if (!user) return [];
  cleanupLegacyStorage(user);
  const userKey = getUserStorageKey(user);
  try {
    const saved = localStorage.getItem(userKey);
    return saved ? JSON.parse(saved) : [];
  } catch {
    return [];
  }
}

/**
 * Async fetch repositories with timeout fallback.
 * Loads user partition immediately and attempts cloud Firestore sync.
 */
export async function loadUserRepositories(user) {
  if (!user) return [];

  const localRepos = getUserRepositoriesSync(user);
  if (!db || !user.uid) {
    return localRepos;
  }

  // Attempt Firestore sync with a fast 1-second timeout so it never hangs
  try {
    const fetchPromise = (async () => {
      const reposRef = collection(db, 'users', user.uid, 'repositories');
      const q = query(reposRef, orderBy('createdAtTimestamp', 'desc'));
      const snapshot = await getDocs(q);

      if (!snapshot.empty) {
        const cloudRepos = [];
        snapshot.forEach((docSnap) => {
          cloudRepos.push({ id: docSnap.id, ...docSnap.data() });
        });
        const userKey = getUserStorageKey(user);
        localStorage.setItem(userKey, JSON.stringify(cloudRepos));
        return cloudRepos;
      }
      return localRepos;
    })();

    const timeoutPromise = new Promise((resolve) => setTimeout(() => resolve(localRepos), 1000));
    return await Promise.race([fetchPromise, timeoutPromise]);
  } catch (err) {
    return localRepos;
  }
}

/**
 * Synchronously saves a repository to the user's isolated storage partition,
 * updates Firestore non-blockingly in the background, and returns the updated list instantly.
 */
export function saveUserSingleRepository(user, newRepoItem) {
  if (!user) return [newRepoItem];

  const userKey = getUserStorageKey(user);
  let currentList = [];
  try {
    const saved = localStorage.getItem(userKey);
    currentList = saved ? JSON.parse(saved) : [];
  } catch {
    currentList = [];
  }

  const existingIndex = currentList.findIndex(
    (r) => r.name.toLowerCase() === newRepoItem.name.toLowerCase()
  );

  const enrichedItem = {
    ...newRepoItem,
    userId: user.uid || '',
    userEmail: user.email || '',
    createdAtTimestamp: newRepoItem.createdAtTimestamp || Date.now()
  };

  let updatedList;
  if (existingIndex >= 0) {
    updatedList = [...currentList];
    updatedList[existingIndex] = { ...updatedList[existingIndex], ...enrichedItem };
  } else {
    updatedList = [enrichedItem, ...currentList];
  }

  // 1. Instant synchronous write to isolated user storage
  try {
    localStorage.setItem(userKey, JSON.stringify(updatedList));
  } catch (err) {
    console.warn('Unable to persist to user storage:', err);
  }

  // 2. Non-blocking background sync to Cloud Firestore
  if (db && user.uid) {
    Promise.race([
      setDoc(
        doc(db, 'users', user.uid, 'repositories', enrichedItem.id),
        enrichedItem,
        { merge: true }
      ),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 1500))
    ]).catch(() => {
      // Gracefully catch any Firestore errors/timeouts so user is never affected
    });
  }

  return updatedList;
}

/**
 * Remove a specific repository belonging to the user.
 */
export function deleteUserRepository(user, repoId) {
  if (!user) return [];

  const userKey = getUserStorageKey(user);
  let currentList = [];
  try {
    const saved = localStorage.getItem(userKey);
    currentList = saved ? JSON.parse(saved) : [];
  } catch {
    currentList = [];
  }

  const updatedList = currentList.filter((r) => r.id !== repoId);
  try {
    localStorage.setItem(userKey, JSON.stringify(updatedList));
  } catch (err) {
    console.warn('Unable to persist deletion:', err);
  }

  if (db && user.uid) {
    Promise.race([
      deleteDoc(doc(db, 'users', user.uid, 'repositories', repoId)),
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), 1500))
    ]).catch(() => {});
  }

  return updatedList;
}

/**
 * Clear all repositories belonging strictly to the user.
 */
export function clearAllUserRepositories(user) {
  if (!user) return [];

  const userKey = getUserStorageKey(user);
  try {
    localStorage.removeItem(userKey);
  } catch (err) {
    console.warn('Unable to clear user storage:', err);
  }

  if (db && user.uid) {
    (async () => {
      try {
        const reposRef = collection(db, 'users', user.uid, 'repositories');
        const snapshot = await getDocs(reposRef);
        const deletePromises = [];
        snapshot.forEach((docSnap) => {
          deletePromises.push(deleteDoc(docSnap.ref));
        });
        await Promise.all(deletePromises);
      } catch (err) {
        // ignore
      }
    })().catch(() => {});
  }

  return [];
}
