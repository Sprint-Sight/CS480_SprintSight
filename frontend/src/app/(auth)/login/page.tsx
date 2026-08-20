"use client";

import React, { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";

const DEMO_CREDENTIALS = {
  instructor: {
    email: "instructor@demo.edu",
    password: "password123",
  },
  student: {
    email: "student@demo.edu",
    password: "password123",
  },
} as const;

export default function LoginPage() {
  const router = useRouter();
  const [role, setRole] = useState<"instructor" | "student">("instructor");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    const expected = DEMO_CREDENTIALS[role];
    if (email.trim().toLowerCase() !== expected.email || password !== expected.password) {
      setError("Invalid credentials for the selected role.");
      return;
    }

    sessionStorage.setItem("sprintsight-auth-role", role);
    sessionStorage.setItem("sprintsight-auth-email", expected.email);
    router.replace("/");
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-8">
        
        {/* Logo & Subtitle */}
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

        {/* Role Toggle */}
        <div className="flex bg-slate-100 rounded-lg p-1 mb-8">
          <button
            type="button"
            onClick={() => setRole("instructor")}
            className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
              role === "instructor"
                ? "bg-[#0b2046] text-white shadow"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            Instructor
          </button>
          <button
            type="button"
            onClick={() => setRole("student")}
            className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
              role === "student"
                ? "bg-[#0b2046] text-white shadow"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            Student
          </button>
        </div>

        {/* Form */}
        <form className="space-y-6" onSubmit={handleSubmit}>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Email Address
            </label>
            <input
              type="email"
              placeholder="you@university.edu"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (error) setError("");
              }}
              className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              required
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
              className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              required
            />
          </div>

          {error ? <p className="text-sm text-rose-600">{error}</p> : null}

          <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-md p-3">
            Demo credentials: Instructor: instructor@demo.edu / password123, Student: student@demo.edu / password123
          </p>

          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" className="rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
              <span className="text-sm text-slate-600">Remember me</span>
            </label>
            <Link href="#" className="text-sm text-blue-600 hover:text-blue-700 font-medium">
              Forgot password?
            </Link>
          </div>

          <button
            type="submit"
            className="w-full bg-[#0b2046] hover:bg-[#0f2c61] text-white py-2.5 rounded-lg font-medium transition-colors"
          >
            Sign In
          </button>
        </form>
      </div>
    </div>
  );
}