"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";

import { scrollFieldIntoView } from "@/lib/scroll-field-into-view";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

type DialogContentProps = React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & {
  /** Set to false for modals with unsaved or busy state that must not close on outside click. */
  dismissOnOutsideClick?: boolean;
  /** Tailwind width/size classes for the panel. */
  className?: string;
};

export const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  DialogContentProps
>(({ className, children, dismissOnOutsideClick = false, onPointerDownOutside, onInteractOutside, onFocus, ...props }, ref) => (
  <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className="fixed inset-0 z-[100] bg-slate-900/50 backdrop-blur-sm" />
    <div className="fixed inset-0 z-[100] flex items-center justify-center overflow-y-auto p-4">
      <DialogPrimitive.Content
        ref={ref}
        onPointerDownOutside={(event) => {
          if (!dismissOnOutsideClick) event.preventDefault();
          onPointerDownOutside?.(event);
        }}
        onInteractOutside={(event) => {
          if (!dismissOnOutsideClick) event.preventDefault();
          onInteractOutside?.(event);
        }}
        onFocus={(event) => {
          scrollFieldIntoView(event);
          onFocus?.(event);
        }}
        aria-modal="true"
        className={`relative max-h-[calc(100dvh-2rem)] w-full overflow-y-auto rounded-xl bg-white shadow-xl focus:outline-none ${className ?? ""}`}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </div>
  </DialogPrimitive.Portal>
));
DialogContent.displayName = "DialogContent";

export const DialogTitle = DialogPrimitive.Title;
export const DialogDescription = DialogPrimitive.Description;
