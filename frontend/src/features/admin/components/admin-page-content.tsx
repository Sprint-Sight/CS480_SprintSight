"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Shield,
  LogOut,
  UserPlus,
  ClipboardList,
  Search,
  Filter,
  Users,
  UserCheck,
  FolderGit2,
  Upload,
} from "lucide-react";
import { UserAccount, CreateUserData, EditUserData } from "@/features/admin/types";
import { CreateUserModal } from "@/features/admin/components/create-user-modal";
import { UserRowActions } from "@/features/admin/components/user-row-actions";
import { EditUserModal } from "@/features/admin/components/edit-user-modal";
import { ConfirmationModal } from "@/components/ui/confirmation-modal";
import { PageSkeleton } from "@/components/ui/page-skeleton";
import { useAdminDirectory } from "@/features/admin/hooks/use-admin-directory";
import { CSVImportModal } from "@/features/projects/components/csv-import-modal";
import { useStudentImport } from "@/features/projects/hooks/use-student-import";
import { getErrorMessage } from "@/lib/api/client";
import { signOut, useSession } from "@/lib/auth/session";
import { restoreSession } from "@/features/auth/login-api";
import {
  activateUser,
  createUser,
  deactivateUser,
  getUser,
  listCourses,
  listUsers,
  resetUserPassword,
  updateUser,
  type AdminCourseOption,
} from "@/features/admin/admin-api";
import { MIN_PASSWORD_LENGTH, ResetPasswordModal } from "@/features/admin/components/reset-password-modal";

export function AdminPageContent() {
  const router = useRouter();
  const session = useSession();
  const adminName = session?.user?.fullName ?? "";
  const currentEmail = session?.user?.email ?? "";
  const [mounted, setMounted] = useState(false);

  // Identity & State
  const [users, setUsers] = useState<UserAccount[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedRoleFilter, setSelectedRoleFilter] = useState("all");
  const [selectedStatusFilter, setSelectedStatusFilter] = useState("Active");
  const [courses, setCourses] = useState<AdminCourseOption[]>([]);
  const [loadingCourses, setLoadingCourses] = useState(false);

  // Modals state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [selectedCourseForImport, setSelectedCourseForImport] = useState<string>("");
  const [editingUser, setEditingUser] = useState<UserAccount | null>(null);
  const [userToDeactivate, setUserToDeactivate] = useState<UserAccount | null>(null);
  const [userToResetPassword, setUserToResetPassword] = useState<UserAccount | null>(null);
  const [resetPasswordInput, setResetPasswordInput] = useState("");
  const [isResettingPassword, setIsResettingPassword] = useState(false);

  // Student import hook
  const { isLoading: isImporting, error: importError, parsedRows, validateAndPreview, submitImport, clearState: clearImportState } = useStudentImport();

  const showNotification = (type: "success" | "error", message: string) => {
    if (type === "success") {
      toast.success(message);
    } else {
      toast.error(message);
    }
  };

  const handleEditUser = async (user: UserAccount) => {
    try {
      const freshUser = await getUser(user.id);
      setEditingUser({ ...user, ...freshUser, createdAt: user.createdAt });
    } catch (error) {
      showNotification("error", getErrorMessage(error, "Failed to fetch user details."));
    }
  };

  // 1. GET /users - Fetch User Directory
  const fetchUsers = useCallback(async () => {
    setLoadingUsers(true);
    try {
      setUsers(await listUsers());
    } catch (error) {
      showNotification("error", getErrorMessage(error, "Failed to load directory."));
    } finally {
      setLoadingUsers(false);
    }
  }, []);

  // Fetch courses for bulk import dropdown
  const fetchCourses = useCallback(async () => {
    setLoadingCourses(true);
    try {
      setCourses(await listCourses());
    } catch {
      // Silently fail for courses - not critical for admin page
    } finally {
      setLoadingCourses(false);
    }
  }, []);

  useEffect(() => {
    let isCurrent = true;

    void restoreSession().then((restored) => {
      if (!isCurrent) return;
      if (restored?.user?.role !== "admin") {
        router.replace("/login");
        return;
      }

      fetchUsers();
      fetchCourses();
      setMounted(true);
    });

    return () => {
      isCurrent = false;
    };
  }, [router, fetchUsers, fetchCourses]);

  // Signing out in another tab clears the shared session; follow it here.
  useEffect(() => {
    if (mounted && !session) router.replace("/login");
  }, [mounted, session, router]);

  // 2. POST /users - Create Managed User
  const handleCreateUser = async (data: CreateUserData): Promise<boolean> => {
    try {
      const createdRecord = await createUser(data);
      setUsers((prev) => [createdRecord, ...prev]);
      if (createdRecord.role === "student" && createdRecord.signupEmailSent) {
        showNotification(
          "success",
          `Student ${createdRecord.fullName} was created. A first-time password setup link was queued for delivery to ${createdRecord.email}.`,
        );
      } else if (createdRecord.role === "student") {
        showNotification(
          "error",
          `Student ${createdRecord.fullName} was created, but the setup email was not queued. Check SMTP configuration and backend logs.`,
        );
      } else {
        showNotification("success", `User ${createdRecord.fullName} provisioned successfully.`);
      }
      return true;
    } catch (error) {
      showNotification("error", getErrorMessage(error, "Failed to create user."));
      return false;
    }
  };

  // 3. PATCH /users/{user_id} - Update Managed User
  const handleUpdateUser = async (user: UserAccount, data: EditUserData): Promise<boolean> => {
    try {
      const updatedUser = await updateUser(user, data);
      setUsers((prev) =>
        prev.map((u) =>
          u.id === user.id
            ? { ...u, fullName: updatedUser.fullName, email: updatedUser.email, role: updatedUser.role }
            : u,
        ),
      );
      showNotification("success", `Updated identity details for ${updatedUser.fullName}.`);
      return true;
    } catch (error) {
      showNotification("error", getErrorMessage(error, "Failed to update record."));
      return false;
    }
  };

  // 4. DELETE /users/{user_id} - Soft-delete (Deactivate) User
  const handleDeactivateUser = async () => {
    if (!userToDeactivate) return;
    try {
      await deactivateUser(userToDeactivate.id);
      setUsers((prev) =>
        prev.map((u) => (u.id === userToDeactivate.id ? { ...u, status: "Inactive" } : u)),
      );
      showNotification("success", `User ${userToDeactivate.fullName} deactivated.`);
    } catch (error) {
      showNotification("error", getErrorMessage(error, "Failed to deactivate record."));
    } finally {
      setUserToDeactivate(null);
    }
  };

  // 5. POST /users/{user_id}/activate - Reactivate User Account
  const handleActivateUser = async (user: UserAccount) => {
    try {
      await activateUser(user.id);
      setUsers((prev) => prev.map((u) => (u.id === user.id ? { ...u, status: "Active" } : u)));
      showNotification("success", `User ${user.fullName} reactivated.`);
    } catch (error) {
      showNotification("error", getErrorMessage(error, "Failed to activate user."));
    }
  };

  // 6. POST /users/{user_id}/reset-password - Admin Reset Password
  const handleResetPassword = async () => {
    if (!userToResetPassword || isResettingPassword) return;
    if (resetPasswordInput.length < MIN_PASSWORD_LENGTH) {
      showNotification("error", `The new password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    setIsResettingPassword(true);
    try {
      await resetUserPassword(userToResetPassword.id, resetPasswordInput);
      showNotification("success", `Password reset successfully for ${userToResetPassword.fullName}.`);
      // Close only on success so a rejected password can be corrected in place.
      setUserToResetPassword(null);
      setResetPasswordInput("");
    } catch (error) {
      showNotification("error", getErrorMessage(error, "Failed to reset password."));
    } finally {
      setIsResettingPassword(false);
    }
  };

  const handleLogout = () => {
    signOut();
    router.replace("/login");
  };

  const { filteredUsers, stats } = useAdminDirectory(users, searchQuery, selectedRoleFilter, selectedStatusFilter);

  if (!mounted) return <PageSkeleton variant="table" />;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-8 bg-slate-50 min-h-screen">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">User & Project Directory</h1>
          <p className="text-slate-500 mt-1">
            Welcome back, <span className="font-semibold text-slate-700">{adminName || "System Admin"}</span>. Provision and manage user accounts.
          </p>
        </div>
        
        <div className="flex flex-wrap items-center gap-3 self-start md:self-auto">
          <Link
            href="/admin/audit-log"
            className="inline-flex items-center gap-2 bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 text-sm font-semibold px-4 py-2.5 rounded-xl transition-colors"
          >
            <ClipboardList className="w-4 h-4 text-slate-500" />
            Audit Log
          </Link>
          {courses.length > 0 && (
            <select
              value={selectedCourseForImport}
              onChange={(e) => setSelectedCourseForImport(e.target.value)}
              className="bg-white border border-slate-300 text-slate-700 text-sm font-semibold px-4 py-2.5 rounded-xl transition-colors cursor-pointer hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600"
            >
              <option value="">Select course for import...</option>
              {courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.code} - {course.title}
                </option>
              ))}
            </select>
          )}
          <button
            onClick={() => {
              if (courses.length === 0) {
                showNotification("error", "No courses available. Cannot import students.");
                return;
              }
              if (!selectedCourseForImport) {
                showNotification("error", "Please select a course first to import students.");
                return;
              }
              setIsImportModalOpen(true);
            }}
            disabled={courses.length === 0 || !selectedCourseForImport}
            className="inline-flex items-center gap-2 bg-white hover:bg-slate-100 disabled:opacity-50 disabled:cursor-not-allowed text-slate-700 border border-slate-300 text-sm font-semibold px-4 py-2.5 rounded-xl transition-colors cursor-pointer"
          >
            <Upload className="w-4 h-4 text-slate-500" />
            Import Students
          </button>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-4 py-2.5 rounded-xl shadow-xs transition-colors cursor-pointer"
          >
            <UserPlus className="w-4 h-4" />
            Provision New User
          </button>
          <button
            onClick={handleLogout}
            className="inline-flex items-center gap-2 bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 text-sm font-semibold px-4 py-2.5 rounded-xl transition-colors cursor-pointer"
            title="Sign Out"
          >
            <LogOut className="w-4 h-4 text-slate-500" />
            Sign Out
          </button>
        </div>
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

      {/* Directory Table */}
      <div className="bg-white rounded-xl border border-slate-100 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/50 text-slate-500 text-xs font-semibold">
                <th className="py-3.5 px-6">User Identity</th>
                <th className="py-3.5 px-6">Role</th>
                <th className="py-3.5 px-6">Status</th>
                <th className="py-3.5 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-slate-500 text-xs">
                    {loadingUsers ? "Loading user records..." : "No matching users found."}
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
                      <td className="py-4 px-6 text-right">
                        <UserRowActions
                          userName={user.fullName}
                          isActive={user.status === "Active"}
                          isSelf={isSelf}
                          onEdit={() => handleEditUser(user)}
                          onResetPassword={() => {
                            setUserToResetPassword(user);
                            setResetPasswordInput("");
                          }}
                          onDeactivate={() => setUserToDeactivate(user)}
                          onActivate={() => handleActivateUser(user)}
                        />
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
        onClose={() => setIsCreateModalOpen(false)}
        onCreate={handleCreateUser}
      />

      {editingUser && (
        <EditUserModal
          user={editingUser}
          onClose={() => setEditingUser(null)}
          onSave={(user, data) => handleUpdateUser(user, data)}
        />
      )}

      {/* Deactivation Confirmation Modal */}
      <ConfirmationModal
        isOpen={Boolean(userToDeactivate)}
        onClose={() => setUserToDeactivate(null)}
        onConfirm={handleDeactivateUser}
        title="Deactivate User Account"
        message={`Are you sure you want to deactivate ${userToDeactivate?.fullName}? This soft-deletes their account and cleans up active enrollments/memberships.`}
        confirmText="Deactivate"
        cancelText="Cancel"
      />

      {/* Password Reset Modal */}
      <ResetPasswordModal
        user={userToResetPassword}
        password={resetPasswordInput}
        isSubmitting={isResettingPassword}
        onPasswordChange={setResetPasswordInput}
        onCancel={() => {
          if (isResettingPassword) return;
          setUserToResetPassword(null);
          setResetPasswordInput("");
        }}
        onSubmit={() => void handleResetPassword()}
      />

      {/* CSV Import Modal - For bulk student import */}
      {selectedCourseForImport && (
        <CSVImportModal
          isOpen={isImportModalOpen}
          courseId={selectedCourseForImport}
          courseName={courses.find((c) => c.id === selectedCourseForImport)?.title || ""}
          onClose={() => {
            setIsImportModalOpen(false);
            clearImportState();
          }}
          onValidatePreview={validateAndPreview}
          onSubmit={submitImport}
          isLoading={isImporting}
          error={importError}
          parsedRows={parsedRows}
        />
      )}
    </div>
  );
}