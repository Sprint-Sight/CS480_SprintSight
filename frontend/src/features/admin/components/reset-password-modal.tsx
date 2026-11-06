"use client";

import { useId } from "react";
import { Loader2 } from "lucide-react";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import type { UserAccount } from "@/features/admin/types";

/** Mirrors the backend `AdminPasswordReset.password` min_length. */
export const MIN_PASSWORD_LENGTH = 8;

type ResetPasswordModalProps = {
  user: UserAccount | null;
  password: string;
  isSubmitting: boolean;
  onPasswordChange: (password: string) => void;
  onCancel: () => void;
  onSubmit: () => void;
};

export function ResetPasswordModal({
  user,
  password,
  isSubmitting,
  onPasswordChange,
  onCancel,
  onSubmit,
}: ResetPasswordModalProps) {
  const inputId = useId();
  const hintId = useId();

  if (!user) return null;

  const isTooShort = password.length < MIN_PASSWORD_LENGTH;

  return (
    <Dialog open onOpenChange={(open) => { if (!open) onCancel(); }}>
      <DialogContent dismissOnOutsideClick={false} className="max-w-md overflow-hidden rounded-2xl p-0">
      <form
        className="w-full"
        onSubmit={(event) => {
          event.preventDefault();
          if (!isTooShort && !isSubmitting) onSubmit();
        }}
      >
        <div className="p-6">
          <DialogTitle asChild>
            <h3 className="text-lg font-bold text-slate-900 mb-2">Reset User Password</h3>
          </DialogTitle>
          <p className="text-sm text-slate-500 mb-5">
            Set a new password for <span className="font-semibold text-slate-700">{user.fullName}</span>. They will be required to change it upon their next login.
          </p>

          <div>
            <label htmlFor={inputId} className="block text-sm font-medium text-slate-700 mb-1.5">
              New Password
            </label>
            <input
              id={inputId}
              type="password"
              autoComplete="new-password"
              minLength={MIN_PASSWORD_LENGTH}
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
              placeholder="Enter temporary password..."
              aria-describedby={hintId}
              aria-invalid={password.length > 0 && isTooShort}
              disabled={isSubmitting}
              className="w-full px-4 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all disabled:opacity-60"
              autoFocus
            />
            <p
              id={hintId}
              className={`mt-1.5 text-xs ${password.length > 0 && isTooShort ? "text-rose-600" : "text-slate-500"}`}
            >
              Minimum {MIN_PASSWORD_LENGTH} characters.
            </p>
          </div>
        </div>

        <div className="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-200/50 rounded-lg transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isTooShort || isSubmitting}
            aria-busy={isSubmitting}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
            {isSubmitting ? "Resetting..." : "Reset Password"}
          </button>
        </div>
      </form>
      </DialogContent>
    </Dialog>
  );
}
