"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ProgressDataset } from "@/features/progress/types";

export function ProgressTeamComparison({ data }: { data: ProgressDataset["teamComparison"] }) { return <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"><h2 className="text-xl font-semibold text-blue-950">Team Comparison Across Sprints</h2><div className="mt-3 h-[260px]"><ResponsiveContainer width="100%" height="100%"><BarChart data={data}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" /><XAxis dataKey="team" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} /><YAxis domain={[50, 100]} axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} /><Tooltip /><Legend /><Bar dataKey="sprint3" name="Sprint3" fill="#5C98BD" radius={[4, 4, 0, 0]} /><Bar dataKey="sprint4" name="Sprint4" fill="#3F7C9E" radius={[4, 4, 0, 0]} /><Bar dataKey="sprint5" name="Sprint5" fill="#1F3D6D" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div></section>; }
