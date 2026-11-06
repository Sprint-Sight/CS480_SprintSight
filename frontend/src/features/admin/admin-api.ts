import { apiRequest } from "@/lib/api/client";
import type { CreateUserData, EditUserData, Role, UserAccount } from "@/features/admin/types";

type BackendUser = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at?: string | null;
  signup_email_sent?: boolean;
};

type BackendCourse = { id: string; code: string; title?: string; name?: string };

export type AdminCourseOption = { id: string; code: string; title: string };

function today() {
  return new Date().toISOString().split("T")[0];
}

export function toUserAccount(user: BackendUser, fallbackCreatedAt = "N/A"): UserAccount {
  return {
    id: user.id,
    fullName: user.full_name,
    email: user.email,
    role: user.role,
    status: user.is_active ? "Active" : "Inactive",
    createdAt: user.created_at ? user.created_at.split("T")[0] : fallbackCreatedAt,
    signupEmailSent: user.signup_email_sent,
  };
}

export async function listUsers(): Promise<UserAccount[]> {
  const users = await apiRequest<BackendUser[]>("/users");
  return users.map((user) => toUserAccount(user));
}

export async function getUser(userId: string): Promise<UserAccount> {
  return toUserAccount(await apiRequest<BackendUser>(`/users/${encodeURIComponent(userId)}`));
}

export async function listCourses(): Promise<AdminCourseOption[]> {
  const courses = await apiRequest<BackendCourse[]>("/courses");
  return courses.map((course) => ({
    id: course.id,
    code: course.code,
    title: course.title ?? course.name ?? "",
  }));
}

export async function createUser(data: CreateUserData): Promise<UserAccount> {
  const user = await apiRequest<BackendUser>("/users", {
    method: "POST",
    body: JSON.stringify({
      email: data.email,
      full_name: data.fullName,
      role: data.role,
      ...(data.password ? { password: data.password } : {}),
    }),
  });
  return toUserAccount(user, today());
}

export async function updateUser(user: UserAccount, data: EditUserData): Promise<UserAccount> {
  const updated = await apiRequest<BackendUser>(`/users/${encodeURIComponent(user.id)}`, {
    method: "PATCH",
    body: JSON.stringify({
      role: data.role,
      full_name: data.fullName ?? user.fullName,
      email: data.email ?? user.email,
    }),
  });
  return toUserAccount(updated, user.createdAt);
}

export async function deactivateUser(userId: string): Promise<void> {
  await apiRequest<unknown>(`/users/${encodeURIComponent(userId)}`, { method: "DELETE" });
}

export async function activateUser(userId: string): Promise<void> {
  await apiRequest<unknown>(`/users/${encodeURIComponent(userId)}/activate`, { method: "POST" });
}

export async function resetUserPassword(userId: string, password: string): Promise<void> {
  await apiRequest<unknown>(`/users/${encodeURIComponent(userId)}/reset-password`, {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}
