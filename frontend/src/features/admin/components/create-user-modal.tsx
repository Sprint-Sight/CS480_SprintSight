"use client";

import React, { useState } from "react";
import { X, Shield, Key } from "lucide-react";
import { Role, CreateUserData } from "@/features/admin/types";
import { ConfirmationModal } from "@/components/ui/confirmation-modal";

interface CreateUserModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (data: CreateUserData) => Promise<void>;
}

export function CreateUserModal({ isOpen, onClose, onCreate }: CreateUserModalProps) {
  const [formData, setFormData] = useState<CreateUserData>({
    fullName: "",
    email: "",
    password: "", // Added password field
    role: "student",
  });
  const [showConfirm, setShowConfirm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setShowConfirm(true);
  };

  const handleConfirmedCreate = async () => {
    setShowConfirm(false);
    setIsSubmitting(true);
    await onCreate(formData);
    setIsSubmitting(false);
    
    // Reset form after successful creation
    setFormData({
      fullName: "",
      email: "",
      password: "",
      role: "student",
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
                <Key className="w-3.5 h-3.5 text-blue-600" />
                Initial Password
              </label>
              <input
                type="text" // Kept as text so the admin can see it and copy it to give to the user
                required
                minLength={6}
                value={formData.password}
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all"
                placeholder="TempPassword123!"
              />
              <p className="text-[10px] text-slate-500 mt-1.5">You will need to securely share this password with the user.</p>
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

            <p className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
              Instructors manage student course enrollment and project-team membership from the course workspace.
            </p>

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