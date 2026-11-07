"use client";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useAsyncAction } from "@/hooks/use-async-action";

type ConfirmationModalProps = {
  isOpen: boolean;
  onClose: () => void;
  // May return a promise; the confirm button stays pending until it settles.
  onConfirm: () => void | Promise<unknown>;
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  variant?: "default" | "danger";
};

export function ConfirmationModal({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText = "Confirm",
  cancelText = "Cancel",
  variant = "default",
}: ConfirmationModalProps) {
  const { run: runConfirm, isPending } = useAsyncAction(() => onConfirm());

  const handleConfirm = () => {
    // Failures are reported by the caller's own handler, so the rejection is intentionally dropped here.
    void runConfirm().catch(() => undefined);
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && !isPending && onClose()}>
      <DialogContent className="max-w-md p-6">
        <DialogTitle className="text-lg font-semibold text-slate-900">{title}</DialogTitle>
        <DialogDescription className="mt-2 text-sm text-slate-600">{message}</DialogDescription>

        <div className="mt-6 flex items-center justify-end gap-3">
          <Button variant="ghost" onClick={onClose} disabled={isPending}>
            {cancelText}
          </Button>
          <Button
            variant={variant === "danger" ? "danger" : "primary"}
            onClick={handleConfirm}
            isPending={isPending}
          >
            {confirmText}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}