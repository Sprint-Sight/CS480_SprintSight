const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export type PasswordPurpose = "first-time-password" | "password-reset";

type PasswordActionResponse = {
  detail?: unknown;
  error?: { message?: unknown };
};

async function postAuth<T>(path: string, body: Record<string, string>): Promise<T> {
  const response = await fetch(`${API_BASE_URL}/auth/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const result: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const errorResponse = result as PasswordActionResponse | null;
    const detail = errorResponse?.error?.message ?? errorResponse?.detail;
    throw new Error(
      typeof detail === "string" ? detail : "The request could not be completed. Please try again.",
    );
  }

  return result as T;
}

export function requestPasswordReset(email: string): Promise<{ message: string }> {
  return postAuth("password-reset/request", { email: email.trim().toLowerCase() });
}

export function completePasswordAction(
  purpose: PasswordPurpose,
  token: string,
  newPassword: string,
): Promise<unknown> {
  const endpoint = purpose === "first-time-password" ? "first-time-password" : "password-reset";
  return postAuth(`${endpoint}/complete`, { token, new_password: newPassword });
}
