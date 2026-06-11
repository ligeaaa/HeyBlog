import type { AuthSession, UserProfile } from "../types/graph";

const AUTH_STORAGE_KEY = "heyblog_user_session";

/**
 * Read the browser-local user session snapshot.
 *
 * @returns Stored auth session, or null when no usable session exists.
 */
export function readStoredAuthSession(): AuthSession | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as AuthSession;
    if (!parsed.token || !parsed.user?.email) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

/**
 * Return whether the browser-local user session belongs to an active,
 * email-verified admin user.
 *
 * @returns True when the stored session can be used for admin navigation.
 */
export function hasStoredAdminSession(): boolean {
  const session = readStoredAuthSession();
  return Boolean(
    session?.token &&
      session.user?.role === "admin" &&
      session.user.isActive &&
      session.user.emailVerified,
  );
}

/**
 * Persist the current user session in localStorage.
 *
 * @param session Auth payload returned by register or login.
 */
export function storeAuthSession(session: AuthSession) {
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session));
}

/**
 * Merge a freshly fetched profile into the stored auth session.
 *
 * @param user Current user profile returned by `/api/auth/me`.
 * @returns Updated stored session, or null when no session exists.
 */
export function updateStoredUser(user: UserProfile): AuthSession | null {
  const current = readStoredAuthSession();
  if (!current) {
    return null;
  }
  const next = { ...current, user };
  storeAuthSession(next);
  return next;
}

/**
 * Remove the browser-local auth session.
 */
export function clearStoredAuthSession() {
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
}
