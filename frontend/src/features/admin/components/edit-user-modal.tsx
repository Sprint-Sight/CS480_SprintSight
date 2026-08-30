"use client";

import React, { useState, useEffect } from "react";
import { X, Layers, Users, Shield } from "lucide-react";
import { Role, UserAccount, ProjectOption, EditUserData } from "../types";
import { ConfirmationModal } from "@/components/ui/confirmation-modal";

interface EditUserModalProps {
  user: UserAccount | null;
  projects: ProjectOption[];
  onClose: () => void;
  onSave: (user: UserAccount, data: EditUserData) => Promise<void>;
}

export function EditUserModal({ user, projects, onClose, onSave }: EditUserModalProps) {
  const [role, setRole] = useState<Role>("student");
  const [projectId, setProjectId] = useState<string>("");
  const [courseCode, setCourseCode] = useState<string>("");
  const [section, setSection] = useState<string>("");
  const [showConfirm, setShowConfirm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (user) {
      setRole(user.role);
      setProjectId(user.projectId || "");
      setCourseCode(user.courseCode || "CS480");
      setSection(user.section || "001");
    }
  }, [user]);

  if (!user) return null;

  const handleProjectSelect = (selectedId: string) => {
    setProjectId(selectedId);
    const selected = projects.find((p) => p.id === selectedId);
    if (selected) {
      setCourseCode(selected.courseCode);
      setSection(selected.section);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setShowConfirm(true);
  };

  const handleConfirmedSave = async () => {
    setShowConfirm(false);
    setIsSubmitting(true);
    await onSave(user, {
      role,
      projectId: role === "student" ? projectId : undefined,
      courseCode: role !== "admin" ? courseCode : undefined,
      section: role !== "admin" ? section : undefined,
    });
    setIsSubmitting(false);
    onClose();
  };

  return (
    <>
      <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
        <div className="bg-white rounded-xl border border-slate-100 shadow-xl w-full max-w-md p-6">
          <div className="flex justify-between items-center pb-3 border-b border-slate-100">
            <h2 className="text-base font-bold text-slate-900">Modify Identity & Assignments</h2>
            <button
              onClick={onClose}
              className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            <div className="bg-slate-50 p-3 rounded-lg border border-slate-200">
              <p className="text-xs font-medium text-slate-500">Target User</p>
              <p className="font-semibold text-slate-900 text-sm mt-0.5">{user.fullName}</p>
              <p className="text-xs text-slate-500">{user.email}</p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-blue-600" />
                Assigned Role
              </label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all cursor-pointer"
              >
                <option value="student">Student</option>
                <option value="instructor">Instructor</option>
                <option value="admin">Admin</option>
              </select>
            </div>

            {role !== "admin" && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center gap-1">
                    <Layers className="w-3.5 h-3.5 text-blue-600" /> Course Code
                  </label>
                  <input
                    type="text"
                    required
                    value={courseCode}
                    onChange={(e) => setCourseCode(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all"
                    placeholder="CS480"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Section</label>
                  <input
                    type="text"
                    required
                    value={section}
                    onChange={(e) => setSection(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all"
                    placeholder="001"
                  />
                </div>
              </div>
            )}

            {role === "student" && (
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center gap-1.5">
                  <Users className="w-3.5 h-3.5 text-purple-600" />
                  Assigned Project / Team
                </label>
                <select
                  value={projectId}
                  onChange={(e) => handleProjectSelect(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all cursor-pointer"
                >
                  <option value="">Unassigned (No Team)</option>
                  {projects.map((proj) => (
                    <option key={proj.id} value={proj.id}>
                      {proj.projectName} ({proj.courseCode} - Sec {proj.section})
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-xs font-semibold text-white transition-colors shadow-xs"
              >
                {isSubmitting ? "Updating..." : "Save Assignment"}
              </button>
            </div>
          </form>
        </div>
      </div>

      <ConfirmationModal
        isOpen={showConfirm}
        onClose={() => setShowConfirm(false)}
        onConfirm={handleConfirmedSave}
        title="Confirm User Assignment Change"
        message={`Update role and team assignments for ${user.fullName}?`}
        confirmText="Yes, Update User"
        cancelText="Cancel"
      />
    </>
  );
}