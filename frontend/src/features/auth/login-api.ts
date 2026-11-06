import { apiRequest } from "@/lib/api/client";
import { getSession, setSession, type Session } from "@/lib/auth/session";

export type LoginResponse = {
  access_token: string;
  must_change_password?: boolean;
};

export type UserProfile = {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "instructor" | "student";
};

/**
 * Authenticates a user with email and password.
 *
 * SECURITY NOTE: apiRequest only resolves for a 2xx response, so a token is
 * never extracted from a failed login.
 */
export function loginUser(email: string, password: string): Promise<LoginResponse> {
  return apiRequest<LoginResponse>("/auth/login", {
    method: "POST",
    auth: false,
    body: JSON.stringify({
      email: email.trim().toLowerCase(),
      password,
    }),
  });
}

/**
 * Fetches the profile for a specific token (used right after login, before the
 * session is stored). The backend returns only the token owner's profile.
 */
export function fetchUserProfile(token: string): Promise<UserProfile> {
  return apiRequest<UserProfile>("/auth/me", {
    auth: false,
    headers: { Authorization: `Bearer ${token}` },
  });
}

/**
 * Changes the password after a first-time login with the token from that login.
 * The backend only allows the token owner to change their own password.
 */
export async function changePasswordOnFirstLogin(
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await apiRequest<unknown>("/auth/change-password", {
    method: "POST",
    auth: false,
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}

export function toSessionUser(profile: UserProfile): NonNullable<Session["user"]> {
  return { id: profile.id, role: profile.role, email: profile.email, fullName: profile.full_name };
}

/** Stores a freshly issued token together with its owner's profile. */
export async function startSession(token: string): Promise<Session> {
  const profile = await fetchUserProfile(token);
  const session = { token, user: toSessionUser(profile) };
  setSession(session);
  return session;
}

/**
 * Returns a complete session. When a token exists without a user (e.g. migrated
 * from an older login), loads the user from `/auth/me` instead of forcing a new
 * login. Returns null when signed out or when the token can't be used.
 */
export async function restoreSession(): Promise<Session | null> {
  const session = getSession();
  if (!session) return null;
  if (session.user) return session;
  try {
    const profile = await apiRequest<UserProfile>("/auth/me");
    const restored = { token: session.token, user: toSessionUser(profile) };
    setSession(restored);
    return restored;
  } catch {
    return null;
  }
}
