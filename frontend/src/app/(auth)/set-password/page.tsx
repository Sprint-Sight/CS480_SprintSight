"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
type PasswordPurpose = "first-time-password" | "password-reset";

export default function SetPasswordPage() {
  const [token, setToken] = useState("");
  const [purpose, setPurpose] = useState<PasswordPurpose | "">("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isComplete, setIsComplete] = useState(false);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const requestedPurpose = query.get("purpose");
    const requestedToken = query.get("token");
    if (
      requestedToken &&
      (requestedPurpose === "first-time-password" || requestedPurpose === "password-reset")
    ) {
      setToken(requestedToken);
      setPurpose(requestedPurpose);
    } else {
      setError("This password link is invalid. Request a new email and try again.");
    }
  }, []);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Your password must be at least 8 characters.");
      return;
    }
    if (password !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }
    if (!purpose || !token) {
      setError("This password link is invalid. Request a new email and try again.");
      return;
    }

    setIsLoading(true);
    try {
      const endpoint =
        purpose === "first-time-password" ? "first-time-password" : "password-reset";
      const response = await fetch(`${API_BASE_URL}/auth/${endpoint}/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: password }),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          result?.error?.message ||
            result?.detail ||
            "This password link is invalid or expired. Request a new email and try again.",
        );
      }
      setIsComplete(true);
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : "Unable to update your password. Please try again.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <section className="w-full max-w-md rounded-2xl bg-white p-8 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
        <h1 className="mb-2 text-2xl font-semibold text-slate-900">
          {isComplete ? "Password updated" : "Choose a new password"}
        </h1>
        {isComplete ? (
          <div className="space-y-5">
            <p className="text-sm text-slate-600">
              Your password has been updated. Sign in with your new password to continue.
            </p>
            <Link
              href="/login"
              className="block w-full rounded-lg bg-[#0b2046] py-2.5 text-center font-medium text-white hover:bg-[#0f2c61]"
            >
              Go to sign in
            </Link>
          </div>
        ) : (
          <form className="space-y-5" onSubmit={handleSubmit}>
            <p className="text-sm text-slate-600">
              Enter and confirm the password you want to use for SprintSight.
            </p>
            <label className="block text-sm font-medium text-slate-700">
              New password
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-4 py-2 text-slate-800"
              />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Confirm new password
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                required
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-4 py-2 text-slate-800"
              />
            </label>
            {error && <p className="text-sm text-rose-600">{error}</p>}
            <button
              type="submit"
              disabled={isLoading || !token || !purpose}
              className="w-full rounded-lg bg-[#0b2046] py-2.5 font-medium text-white disabled:opacity-50"
            >
              {isLoading ? "Updating password..." : "Set password"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
