export type Role = "admin" | "instructor" | "student";

export interface UserAccount {
  id: string;
  fullName: string;
  email: string;
  role: Role;
  status: "Active" | "Inactive";
  createdAt: string;
}

export interface CreateUserData {
  fullName: string;
  email: string;
  password?: string;
  role: Role;
}

export interface EditUserData {
  fullName?: string;
  email?: string;
  password?: string;
  role: Role;
}