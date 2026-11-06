"use client";

import { useSyncExternalStore } from "react";

export type SessionRole = "admin" | "instructor" | "student";

export type SessionUser = {
  id: string;
  role: SessionRole;
  email: string;
  fullName: string;
};

/** `user` is null until `/auth/me` has been loaded for the token. */
export type Session = {
  token: string;
  user: SessionUser | null;
};

export const SESSION_STORAGE_KEY = "sprintsight-session";

// Keys used before the session was consolidated; migrated once, then removed.
const LEGACY_TOKEN_KEY = "sprintsight-access-token";
const LEGACY_ROLE_KEY = "sprintsight-auth-role";
const LEGACY_EMAIL_KEY = "sprintsight-auth-email";
const LEGACY_NAME_KEY = "sprintsight-auth-name";

const SESSION_ROLES: SessionRole[] = ["admin", "instructor", "student"];
const listeners = new Set<() => void>();

let cachedRaw: string | null | undefined;
let cachedSession: Session | null = null;

function safeGet(storage: Storage, key: string): string | null {
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}

function safeRemove(storage: Storage, key: string) {
  try {
    storage.removeItem(key);
  } catch {
    // Storage blocked: nothing to remove.
  }
}

function removeLegacyKeys() {
  [LEGACY_TOKEN_KEY, LEGACY_ROLE_KEY, LEGACY_EMAIL_KEY, LEGACY_NAME_KEY].forEach((key) => {
    safeRemove(window.sessionStorage, key);
    safeRemove(window.localStorage, key);
  });
}

function isSessionRole(value: unknown): value is SessionRole {
  return typeof value === "string" && SESSION_ROLES.includes(value as SessionRole);
}

function parseSession(raw: string | null): Session | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<Session> | null;
    if (!value || typeof value.token !== "string" || !value.token) return null;
    const user = value.user;
    const validUser =
      user &&
      isSessionRole(user.role) &&
      typeof user.email === "string" &&
      typeof user.fullName === "string"
        ? {
            id: typeof user.id === "string" ? user.id : "",
            role: user.role,
            email: user.email,
            fullName: user.fullName,
          }
        : null;
    return { token: value.token, user: validUser };
  } catch {
    return null;
  }
}

/** Moves a pre-consolidation login (token + per-tab identity keys) into the single key. */
function migrateLegacySession() {
  if (safeGet(window.localStorage, SESSION_STORAGE_KEY)) return;
  const token =
    safeGet(window.sessionStorage, LEGACY_TOKEN_KEY) ??
    safeGet(window.localStorage, LEGACY_TOKEN_KEY);
  if (!token) return;

  const role = safeGet(window.sessionStorage, LEGACY_ROLE_KEY);
  const email = safeGet(window.sessionStorage, LEGACY_EMAIL_KEY);
  const user =
    isSessionRole(role) && email
      ? { id: "", role, email, fullName: safeGet(window.sessionStorage, LEGACY_NAME_KEY) ?? "" }
      : null;
  try {
    window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({ token, user }));
    removeLegacyKeys();
  } catch {
    // Storage blocked: keep the legacy keys; the user will be asked to log in.
  }
}

function notify() {
  listeners.forEach((listener) => listener());
}

/** Current session, or null when signed out. Returns a stable reference until it changes. */
export function getSession(): Session | null {
  if (typeof window === "undefined") return null;
  migrateLegacySession();
  const raw = safeGet(window.localStorage, SESSION_STORAGE_KEY);
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedSession = parseSession(raw);
  }
  return cachedSession;
}

export function getSessionToken(): string | null {
  return getSession()?.token ?? null;
}

export function getSessionUser(): SessionUser | null {
  return getSession()?.user ?? null;
}

export function setSession(session: Session) {
  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  removeLegacyKeys();
  notify();
}

/** Clears the session in this tab; other tabs follow through the `storage` event. */
export function signOut() {
  if (typeof window === "undefined") return;
  safeRemove(window.localStorage, SESSION_STORAGE_KEY);
  removeLegacyKeys();
  notify();
}

export function subscribeToSession(listener: () => void) {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === SESSION_STORAGE_KEY || event.key === null) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

/** Reactive session for components; null on the server and when signed out. */
export function useSession(): Session | null {
  return useSyncExternalStore(subscribeToSession, getSession, () => null);
}
