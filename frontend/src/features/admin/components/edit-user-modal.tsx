"use client";

import React, { useState, useEffect } from "react";
import { X, Shield, User, Mail } from "lucide-react";
import { Role, UserAccount, EditUserData } from "@/features/admin/types";
import { ConfirmationModal } from "@/components/ui/confirmation-modal";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useAsyncAction } from "@/hooks/use-async-action";

interface EditUserModalProps {
  user: UserAccount | null;
  onClose: () => void;
  // Resolves to true when the save succeeded; the modal stays open on failure so edits are kept.
  onSave: (user: UserAccount, data: EditUserData) => Promise<boolean>;
}

export function EditUserModal({ user, onClose, onSave }: EditUserModalProps) {
  const [fullName, setFullName] = useState<string>("");
  const [email, setEmail] = useState<string>("");
  const [role, setRole] = useState<Role>("student");
  const [showConfirm, setShowConfirm] = useState(false);

  const { run: saveUser, isPending: isSubmitting } = useAsyncAction(async () => {
    if (!user) return;
    const saved = await onSave(user, { fullName, email, role });
    setShowConfirm(false);
    if (saved) onClose();
  });

  useEffect(() => {
    if (user) {
      setFullName(user.fullName || "");
      setEmail(user.email || "");
      setRole(user.role);
    }
  }, [user]);

  if (!user) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setShowConfirm(true);
  };

  const handleConfirmedSave = () => {
    void saveUser().catch(() => undefined);
  };

  return (
    <>
      <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
        <DialogContent dismissOnOutsideClick={false} className="max-w-md border border-slate-100 p-6">
          <div className="flex justify-between items-center pb-3 border-b border-slate-100">
            <DialogTitle asChild>
              <h2 className="text-base font-bold text-slate-900">Modify Identity & Assignments</h2>
            </DialogTitle>
            <button
              onClick={onClose}
              className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-blue-600" />
                Full Name
              </label>
              <input
                type="text"
                required
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all"
                placeholder="Full Name"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1 flex items-center gap-1.5">
                <Mail className="w-3.5 h-3.5 text-blue-600" />
                Email Address
              </label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all"
                placeholder="user@sprintsight.dev"
              />
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

            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
              {role === "student"
                ? "Course enrollment and project-team membership are managed from the instructor's course workspace."
                : "Course and project assignments are N/A for this role."}
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={onClose}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors"
              >
                Cancel
              </button>
              <Button type="submit" size="sm" isPending={isSubmitting} className="shadow-xs">
                {isSubmitting ? "Updating..." : "Save Assignment"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmationModal
        isOpen={showConfirm}
        onClose={() => setShowConfirm(false)}
        onConfirm={handleConfirmedSave}
        title="Confirm User Details Change"
        message={`Update identity details for ${fullName}?`}
        confirmText="Yes, Update User"
        cancelText="Cancel"
      />
    </>
  );
}