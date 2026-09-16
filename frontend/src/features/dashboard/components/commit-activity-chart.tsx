"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DashboardCommit } from "@/features/dashboard/types";

export function CommitActivityChart({ commits }: { commits: DashboardCommit[] }) {
  const chartData = commits.reduce<Array<{ name: string; commits: number }>>((days, commit) => {
    const name = new Date(commit.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    const day = days.find((item) => item.name === name);
    if (day) day.commits += 1;
    else days.push({ name, commits: 1 });
    return days;
  }, []);
  return <div className="rounded-xl border border-slate-100 bg-white p-6 shadow-sm"><h3 className="mb-6 text-lg font-bold text-slate-900">Commit Activity</h3><div className="h-64 w-full"><ResponsiveContainer width="100%" height="100%"><LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" /><XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} dy={10} /><YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} /><Tooltip contentStyle={{ borderRadius: "8px", border: "none", boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)" }} /><Line type="monotone" dataKey="commits" stroke="#1e3a8a" strokeWidth={3} dot={{ r: 4, fill: "#1e3a8a", strokeWidth: 0 }} activeDot={{ r: 6, fill: "#3b82f6", strokeWidth: 0 }} /></LineChart></ResponsiveContainer></div></div>;
}
