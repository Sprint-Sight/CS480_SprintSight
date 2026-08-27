"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  FolderOpen,
  Activity,
  FileCheck,
  AlertTriangle,
  Award,
  Clock,
  CheckCircle2,
  GitCommit,
  CheckSquare,
  FileCode,
  MessageSquare,
  ArrowRight,
  Search,
  Filter,
  Plus,
  Trash2,
  Edit3,
  ChevronLeft,
  ChevronRight,
  Shield,
  UserCheck,
  UserPlus,
  X,
  MoreVertical,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

type Role = "student" | "instructor" | "admin";

interface UserAccount {
  id: string;
  fullName: string;
  email: string;
  role: Role;
  scope: string;
  status: "Active" | "Inactive";
  createdAt: string;
}

// --- Initial Admin Mock User Accounts ---
const INITIAL_USERS: UserAccount[] = [
  { id: "usr_9901", fullName: "Alex Rivera", email: "alex.admin@sprintsight.dev", role: "admin", scope: "System Global", status: "Active", createdAt: "2026-01-10" },
  { id: "usr_1042", fullName: "Dr. Sarah Jenkins", email: "s.jenkins@university.edu", role: "instructor", scope: "CS480 - Software Eng", status: "Active", createdAt: "2026-01-15" },
  { id: "usr_1043", fullName: "Prof. Michael Chen", email: "m.chen@university.edu", role: "instructor", scope: "CS482 - Senior Design", status: "Active", createdAt: "2026-01-18" },
  { id: "usr_2081", fullName: "Jane Doe", email: "jane.doe@student.edu", role: "student", scope: "Team Alpha (CS480)", status: "Active", createdAt: "2026-02-01" },
  { id: "usr_2082", fullName: "John Smith", email: "john.smith@student.edu", role: "student", scope: "Team Beta (CS480)", status: "Active", createdAt: "2026-02-01" },
  { id: "usr_2083", fullName: "Elena Rostova", email: "e.rostova@student.edu", role: "student", scope: "Team Delta (CS482)", status: "Inactive", createdAt: "2026-02-03" },
  { id: "usr_2084", fullName: "Marcus Vance", email: "m.vance@student.edu", role: "student", scope: "Team Zeta (CS482)", status: "Active", createdAt: "2026-02-04" },
];

// --- Instructor Mock Data ---
const instructorChartData = [
  { name: "Sprint 1", score: 62 },
  { name: "Sprint 2", score: 67 },
  { name: "Sprint 3", score: 71 },
  { name: "Sprint 4", score: 73 },
  { name: "Sprint 5", score: 78 },
  { name: "Sprint 6", score: 76 },
  { name: "Sprint 7", score: 81 },
];

const instructorAlerts = [
  { team: "Team Delta", msg: "One member has 0 commits in Sprint 3", critical: true },
  { team: "Team Zeta", msg: "Uneven workload distribution detected", critical: false },
  { team: "Team Eta", msg: "Missing Jira task updates for 5 days", critical: false },
  { team: "Team Delta", msg: "Peer evaluation scores significantly diverge", critical: true },
  { team: "Team Theta", msg: "No documentation updates in Sprint 4", critical: false },
];

// --- Student Mock Data ---
const studentChartData = [
  { name: "Sprint 1", myScore: 78, teamAvg: 74, target: 85 },
  { name: "Sprint 2", myScore: 82, teamAvg: 79, target: 85 },
  { name: "Sprint 3", myScore: 85, teamAvg: 81, target: 85 },
  { name: "Sprint 4", myScore: 84, teamAvg: 82, target: 85 },
  { name: "Sprint 5", myScore: 88, teamAvg: 85, target: 85 },
];

const studentActionCenter = [
  { title: "Submit Sprint 5 Peer Evaluation", due: "Due in 2 days", icon: CheckSquare, badge: "Action Required", color: "text-amber-600 bg-amber-50 border-amber-200" },
  { title: "1 GitHub PR Waiting for Team Review", due: "PR #42 - Auth Flow Integration", icon: FileCode, badge: "Pending Review", color: "text-blue-600 bg-blue-50 border-blue-200" },
  { title: "Instructor Feedback on Artifact #3", due: "Posted yesterday", icon: MessageSquare, badge: "New Feedback", color: "text-emerald-600 bg-emerald-50 border-emerald-200" },
];

const studentSprintHistory = [
  { sprint: "Sprint 5 (Current)", myScore: 88, teamScore: 85, stats: "14 commits · 3 PRs · 8 tasks", feedback: "Strong backend performance; technical design document clear.", status: "In Progress" },
  { sprint: "Sprint 4", myScore: 84, teamScore: 82, stats: "11 commits · 2 PRs · 6 tasks", feedback: "Good effort in API integration. Ensure tests cover edge cases.", status: "Completed" },
  { sprint: "Sprint 3", myScore: 85, teamScore: 81, stats: "13 commits · 4 PRs · 7 tasks", feedback: "Excellent code quality. Great leadership in group discussions.", status: "Completed" },
  { sprint: "Sprint 2", myScore: 82, teamScore: 79, stats: "9 commits · 2 PRs · 5 tasks", feedback: "Consistent progress. Work on documentation completeness.", status: "Completed" },
  { sprint: "Sprint 1", myScore: 78, teamScore: 74, stats: "8 commits · 1 PR · 4 tasks", feedback: "Good baseline setup. Team sync can be improved.", status: "Completed" },
];

export default function DashboardPage() {
  const [role, setRole] = useState<Role>("instructor");
  const [fullName, setFullName] = useState<string>("");
  const [mounted, setMounted] = useState(false);

// Admin IAM State
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRoleFilter, setSelectedRoleFilter] = useState<string>("all");
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<string>("all");
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserAccount | null>(null);

  // Form State for User Creation / Edit
  const [formData, setFormData] = useState({ fullName: "", email: "", role: "student" as Role, scope: "", status: "Active" as "Active" | "Inactive" });

  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as Role | null;
    const savedName = sessionStorage.getItem("sprintsight-auth-name");
    const token = sessionStorage.getItem("sprintsight-access-token");

    if (savedRole) setRole(savedRole);
    if (savedName) setFullName(savedName);

    // Fetch users from FastAPI backend if logged in as Admin
    if (savedRole === "admin" && token) {
      fetch("http://localhost:8000/api/v1/admin/users", {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
        .then((res) => res.json())
        .then((data) => {
          // Map backend response (snake_case) to UI model (camelCase)
          const mappedUsers: UserAccount[] = data.map((u: any) => ({
            id: u.id,
            fullName: u.full_name,
            email: u.email,
            role: u.role,
            scope: u.role === "admin" ? "System Global" : "Assigned Course",
            status: u.is_active ? "Active" : "Inactive",
            createdAt: u.created_at || "N/A",
          }));
          setUsers(mappedUsers);
        })
        .catch((err) => console.error("Error fetching admin user list:", err))
        .finally(() => setMounted(true));
    } else {
      setMounted(true);
    }
  }, []);

  // Filtered Users for Admin Table
  const filteredUsers = useMemo(() => {
    return users.filter((user) => {
      const matchesSearch =
        user.fullName.toLowerCase().includes(searchQuery.toLowerCase()) ||
        user.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
        user.id.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesRole = selectedRoleFilter === "all" || user.role === selectedRoleFilter;
      const matchesStatus = selectedStatusFilter === "all" || user.status === selectedStatusFilter;

      return matchesSearch && matchesRole && matchesStatus;
    });
  }, [users, searchQuery, selectedRoleFilter, selectedStatusFilter]);

  // Admin Actions
  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = sessionStorage.getItem("sprintsight-access-token");

    try {
      const res = await fetch("http://localhost:8000/api/v1/admin/users", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          email: formData.email,
          full_name: formData.fullName,
          role: formData.role,
          password: "TemporaryPassword123!", // Temp password for new identity
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        alert(`Error creating user: ${err.detail || "Failed request"}`);
        return;
      }

      const newUser = await res.json();

      // Append newly created database user to UI state
      const createdUserRecord: UserAccount = {
        id: newUser.id,
        fullName: newUser.full_name,
        email: newUser.email,
        role: newUser.role,
        scope: formData.scope || (newUser.role === "student" ? "Unassigned Team" : "CS Course"),
        status: newUser.is_active ? "Active" : "Inactive",
        createdAt: new Date().toISOString().split("T")[0],
      };

      setUsers((prev) => [createdUserRecord, ...prev]);
      setIsCreateModalOpen(false);
      setFormData({ fullName: "", email: "", role: "student", scope: "", status: "Active" });
    } catch (err) {
      console.error("Failed to create user", err);
    }
  };

  const handleUpdateRole = async (user: UserAccount, newRole: Role) => {
    const token = sessionStorage.getItem("sprintsight-access-token");

    try {
      const res = await fetch(`http://localhost:8000/api/v1/admin/users/${user.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ role: newRole }),
      });

      if (res.ok) {
        setUsers((prev) =>
          prev.map((u) => (u.id === user.id ? { ...u, role: newRole } : u))
        );
        setEditingUser(null);
      }
    } catch (err) {
      console.error("Failed to update user role", err);
    }
  };

  const handleDeleteUser = async (userId: string) => {
    if (!confirm("Are you sure you want to delete this identity record?")) return;

    const token = sessionStorage.getItem("sprintsight-access-token");

    try {
      const res = await fetch(`http://localhost:8000/api/v1/admin/users/${userId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (res.ok) {
        setUsers((prev) => prev.filter((u) => u.id !== userId));
      } else {
        alert("Failed to delete user record from database.");
      }
    } catch (err) {
      console.error("Failed to delete user", err);
    }
  };

  if (!mounted) return null;

  // ------------------------------------------------------------------
  // ADMIN IAM DASHBOARD (Dynatrace Dark-Mode Aesthetic)
  // ------------------------------------------------------------------
  if (role === "admin") {
    return (
      <div className="bg-[#0b0f17] text-slate-200 min-h-screen p-6 font-mono text-xs">
        {/* Header & Stats Overview */}
        <div className="mb-6 border-b border-slate-800 pb-5 flex justify-between items-center">
          <div>
            <div className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-cyan-400" />
              <h1 className="text-xl font-bold tracking-tight text-white font-sans">Identity & Access Management (IAM)</h1>
            </div>
            <p className="text-slate-400 mt-1 font-sans text-sm">
              Manage accounts, control scope permissions, and update user roles.
            </p>
          </div>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="flex items-center gap-2 bg-cyan-600 hover:bg-cyan-500 text-white font-semibold font-sans px-4 py-2 rounded-md transition-colors shadow-sm"
          >
            <UserPlus className="w-4 h-4" /> Provision New Identity
          </button>
        </div>

        {/* Global Toolbar: Search & Filters */}
        <div className="bg-[#121824] border border-slate-800 rounded-lg p-3 mb-4 flex flex-wrap items-center justify-between gap-3 shadow-inner">
          <div className="flex items-center gap-3 flex-1 min-w-[280px]">
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search subject by name, email, or user ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-[#0b0f17] border border-slate-700 rounded pl-9 pr-3 py-1.5 text-slate-200 focus:outline-none focus:border-cyan-500 transition-colors"
              />
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 bg-[#0b0f17] border border-slate-700 px-3 py-1.5 rounded">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <span className="text-slate-400 font-sans">Role:</span>
              <select
                value={selectedRoleFilter}
                onChange={(e) => setSelectedRoleFilter(e.target.value)}
                className="bg-transparent text-slate-200 focus:outline-none cursor-pointer"
              >
                <option value="all" className="bg-[#0b0f17]">All Roles</option>
                <option value="student" className="bg-[#0b0f17]">Student</option>
                <option value="instructor" className="bg-[#0b0f17]">Instructor</option>
                <option value="admin" className="bg-[#0b0f17]">Admin</option>
              </select>
            </div>

            <div className="flex items-center gap-2 bg-[#0b0f17] border border-slate-700 px-3 py-1.5 rounded">
              <span className="text-slate-400 font-sans">Status:</span>
              <select
                value={selectedStatusFilter}
                onChange={(e) => setSelectedStatusFilter(e.target.value)}
                className="bg-transparent text-slate-200 focus:outline-none cursor-pointer"
              >
                <option value="all" className="bg-[#0b0f17]">All Statuses</option>
                <option value="Active" className="bg-[#0b0f17]">Active</option>
                <option value="Inactive" className="bg-[#0b0f17]">Inactive</option>
              </select>
            </div>
          </div>
        </div>

        {/* Dynatrace-Style Data Grid Table */}
        <div className="bg-[#121824] border border-slate-800 rounded-lg overflow-hidden shadow-xl">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800 bg-[#172030] text-slate-300 uppercase tracking-wider text-[11px] font-semibold">
                  <th className="py-3 px-4">Subject (Identity)</th>
                  <th className="py-3 px-4">Scope</th>
                  <th className="py-3 px-4">Assigned Role</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4">Created Date</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-sans text-xs">
                {filteredUsers.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-slate-500">
                      No matching identity records found.
                    </td>
                  </tr>
                ) : (
                  filteredUsers.map((user) => (
                    <tr key={user.id} className="hover:bg-slate-800/40 transition-colors group">
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-white">{user.fullName}</div>
                        <div className="text-slate-400 text-[11px] font-mono">{user.email}</div>
                        <div className="text-slate-600 text-[10px] font-mono">ID: {user.id}</div>
                      </td>
                      <td className="py-3.5 px-4 font-mono text-slate-300">
                        <span className="bg-slate-900 border border-slate-700/60 px-2 py-0.5 rounded text-[11px]">
                          {user.scope}
                        </span>
                      </td>
                      <td className="py-3.5 px-4">
                        {user.role === "admin" && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-950/80 text-purple-300 border border-purple-700/60">
                            ADMIN
                          </span>
                        )}
                        {user.role === "instructor" && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-cyan-950/80 text-cyan-300 border border-cyan-700/60">
                            INSTRUCTOR
                          </span>
                        )}
                        {user.role === "student" && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-700/60">
                            STUDENT
                          </span>
                        )}
                      </td>
                      <td className="py-3.5 px-4">
                        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] ${user.status === "Active" ? "text-emerald-400 bg-emerald-950/30" : "text-slate-400 bg-slate-900"}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${user.status === "Active" ? "bg-emerald-400" : "bg-slate-500"}`} />
                          {user.status}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 font-mono text-slate-400 text-[11px]">
                        {user.createdAt}
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => setEditingUser(user)}
                            className="p-1.5 text-slate-400 hover:text-cyan-400 hover:bg-slate-800 rounded transition-colors"
                            title="Edit Role"
                          >
                            <Edit3 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleDeleteUser(user.id)}
                            className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded transition-colors"
                            title="Delete User"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Footer */}
          <div className="bg-[#172030] px-4 py-3 border-t border-slate-800 flex items-center justify-between text-slate-400 text-xs font-mono">
            <span>Showing {filteredUsers.length} of {users.length} identity records</span>
            <div className="flex items-center gap-2">
              <button disabled className="p-1 rounded bg-slate-800 text-slate-600 cursor-not-allowed">
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">1</span>
              <button disabled className="p-1 rounded bg-slate-800 text-slate-600 cursor-not-allowed">
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Provision User Modal */}
        {isCreateModalOpen && (
          <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
            <div className="bg-[#121824] border border-slate-800 rounded-lg w-full max-w-md p-6 font-sans">
              <div className="flex justify-between items-center pb-4 border-b border-slate-800">
                <h2 className="text-lg font-bold text-white">Provision New Account</h2>
                <button onClick={() => setIsCreateModalOpen(false)} className="text-slate-400 hover:text-white">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <form onSubmit={handleCreateUser} className="mt-4 space-y-4 text-xs">
                <div>
                  <label className="block text-slate-400 mb-1">Full Name</label>
                  <input
                    type="text"
                    required
                    value={formData.fullName}
                    onChange={(e) => setFormData({ ...formData, fullName: e.target.value })}
                    className="w-full bg-[#0b0f17] border border-slate-700 rounded px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                    placeholder="e.g. Alex Taylor"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Email Address</label>
                  <input
                    type="email"
                    required
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    className="w-full bg-[#0b0f17] border border-slate-700 rounded px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                    placeholder="alex@university.edu"
                  />
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Assigned Role</label>
                  <select
                    value={formData.role}
                    onChange={(e) => setFormData({ ...formData, role: e.target.value as Role })}
                    className="w-full bg-[#0b0f17] border border-slate-700 rounded px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                  >
                    <option value="student">Student</option>
                    <option value="instructor">Instructor</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-400 mb-1">Scope / Department</label>
                  <input
                    type="text"
                    value={formData.scope}
                    onChange={(e) => setFormData({ ...formData, scope: e.target.value })}
                    className="w-full bg-[#0b0f17] border border-slate-700 rounded px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                    placeholder="e.g. CS480 - Team Alpha"
                  />
                </div>
                <div className="flex justify-end gap-2 pt-4 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setIsCreateModalOpen(false)}
                    className="px-4 py-2 rounded border border-slate-700 text-slate-300 hover:bg-slate-800"
                  >
                    Cancel
                  </button>
                  <button type="submit" className="px-4 py-2 rounded bg-cyan-600 hover:bg-cyan-500 text-white font-semibold">
                    Create User
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Edit Role Modal */}
        {editingUser && (
          <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
            <div className="bg-[#121824] border border-slate-800 rounded-lg w-full max-w-sm p-6 font-sans">
              <div className="flex justify-between items-center pb-3 border-b border-slate-800">
                <h2 className="text-base font-bold text-white">Modify User Role</h2>
                <button onClick={() => setEditingUser(null)} className="text-slate-400 hover:text-white">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="mt-4 space-y-3 text-xs">
                <p className="text-slate-300">Target User: <span className="font-semibold text-white">{editingUser.fullName}</span></p>
                <div>
                  <label className="block text-slate-400 mb-1">Select New Role</label>
                  <select
                    defaultValue={editingUser.role}
                    onChange={(e) => handleUpdateRole(editingUser, e.target.value as Role)}
                    className="w-full bg-[#0b0f17] border border-slate-700 rounded px-3 py-2 text-white focus:outline-none focus:border-cyan-500"
                  >
                    <option value="student">Student</option>
                    <option value="instructor">Instructor</option>
                    <option value="admin">Admin</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // Render Student Dashboard
  if (role === "student") {
    return (
      <div className="p-8 max-w-7xl mx-auto space-y-8 bg-slate-50 min-h-screen">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-slate-900">My Dashboard</h1>
          <p className="text-slate-500 mt-1">
            Welcome back, <span className="font-semibold text-slate-700">{fullName || "Student"}</span>. Here is your project overview for <span className="font-semibold text-slate-700">Team Alpha — E-Commerce Platform</span>.
          </p>
        </div>

        {/* Top Metrics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm font-medium text-slate-500">Current Grade</p>
                <h3 className="text-3xl font-bold text-slate-900 mt-1">88<span className="text-lg font-normal text-slate-400">/100</span></h3>
              </div>
              <div className="p-2 bg-emerald-50 rounded-lg text-emerald-600">
                <Award className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs font-medium text-emerald-600">↗ On Track for Grade A</p>
          </div>

          <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm font-medium text-slate-500">Sprint Countdown</p>
                <h3 className="text-3xl font-bold text-slate-900 mt-1">4 Days</h3>
              </div>
              <div className="p-2 bg-blue-50 rounded-lg text-blue-600">
                <Clock className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs font-medium text-slate-500">Sprint 5 Ends Friday, 11:59 PM</p>
          </div>

          <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm font-medium text-slate-500">My Tasks</p>
                <h3 className="text-3xl font-bold text-slate-900 mt-1">8 / 10</h3>
              </div>
              <div className="p-2 bg-indigo-50 rounded-lg text-indigo-600">
                <CheckCircle2 className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs font-medium text-indigo-600">80% Jira Tasks Completed</p>
          </div>

          <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm font-medium text-slate-500">Contribution Share</p>
                <h3 className="text-3xl font-bold text-slate-900 mt-1">26%</h3>
              </div>
              <div className="p-2 bg-purple-50 rounded-lg text-purple-600">
                <GitCommit className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs font-medium text-purple-600">14 Commits · 3 PRs Merged</p>
          </div>
        </div>

        {/* Middle Section: Chart & Action Center */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-white p-6 rounded-xl border border-slate-100 shadow-sm">
            <h3 className="text-lg font-bold text-slate-900 mb-6">Performance Trend (My Score vs. Team)</h3>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={studentChartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} dy={10} />
                  <YAxis domain={[50, 100]} axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                  <Tooltip contentStyle={{ borderRadius: "8px", border: "none", boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)" }} />
                  <Legend verticalAlign="top" height={36} />
                  <Line type="monotone" name="My Score" dataKey="myScore" stroke="#2563eb" strokeWidth={3} dot={{ r: 4 }} />
                  <Line type="monotone" name="Team Average" dataKey="teamAvg" stroke="#94a3b8" strokeWidth={2} strokeDasharray="4 4" dot={false} />
                  <Line type="monotone" name="Target (85+)" dataKey="target" stroke="#10b981" strokeWidth={1.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Action Center</h3>
            <div className="flex-1 overflow-y-auto space-y-3">
              {studentActionCenter.map((item, idx) => (
                <div key={idx} className={`p-3.5 rounded-xl border ${item.color} transition-all hover:shadow-xs`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-700">
                      {item.badge}
                    </span>
                    <item.icon className="w-4 h-4 text-slate-500" />
                  </div>
                  <p className="text-sm font-semibold text-slate-900 mt-1">{item.title}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{item.due}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Bottom Section */}
        <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm">
          <h3 className="text-lg font-bold text-slate-900 mb-6">My Sprint Breakdown</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="pb-3 text-sm font-semibold text-slate-500">Sprint</th>
                  <th className="pb-3 text-sm font-semibold text-slate-500">My Score</th>
                  <th className="pb-3 text-sm font-semibold text-slate-500">Team Score</th>
                  <th className="pb-3 text-sm font-semibold text-slate-500">Contributions</th>
                  <th className="pb-3 text-sm font-semibold text-slate-500">AI Feedback Summary</th>
                  <th className="pb-3 text-sm font-semibold text-slate-500 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {studentSprintHistory.map((row, idx) => (
                  <tr key={idx} className="border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors">
                    <td className="py-4 text-sm font-semibold text-slate-900">{row.sprint}</td>
                    <td className="py-4 text-sm font-bold text-blue-600">{row.myScore}/100</td>
                    <td className="py-4 text-sm text-slate-600">{row.teamScore}/100</td>
                    <td className="py-4 text-xs text-slate-600">{row.stats}</td>
                    <td className="py-4 text-xs text-slate-600 max-w-xs truncate">{row.feedback}</td>
                    <td className="py-4 text-right">
                      <button type="button" className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800">
                        View Details <ArrowRight className="w-3 h-3" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  }

  // Render Instructor Dashboard
  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 bg-slate-50 min-h-screen">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-slate-500 mt-1">
          Welcome back, <span className="font-semibold text-slate-700">{fullName || "Instructor"}</span>. Here&apos;s your assessment overview.
        </p>
      </div>

      {/* Top Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {[
          { title: "Total Projects", value: "24", sub: "+3 this semester", icon: FolderOpen, color: "text-blue-500" },
          { title: "Active Sprints", value: "12", sub: "4 due this week", icon: Activity, color: "text-indigo-500" },
          { title: "Assessments Completed", value: "87", sub: "+12 this week", icon: FileCheck, color: "text-emerald-500" },
          { title: "Collaboration Alerts", value: "5", sub: "2 critical", icon: AlertTriangle, color: "text-rose-500" },
        ].map((metric, idx) => (
          <div key={idx} className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm font-medium text-slate-500">{metric.title}</p>
                <h3 className="text-3xl font-bold text-slate-900 mt-1">{metric.value}</h3>
              </div>
              <div className={`p-2 bg-slate-50 rounded-lg ${metric.color}`}>
                <metric.icon className="w-5 h-5" />
              </div>
            </div>
            <p className={`text-xs ${metric.title === "Collaboration Alerts" ? "text-rose-500" : "text-emerald-600"} font-medium`}>
              {metric.title !== "Collaboration Alerts" && "↗ "}
              {metric.sub}
            </p>
          </div>
        ))}
      </div>

      {/* Middle Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white p-6 rounded-xl border border-slate-100 shadow-sm">
          <h3 className="text-lg font-bold text-slate-900 mb-6">Average Scores Over Time</h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={instructorChartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} dy={10} />
                <YAxis domain={[50, 100]} axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                <Tooltip contentStyle={{ borderRadius: "8px", border: "none", boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)" }} />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke="#1e3a8a"
                  strokeWidth={3}
                  dot={{ r: 4, fill: "#1e3a8a", strokeWidth: 0 }}
                  activeDot={{ r: 6, fill: "#3b82f6", strokeWidth: 0 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col">
          <h3 className="text-lg font-bold text-slate-900 mb-4">Collaboration Alerts</h3>
          <div className="flex-1 overflow-y-auto pr-2 space-y-3">
            {instructorAlerts.map((alert, idx) => (
              <div key={idx} className="p-3 rounded-lg border border-slate-100 bg-slate-50 flex items-start gap-3">
                <div className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${alert.critical ? "bg-rose-500" : "bg-amber-400"}`} />
                <div>
                  <p className="text-xs font-semibold text-slate-800">{alert.team}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{alert.msg}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}