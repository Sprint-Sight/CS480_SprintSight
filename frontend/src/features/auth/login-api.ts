const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export type LoginResponse = {
  access_token: string;
  must_change_password?: boolean;
  error?: { message?: string };
  detail?: string;
};

export type UserProfile = {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "team_lead" | "member";
};

/**
 * Authenticates a user with email and password.
 * 
 * SECURITY NOTE: Validates that response.ok before extracting tokens
 * to prevent BOLA/IDOR attacks. The backend enforces that each user
 * can only receive their own credentials via proper auth checks.
 */
export async function loginUser(
  email: string,
  password: string,
): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: email.trim().toLowerCase(),
      password,
    }),
  });

  const data: unknown = await response.json().catch(() => ({}));

  if (!response.ok) {
    const errorData = data as LoginResponse;
    const detail = errorData?.error?.message ?? errorData?.detail ?? "Invalid email or password.";
    throw new Error(typeof detail === "string" ? detail : "Invalid email or password.");
  }

  return data as LoginResponse;
}

/**
 * Fetches the current authenticated user's profile.
 * Requires a valid JWT token in the Authorization header.
 * 
 * SECURITY NOTE: The backend validates the token and returns only
 * the authenticated user's profile, preventing BOLA/IDOR attacks.
 */
export async function fetchUserProfile(token: string): Promise<UserProfile> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    method: "GET",
    headers: {
      "Authorization": `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error("Failed to fetch user profile data.");
  }

  return response.json() as Promise<UserProfile>;
}

/**
 * Changes the password for an authenticated user after first-time login.
 * Requires a valid JWT token from the login response.
 * 
 * SECURITY NOTE: The backend validates the token is tied to the user
 * and only allows password changes for the authenticated session,
 * preventing BOLA/IDOR attacks.
 */
export async function changePasswordOnFirstLogin(
  token: string,
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/auth/change-password`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });

  const data: unknown = await response.json().catch(() => ({}));

  if (!response.ok) {
    const errorData = data as { detail?: string };
    const detail = errorData?.detail ?? "Unable to change password.";
    throw new Error(typeof detail === "string" ? detail : "Unable to change password.");
  }
}
