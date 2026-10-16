"use client";

import React, { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [mustChangePassword, setMustChangePassword] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    const cleanEmail = email.trim().toLowerCase();

    try {
      // Send login credentials to FastAPI backend
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: cleanEmail,
          password: password,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data?.error?.message || data?.detail || "Invalid email or password.");
      }

      // Store JWT token and user details in session storage
      sessionStorage.setItem("sprintsight-access-token", data.access_token);
      localStorage.setItem("sprintsight-access-token", data.access_token);

      if (data.must_change_password) {
        setMustChangePassword(true);
        setError("Change the temporary password before continuing.");
        return;
      }

      // Fetch user profile details to store role
      const userResponse = await fetch(`${API_BASE_URL}/auth/me`, {
        headers: {
          Authorization: `Bearer ${data.access_token}`,
        },
      });

      if (userResponse.ok) {
        const user = await userResponse.json();
        // Storage is already set above, but safe to do again along with role
        sessionStorage.setItem("sprintsight-auth-role", user.role);
        sessionStorage.setItem("sprintsight-auth-email", user.email);
        sessionStorage.setItem("sprintsight-auth-name", user.full_name);

        // Redirect based on role
        if (user.role === "admin") {
          router.replace("/admin");
        } else {
          router.replace("/");
        }
        return; // <--- IMPORTANT: Stop execution here so we don't hit other redirects
      } else {
        // If /me fails for some reason, throw an error to be caught below
        throw new Error("Failed to fetch user profile data.");
      }

      // REMOVED the rogue router.replace("/") that was here!
      
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred. Please try again.");
      // If login fails midway, clear the token just in case
      sessionStorage.removeItem("sprintsight-access-token");
      localStorage.removeItem("sprintsight-access-token");
    } finally {
      setIsLoading(false);
    }
  };

  const handleFirstPasswordChange = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    if (newPassword.length < 8) {
      setError("The new password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("The new passwords do not match.");
      return;
    }

    const token = sessionStorage.getItem("sprintsight-access-token");
    if (!token) {
      setError("Your session has expired. Please log in again.");
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ current_password: password, new_password: newPassword }),
      });
      const result = await response.json().catch(() => null);
      if (!response.ok) throw new Error(result?.detail || "Unable to change password.");

      const loginResponse = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase(), password: newPassword }),
      });
      const loginResult = await loginResponse.json().catch(() => null);
      if (!loginResponse.ok || !loginResult?.access_token) {
        throw new Error(loginResult?.detail || "Password changed, but a new session could not be created.");
      }

      const refreshedToken = loginResult.access_token;
      sessionStorage.setItem("sprintsight-access-token", refreshedToken);
      localStorage.setItem("sprintsight-access-token", refreshedToken);
      const userResponse = await fetch(`${API_BASE_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${refreshedToken}` },
      });
      if (!userResponse.ok) throw new Error("Password changed, but the profile could not be loaded.");
      const user = await userResponse.json();
      sessionStorage.setItem("sprintsight-auth-role", user.role);
      sessionStorage.setItem("sprintsight-auth-email", user.email);
      sessionStorage.setItem("sprintsight-auth-name", user.full_name);
      router.replace(user.role === "admin" ? "/admin" : "/");
    } catch (changeError) {
      setError(changeError instanceof Error ? changeError.message : "Unable to change password.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-8">
        <div className="flex flex-col items-center mb-6">
          <Image
            src="/logo.png"
            alt="SprintSight Logo"
            width={320}
            height={100}
            priority
            className="h-24 w-auto object-contain mb-1"
          />
          <p className="text-xs text-slate-400 font-medium tracking-tight">
            AI-Powered Continuous Sprint Assessment
          </p>
        </div>

        {mustChangePassword ? (
          <form className="space-y-6" onSubmit={handleFirstPasswordChange}>
            <p className="text-sm text-slate-600">This account has a temporary password. Set a new password to continue.</p>
            <input type="password" placeholder="New password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} className="w-full rounded-lg border border-slate-200 px-4 py-2 text-slate-800" required />
            <input type="password" placeholder="Confirm new password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className="w-full rounded-lg border border-slate-200 px-4 py-2 text-slate-800" required />
            {error && <p className="text-sm text-rose-600">{error}</p>}
            <button type="submit" disabled={isLoading} className="w-full rounded-lg bg-[#0b2046] py-2.5 font-medium text-white disabled:opacity-50">
              {isLoading ? "Updating password..." : "Set Password and Continue"}
            </button>
          </form>
        ) : (
        <form className="space-y-6" onSubmit={handleSubmit}>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Email Address
            </label>
            <input
              type="email"
              placeholder="you@sprintsight.dev"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (error) setError("");
              }}
              className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all text-slate-800 disabled:bg-slate-100"
              required
              disabled={isLoading}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Password
            </label>
            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                if (error) setError("");
              }}
              className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all text-slate-800 disabled:bg-slate-100"
              required
              disabled={isLoading}
            />
          </div>

          {error ? <p className="text-sm text-rose-600">{error}</p> : null}

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
        )}
      </div>
    </div>
  );
}