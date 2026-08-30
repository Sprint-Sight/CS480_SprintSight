"use client";

import React, { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import {
  Shield,
  UserPlus,
  Search,
  Filter,
  Edit3,
  Trash2,
  X,
  CheckCircle2,
  AlertCircle,
  Users,
  UserCheck,
  FolderGit2,
  BookOpen,
} from "lucide-react";
import { UserAccount, Role, CreateUserData, EditUserData, ProjectOption } from "../types";
import { CreateUserModal } from "./create-user-modal";
import { EditUserModal } from "./edit-user-modal";
import { ConfirmationModal } from "@/components/ui/confirmation-modal";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

// Mock available projects based on backend schema structure
const initialProjects: ProjectOption[] = [
  { id: "p1", projectName: "Team Alpha — E-Commerce", courseCode: "CS480", section: "001" },
  { id: "p2", projectName: "Team Beta — AI Evaluator", courseCode: "CS480", section: "001" },
  { id: "p3", projectName: "Team Gamma — Health Platform", courseCode: "CS480", section: "002" },
  { id: "p4", projectName: "Team Delta — Dev Analytics", courseCode: "CS488", section: "001" },
];

export function AdminPageContent() {
  const router = useRouter();
  const [adminName, setAdminName] = useState("");
  const [currentEmail, setCurrentEmail] = useState("");
  const [mounted, setMounted] = useState(false);

  // Identity & Project State
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [projects] = useState<ProjectOption[]>(initialProjects);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRoleFilter, setSelectedRoleFilter] = useState("all");
  const [selectedStatusFilter, setSelectedStatusFilter] = useState("all");

  // Modals state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserAccount | null>(null);
  const [userToDeactivate, setUserToDeactivate] = useState<UserAccount | null>(null);

  // Notifications
  const [notification, setNotification] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  const showNotification = (type: "success" | "error", message: string) => {
    setNotification({ type, message });
    setTimeout(() => setNotification(null), 4000);
  };

  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role");
    const savedName = sessionStorage.getItem("sprintsight-auth-name");
    const savedEmail = sessionStorage.getItem("sprintsight-auth-email");
    const token = sessionStorage.getItem("sprintsight-access-token");

    if (savedRole !== "admin") {
      router.replace("/login");
      return;
    }

    if (savedName) setAdminName(savedName);
    if (savedEmail) setCurrentEmail(savedEmail);

    if (token) {
      setLoadingUsers(true);
      fetch(`${API_BASE_URL}/users`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((res) => {
          if (!res.ok) throw new Error("Failed to fetch user directory");
          return res.json();
        })
        .then((data) => {
          const mappedUsers: UserAccount[] = data.map((u: any, idx: number) => {
            const assignedProj = initialProjects[idx % initialProjects.length];
            return {
              id: u.id,
              fullName: u.full_name,
              email: u.email,
              role: u.role,
              projectId: u.role === "student" ? assignedProj.id : undefined,
              projectName: u.role === "student" ? assignedProj.projectName : undefined,
              courseCode: u.role !== "admin" ? assignedProj.courseCode : "Global System",
              section: u.role !== "admin" ? assignedProj.section : "-",
              status: u.is_active ? "Active" : "Inactive",
              createdAt: u.created_at ? u.created_at.split("T")[0] : "N/A",
            };
          });
          setUsers(mappedUsers);
        })
        .catch((err) => {
          console.error("Error fetching users:", err);
          showNotification("error", "Failed to load directory.");
        })
        .finally(() => {
          setLoadingUsers(false);
          setMounted(true);
        });
    } else {
      setMounted(true);
    }
  }, [router]);

  const handleCreateUser = async (data: CreateUserData) => {
    const token = sessionStorage.getItem("sprintsight-access-token");
    try {
      const res = await fetch(`${API_BASE_URL}/users`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          email: data.email,
          full_name: data.fullName,
          role: data.role,
          password: "TemporaryPassword123!",
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        showNotification("error", `Failed: ${err.detail || "Server error"}`);
        return;
      }

      const newUser = await res.json();
      const assignedProj = projects.find((p) => p.id === data.projectId);

      const createdRecord: UserAccount = {
        id: newUser.id,
        fullName: newUser.full_name,
        email: newUser.email,
        role: newUser.role,
        projectId: data.role === "student" ? data.projectId : undefined,
        projectName: data.role === "student" ? assignedProj?.projectName : undefined,
        courseCode: data.role !== "admin" ? data.courseCode || "CS480" : "Global System",
        section: data.role !== "admin" ? data.section || "001" : "-",
        status: newUser.is_active ? "Active" : "Inactive",
        createdAt: new Date().toISOString().split("T")[0],
      };

      setUsers((prev) => [createdRecord, ...prev]);
      showNotification("success", `User ${newUser.full_name} created successfully.`);
    } catch (err) {
      showNotification("error", "Network error while provisioning user.");
    }
  };

  const handleUpdateUser = async (user: UserAccount, data: EditUserData) => {
    const token = sessionStorage.getItem("sprintsight-access-token");
    try {
      const res = await fetch(`${API_BASE_URL}/users/${user.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ role: data.role }),
      });

      if (res.ok) {
        const assignedProj = projects.find((p) => p.id === data.projectId);
        setUsers((prev) =>
          prev.map((u) =>
            u.id === user.id
              ? {
                  ...u,
                  role: data.role,
                  projectId: data.role === "student" ? data.projectId : undefined,
                  projectName: data.role === "student" ? assignedProj?.projectName : undefined,
                  courseCode: data.role !== "admin" ? data.courseCode : "Global System",
                  section: data.role !== "admin" ? data.section : "-",
                }
              : u
          )
        );
        showNotification("success", `Updated identity details for ${user.fullName}.`);
      } else {
        const err = await res.json();
        showNotification("error", err.detail || "Failed to update record.");
      }
    } catch (err) {
      showNotification("error", "Network error while updating user.");
    }
  };

  const handleDeactivateUser = async () => {
    if (!userToDeactivate) return;
    const token = sessionStorage.getItem("sprintsight-access-token");

    try {
      const res = await fetch(`${API_BASE_URL}/users/${userToDeactivate.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (res.ok) {
        setUsers((prev) =>
          prev.map((u) => (u.id === userToDeactivate.id ? { ...u, status: "Inactive" } : u))
        );
        showNotification("success", `User ${userToDeactivate.fullName} deactivated.`);
      } else {
        const err = await res.json();
        showNotification("error", err.detail || "Failed to deactivate record.");
      }
    } catch (err) {
      showNotification("error", "Network error while deactivating user.");
    } finally {
      setUserToDeactivate(null);
    }
  };

  const filteredUsers = useMemo(() => {
    return users.filter((user) => {
      const matchesSearch =
        user.fullName.toLowerCase().includes(searchQuery.toLowerCase()) ||
        user.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (user.projectName && user.projectName.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (user.courseCode && user.courseCode.toLowerCase().includes(searchQuery.toLowerCase()));
      const matchesRole = selectedRoleFilter === "all" || user.role === selectedRoleFilter;
      const matchesStatus = selectedStatusFilter === "all" || user.status === selectedStatusFilter;

      return matchesSearch && matchesRole && matchesStatus;
    });
  }, [users, searchQuery, selectedRoleFilter, selectedStatusFilter]);

  const stats = useMemo(() => {
    const total = users.length;
    const active = users.filter((u) => u.status === "Active").length;
    const students = users.filter((u) => u.role === "student").length;
    const instructors = users.filter((u) => u.role === "instructor").length;
    return { total, active, students, instructors };
  }, [users]);

  if (!mounted) return null;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 bg-slate-50 min-h-screen">
      {/* Notification Toast */}
      {notification && (
        <div
          className={`fixed top-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl border shadow-lg transition-all ${
            notification.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-rose-50 border-rose-200 text-rose-800"
          }`}
        >
          {notification.type === "success" ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-600" />
          ) : (
            <AlertCircle className="w-5 h-5 text-rose-600" />
          )}
          <span className="text-sm font-medium">{notification.message}</span>
          <button onClick={() => setNotification(null)} className="ml-2 hover:opacity-75">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">User & Project Directory</h1>
          <p className="text-slate-500 mt-1">
            Welcome back, <span className="font-semibold text-slate-700">{adminName || "System Admin"}</span>. Assign users to courses, manage sections, and place students in project teams.
          </p>
        </div>
        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-4 py-2.5 rounded-xl shadow-xs transition-colors self-start md:self-auto"
        >
          <UserPlus className="w-4 h-4" />
          Provision New User
        </button>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
          <div className="flex justify-between items-start mb-2">
            <div>
              <p className="text-sm font-medium text-slate-500">Total Users</p>
              <h3 className="text-3xl font-bold text-slate-900 mt-1">{stats.total}</h3>
            </div>
            <div className="p-2.5 bg-blue-50 rounded-lg text-blue-600">
              <Users className="w-5 h-5" />
            </div>
          </div>
          <p className="text-xs font-medium text-slate-500">Registered Accounts</p>
        </div>

        <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
          <div className="flex justify-between items-start mb-2">
            <div>
              <p className="text-sm font-medium text-slate-500">Active Accounts</p>
              <h3 className="text-3xl font-bold text-slate-900 mt-1">{stats.active}</h3>
            </div>
            <div className="p-2.5 bg-emerald-50 rounded-lg text-emerald-600">
              <UserCheck className="w-5 h-5" />
            </div>
          </div>
          <p className="text-xs font-medium text-emerald-600">
            {stats.total > 0 ? Math.round((stats.active / stats.total) * 100) : 0}% Operational
          </p>
        </div>

        <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
          <div className="flex justify-between items-start mb-2">
            <div>
              <p className="text-sm font-medium text-slate-500">Course Instructors</p>
              <h3 className="text-3xl font-bold text-slate-900 mt-1">{stats.instructors}</h3>
            </div>
            <div className="p-2.5 bg-indigo-50 rounded-lg text-indigo-600">
              <Shield className="w-5 h-5" />
            </div>
          </div>
          <p className="text-xs font-medium text-indigo-600">Course Supervisors</p>
        </div>

        <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
          <div className="flex justify-between items-start mb-2">
            <div>
              <p className="text-sm font-medium text-slate-500">Enrolled Students</p>
              <h3 className="text-3xl font-bold text-slate-900 mt-1">{stats.students}</h3>
            </div>
            <div className="p-2.5 bg-purple-50 rounded-lg text-purple-600">
              <FolderGit2 className="w-5 h-5" />
            </div>
          </div>
          <p className="text-xs font-medium text-purple-600">Project Members</p>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-white p-4 rounded-xl border border-slate-100 shadow-sm flex flex-wrap items-center justify-between gap-4">
        <div className="relative flex-1 min-w-[280px]">
          <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
          <input
            type="text"
            placeholder="Search by user name, email, course, or project team..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-10 pr-4 py-2 text-sm text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all"
          />
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 px-3 py-2 rounded-lg text-xs font-medium text-slate-600">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <span>Role:</span>
            <select
              value={selectedRoleFilter}
              onChange={(e) => setSelectedRoleFilter(e.target.value)}
              className="bg-transparent text-slate-900 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="all">All Roles</option>
              <option value="student">Student</option>
              <option value="instructor">Instructor</option>
              <option value="admin">Admin</option>
            </select>
          </div>

          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 px-3 py-2 rounded-lg text-xs font-medium text-slate-600">
            <span>Status:</span>
            <select
              value={selectedStatusFilter}
              onChange={(e) => setSelectedStatusFilter(e.target.value)}
              className="bg-transparent text-slate-900 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="all">All Statuses</option>
              <option value="Active">Active</option>
              <option value="Inactive">Inactive</option>
            </select>
          </div>
        </div>
      </div>

      {/* User Directory Table */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/50 text-slate-500 text-xs font-semibold">
                <th className="py-3.5 px-6">User Identity</th>
                <th className="py-3.5 px-6">Role</th>
                <th className="py-3.5 px-6">Course & Section</th>
                <th className="py-3.5 px-6">Assigned Project / Team</th>
                <th className="py-3.5 px-6">Status</th>
                <th className="py-3.5 px-6">Created Date</th>
                <th className="py-3.5 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500 text-xs">
                    {loadingUsers ? "Loading user records..." : "No matching users or projects found."}
                  </td>
                </tr>
              ) : (
                filteredUsers.map((user) => {
                  const isSelf = user.email === currentEmail;
                  return (
                    <tr key={user.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-4 px-6">
                        <div className="font-semibold text-slate-900 flex items-center gap-2">
                          {user.fullName}
                          {isSelf && (
                            <span className="text-[10px] font-bold bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">
                              YOU
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-slate-500 mt-0.5">{user.email}</div>
                      </td>
                      <td className="py-4 px-6">
                        <span
                          className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-semibold ${
                            user.role === "admin"
                              ? "bg-purple-50 text-purple-700 border border-purple-200"
                              : user.role === "instructor"
                              ? "bg-blue-50 text-blue-700 border border-blue-200"
                              : "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          }`}
                        >
                          {user.role.toUpperCase()}
                        </span>
                      </td>
                      <td className="py-4 px-6 text-xs text-slate-700 font-medium">
                        {user.role === "admin" ? (
                          <span className="text-slate-400">System Global</span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 bg-slate-100 text-slate-700 px-2.5 py-1 rounded-md font-mono">
                            <BookOpen className="w-3 h-3 text-slate-500" />
                            {user.courseCode} (Sec {user.section})
                          </span>
                        )}
                      </td>
                      <td className="py-4 px-6 text-xs">
                        {user.role === "student" ? (
                          user.projectName ? (
                            <span className="font-medium text-slate-900 bg-purple-50 border border-purple-200 text-purple-800 px-2.5 py-1 rounded-md inline-flex items-center gap-1.5">
                              <FolderGit2 className="w-3.5 h-3.5 text-purple-600" />
                              {user.projectName}
                            </span>
                          ) : (
                            <span className="text-amber-600 font-medium bg-amber-50 border border-amber-200 px-2.5 py-1 rounded-md">
                              Unassigned
                            </span>
                          )
                        ) : (
                          <span className="text-slate-400">N/A ({user.role})</span>
                        )}
                      </td>
                      <td className="py-4 px-6">
                        <span
                          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
                            user.status === "Active"
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : "bg-slate-100 text-slate-500 border border-slate-200"
                          }`}
                        >
                          <span
                            className={`w-1.5 h-1.5 rounded-full ${
                              user.status === "Active" ? "bg-emerald-500" : "bg-slate-400"
                            }`}
                          />
                          {user.status}
                        </span>
                      </td>
                      <td className="py-4 px-6 text-xs text-slate-500">{user.createdAt}</td>
                      <td className="py-4 px-6 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => setEditingUser(user)}
                            className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                            title="Edit Role / Project Assignment"
                          >
                            <Edit3 className="w-4 h-4" />
                          </button>
                          <button
                            disabled={isSelf}
                            onClick={() => setUserToDeactivate(user)}
                            className={`p-1.5 rounded-lg transition-colors ${
                              isSelf
                                ? "text-slate-300 cursor-not-allowed"
                                : "text-slate-400 hover:text-rose-600 hover:bg-rose-50"
                            }`}
                            title={isSelf ? "Cannot deactivate yourself" : "Deactivate User"}
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modals */}
      <CreateUserModal
        isOpen={isCreateModalOpen}
        projects={projects}
        onClose={() => setIsCreateModalOpen(false)}
        onCreate={handleCreateUser}
      />

      <EditUserModal
        user={editingUser}
        projects={projects}
        onClose={() => setEditingUser(null)}
        onSave={handleUpdateUser}
      />

      <ConfirmationModal
        isOpen={!!userToDeactivate}
        onClose={() => setUserToDeactivate(null)}
        onConfirm={handleDeactivateUser}
        title="Deactivate Account"
        message={`Deactivate ${userToDeactivate?.fullName}? They will lose access to SprintSight and their assigned project.`}
        confirmText="Yes, Deactivate"
        cancelText="Cancel"
      />
    </div>
  );
}