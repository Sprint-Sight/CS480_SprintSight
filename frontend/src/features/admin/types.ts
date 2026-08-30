export type Role = "admin" | "instructor" | "student";

export interface ProjectOption {
  id: string;
  projectName: string;
  courseCode: string;
  section: string;
}

export interface UserAccount {
  id: string;
  fullName: string;
  email: string;
  role: Role;
  projectId?: string;
  projectName?: string;
  courseCode?: string;
  section?: string;
  status: "Active" | "Inactive";
  createdAt: string;
}

export interface CreateUserData {
  fullName: string;
  email: string;
  role: Role;
  projectId?: string;
  courseCode?: string;
  section?: string;
}

export interface EditUserData {
  role: Role;
  projectId?: string;
  courseCode?: string;
  section?: string;
}