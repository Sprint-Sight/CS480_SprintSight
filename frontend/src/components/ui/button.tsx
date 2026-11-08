"use client";

import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Loader2 } from "lucide-react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isPending?: boolean;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: "bg-blue-700 text-white hover:bg-blue-800 border border-transparent",
  secondary: "bg-white text-slate-700 hover:bg-slate-50 border border-slate-200",
  ghost: "bg-transparent text-slate-700 hover:bg-slate-100 border border-transparent",
  danger: "bg-red-600 text-white hover:bg-red-700 border border-transparent",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "min-h-[44px] px-3 text-xs",
  md: "min-h-[44px] px-4 text-sm",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", isPending = false, disabled, className = "", children, type = "button", ...rest },
  ref,
) {
  const classes = [
    "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2",
    "active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100",
    VARIANT_CLASSES[variant],
    SIZE_CLASSES[size],
    className,
  ].join(" ");

  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || isPending}
      aria-busy={isPending || undefined}
      className={classes}
      {...rest}
    >
      {isPending && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
      {children}
    </button>
  );
});
