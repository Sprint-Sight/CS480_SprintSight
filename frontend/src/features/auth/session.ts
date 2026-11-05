import { fetchUserProfile, type UserProfile } from "@/features/auth/login-api";
import { getAuthToken } from "@/features/projects/components/projects-api";

const ROLE_KEY = "sprintsight-auth-role";
const EMAIL_KEY = "sprintsight-auth-email";
const NAME_KEY = "sprintsight-auth-name";
const TOKEN_KEY = "sprintsight-access-token";

export type SessionRole = UserProfile["role"];

export type StoredSession = {
  role: SessionRole;
  email: string;
  fullName: string;
};

export function readStoredSession(): StoredSession | null {
  if (typeof window === "undefined") return null;
  const role = sessionStorage.getItem(ROLE_KEY) as SessionRole | null;
  const email = sessionStorage.getItem(EMAIL_KEY);
  if (!role || !email) return null;
  return { role, email, fullName: sessionStorage.getItem(NAME_KEY) || "" };
}

export function writeStoredSession(user: Pick<UserProfile, "role" | "email" | "full_name">) {
  sessionStorage.setItem(ROLE_KEY, user.role);
  sessionStorage.setItem(EMAIL_KEY, user.email);
  sessionStorage.setItem(NAME_KEY, user.full_name);
}

/**
 * The access token survives new tabs and browser restarts (localStorage), but the
 * role/email/name live in per-tab sessionStorage. When only the token is present,
 * rebuild the identity from `/auth/me` instead of sending the user back to /login.
 * Returns null when there is no usable session.
 */
export async function restoreSession(): Promise<StoredSession | null> {
  const existing = readStoredSession();
  if (existing) return existing;

  const token = getAuthToken();
  if (!token) return null;

  try {
    const user = await fetchUserProfile(token);
    writeStoredSession(user);
    return readStoredSession();
  } catch {
    return null;
  }
}

/** Removes the identity and the access token from both storages. */
export function clearStoredSession() {
  sessionStorage.removeItem(ROLE_KEY);
  sessionStorage.removeItem(EMAIL_KEY);
  sessionStorage.removeItem(NAME_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_KEY);
}
