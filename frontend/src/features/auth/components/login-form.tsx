import { useId } from "react";
import Link from "next/link";
import Image from "next/image";

import { scrollFieldIntoView } from "@/lib/scroll-field-into-view";

type LoginFormProps = {
  email: string;
  password: string;
  error: string;
  isLoading: boolean;
  onEmailChange: (email: string) => void;
  onPasswordChange: (password: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
};

export function LoginForm({
  email,
  password,
  error,
  isLoading,
  onEmailChange,
  onPasswordChange,
  onSubmit,
}: LoginFormProps) {
  const emailId = useId();
  const passwordId = useId();
  const errorId = useId();

  return (
    <div className="min-h-dvh flex items-start justify-center bg-slate-50 p-4 sm:items-center">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-6 sm:p-8">
        <div className="flex flex-col items-center mb-6">
          <Image
            src="/logo.png"
            alt="SprintSight Logo"
            width={320}
            height={100}
            priority
            className="h-16 sm:h-24 w-auto object-contain mb-1"
          />
          <p className="text-xs text-slate-400 font-medium tracking-tight">
            AI-Powered Continuous Sprint Assessment
          </p>
        </div>

        <form className="space-y-6" onSubmit={onSubmit} onFocus={scrollFieldIntoView}>
          <div>
            <label htmlFor={emailId} className="block text-sm font-medium text-slate-700 mb-1">
              Email Address
            </label>
            <input
              id={emailId}
              name="email"
              type="email"
              autoComplete="email"
              placeholder="you@sprintsight.dev"
              value={email}
              onChange={(e) => {
                onEmailChange(e.target.value);
              }}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? errorId : undefined}
              className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all text-slate-800 disabled:bg-slate-100"
              required
              disabled={isLoading}
            />
          </div>

          <div>
            <label htmlFor={passwordId} className="block text-sm font-medium text-slate-700 mb-1">
              Password
            </label>
            <input
              id={passwordId}
              name="password"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => {
                onPasswordChange(e.target.value);
              }}
              aria-invalid={error ? true : undefined}
              aria-describedby={error ? errorId : undefined}
              className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all text-slate-800 disabled:bg-slate-100"
              required
              disabled={isLoading}
            />
          </div>

          {error && (
            <p id={errorId} role="alert" className="text-sm text-rose-600">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-[#0b2046] hover:bg-[#0f2c61] text-white py-2.5 rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            {isLoading ? "Signing in..." : "Sign In"}
          </button>
          <div className="text-center">
            <Link href="/forgot-password" className="text-sm text-blue-700 hover:underline">
              Forgot your password?
            </Link>
          </div>
        </form>
      </div>
    </div>
  );
}
