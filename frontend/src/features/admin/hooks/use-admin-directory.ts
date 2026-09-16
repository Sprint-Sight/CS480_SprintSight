"use client";

import { useMemo } from "react";
import type { UserAccount } from "@/features/admin/types";

export function useAdminDirectory(users: UserAccount[], searchQuery: string, roleFilter: string, statusFilter: string) {
  const filteredUsers = useMemo(() => users.filter((user) => {
    const query = searchQuery.toLowerCase();
    const matchesSearch = user.fullName.toLowerCase().includes(query) || user.email.toLowerCase().includes(query) || Boolean(user.projectName?.toLowerCase().includes(query)) || Boolean(user.courseCode?.toLowerCase().includes(query));
    return matchesSearch && (roleFilter === "all" || user.role === roleFilter) && (statusFilter === "all" || user.status === statusFilter);
  }), [users, searchQuery, roleFilter, statusFilter]);
  const stats = useMemo(() => ({ total: users.length, active: users.filter((user) => user.status === "Active").length, students: users.filter((user) => user.role === "student").length, instructors: users.filter((user) => user.role === "instructor").length }), [users]);
  return { filteredUsers, stats };
}
