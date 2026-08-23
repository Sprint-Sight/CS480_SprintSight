"use client";

import React, { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";

const DEMO_USERS = [
  {
    email: "instructor@demo.edu",
    password: "password123",
    role: "instructor" as const,
  },
  {
    email: "student@demo.edu",
    password: "password123",
    role: "student" as const,
  },
];

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    const cleanEmail = email.trim().toLowerCase();
    
    // Automatically determine role based on submitted credentials
    const foundUser = DEMO_USERS.find(
      (user) => user.email === cleanEmail && user.password === password
    );

    if (!foundUser) {
      setError("Invalid email or password.");
      return;
    }

    sessionStorage.setItem("sprintsight-auth-role", foundUser.role);
    sessionStorage.setItem("sprintsight-auth-email", foundUser.email);
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
              className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-slate-800"
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
              className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-slate-800"
              required
            />
          </div>

          {error ? <p className="text-sm text-rose-600">{error}</p> : null}

          <p className="text-xs text-slate-500 bg-slate-50 border border-slate-200 rounded-md p-3 leading-relaxed">
            Demo credentials (role detected automatically):<br />
            • Instructor: <span className="font-medium text-slate-700">instructor@demo.edu</span> / <span className="font-medium text-slate-700">password123</span><br />
            • Student: <span className="font-medium text-slate-700">student@demo.edu</span> / <span className="font-medium text-slate-700">password123</span>
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