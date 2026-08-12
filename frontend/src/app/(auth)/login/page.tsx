"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Eye } from "lucide-react";

export default function LoginPage() {
  const [role, setRole] = useState<"instructor" | "student">("instructor");

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-8">
        
        {/* Logo & Header */}
        <div className="flex flex-col items-center mb-8">
          <div className="flex items-center gap-2 mb-4 text-blue-600">
            <Eye className="w-8 h-8" />
            <span className="text-xl font-bold italic tracking-tight text-slate-800">SprintSight</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mb-2">SprintSight</h1>
          <p className="text-sm text-slate-500">AI-Powered Continuous Sprint Assessment</p>
        </div>

        {/* Role Toggle */}
        <div className="flex bg-slate-100 rounded-lg p-1 mb-8">
          <button
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
        <form className="space-y-6" onSubmit={(e) => e.preventDefault()}>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Email Address
            </label>
            <input
              type="email"
              placeholder="you@university.edu"
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
              className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
              required
            />
          </div>

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