import { apiRequest } from "@/lib/api/client";

export type PasswordPurpose = "first-time-password" | "password-reset";

function postAuth<T>(path: string, body: Record<string, string>): Promise<T> {
  return apiRequest<T>(`/auth/${path}`, {
    method: "POST",
    auth: false,
    body: JSON.stringify(body),
  });
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
