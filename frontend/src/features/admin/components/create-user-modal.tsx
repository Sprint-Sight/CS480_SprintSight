"use client";

import React, { useState } from "react";
import { X, Layers, Users, Shield } from "lucide-react";
import { Role, CreateUserData, ProjectOption } from "../types";
import { ConfirmationModal } from "@/components/ui/confirmation-modal";

interface CreateUserModalProps {
  isOpen: boolean;
  projects: ProjectOption[];
  onClose: () => void;
  onCreate: (data: CreateUserData) => Promise<void>;
}

export function CreateUserModal({ isOpen, projects, onClose, onCreate }: CreateUserModalProps) {
  const [formData, setFormData] = useState<CreateUserData>({
    fullName: "",
    email: "",
    role: "student",
    projectId: "",
    courseCode: "CS480",
    section: "001",
  });
  const [showConfirm, setShowConfirm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleProjectSelect = (selectedId: string) => {
    const selected = projects.find((p) => p.id === selectedId);
    setFormData((prev) => ({
      ...prev,
      projectId: selectedId,
      courseCode: selected ? selected.courseCode : prev.courseCode,
      section: selected ? selected.section : prev.section,
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setShowConfirm(true);
  };

  const handleConfirmedCreate = async () => {
    setShowConfirm(false);
    setIsSubmitting(true);
    await onCreate(formData);
    setIsSubmitting(false);
    setFormData({
      fullName: "",
      email: "",
      role: "student",
      projectId: "",
      courseCode: "CS480",
      section: "001",
    });
    onClose();
  };

  return (
    <>
      <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
        <div className="bg-white rounded-xl border border-slate-100 shadow-xl w-full max-w-md p-6">
          <div className="flex justify-between items-center pb-4 border-b border-slate-100">
            <h2 className="text-lg font-bold text-slate-900">Provision New User</h2>
            <button
              onClick={onClose}
              className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Full Name</label>
              <input
                type="text"
                required
                value={formData.fullName}
                onChange={(e) => setFormData({ ...formData, fullName: e.target.value })}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all"
                placeholder="e.g. Alex Taylor"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Email Address</label>
              <input
                type="email"
                required
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all"
                placeholder="alex@university.edu"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-blue-600" />
                Assigned Role
              </label>
              <select
                value={formData.role}
                onChange={(e) => setFormData({ ...formData, role: e.target.value as Role })}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all cursor-pointer"
              >
                <option value="student">Student</option>
                <option value="instructor">Instructor</option>
                <option value="admin">Admin</option>
              </select>
            </div>

            {formData.role !== "admin" && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center gap-1">
                    <Layers className="w-3.5 h-3.5 text-blue-600" /> Course Code
                  </label>
                  <input
                    type="text"
                    required
                    value={formData.courseCode}
                    onChange={(e) => setFormData({ ...formData, courseCode: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all"
                    placeholder="CS480"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Section</label>
                  <input
                    type="text"
                    required
                    value={formData.section}
                    onChange={(e) => setFormData({ ...formData, section: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all"
                    placeholder="001"
                  />
                </div>
              </div>
            )}

            {formData.role === "student" && (
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center gap-1.5">
                  <Users className="w-3.5 h-3.5 text-purple-600" />
                  Assigned Project / Team
                </label>
                <select
                  value={formData.projectId}
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

            <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-lg border border-slate-200 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-sm font-semibold text-white transition-colors shadow-xs"
              >
                {isSubmitting ? "Provisioning..." : "Create User"}
              </button>
            </div>
          </form>
        </div>
      </div>

      <ConfirmationModal
        isOpen={showConfirm}
        onClose={() => setShowConfirm(false)}
        onConfirm={handleConfirmedCreate}
        title="Confirm User Provisioning"
        message={`Provision a new ${formData.role.toUpperCase()} account for ${formData.fullName} (${formData.email})?`}
        confirmText="Yes, Create Account"
        cancelText="Cancel"
      />
    </>
  );
}