"use client";

import React from "react";
import { FolderOpen, Activity, FileCheck, AlertTriangle } from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

// Mock Data Definitions
const chartData = [
  { name: "Sprint 1", score: 62 },
  { name: "Sprint 2", score: 67 },
  { name: "Sprint 3", score: 71 },
  { name: "Sprint 4", score: 73 },
  { name: "Sprint 5", score: 78 },
  { name: "Sprint 6", score: 76 },
  { name: "Sprint 7", score: 81 },
];

const alerts = [
  { team: "Team Delta", msg: "One member has 0 commits in Sprint 3", critical: true },
  { team: "Team Zeta", msg: "Uneven workload distribution detected", critical: false },
  { team: "Team Eta", msg: "Missing Jira task updates for 5 days", critical: false },
  { team: "Team Delta", msg: "Peer evaluation scores significantly diverge", critical: true },
  { team: "Team Theta", msg: "No documentation updates in Sprint 4", critical: false },
];

const assessments = [
  { team: "Team Alpha", project: "E-Commerce Platform", sprint: "Sprint 5", score: 82, status: "Completed" },
  { team: "Team Beta", project: "Chat Application", sprint: "Sprint 4", score: 75, status: "Completed" },
  { team: "Team Gamma", project: "Task Manager", sprint: "Sprint 5", score: 88, status: "Completed" },
  { team: "Team Delta", project: "Social Network", sprint: "Sprint 3", score: 69, status: "Needs Review" },
  { team: "Team Epsilon", project: "Weather App", sprint: "Sprint 5", score: 91, status: "Completed" },
];

export default function DashboardPage() {
  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 bg-slate-50 min-h-screen">
      
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-slate-500 mt-1">Welcome back, Dr. Chen. Here's your assessment overview.</p>
      </div>

      {/* Top Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {[
          { title: "Total Projects", value: "24", sub: "+3 this semester", icon: FolderOpen, color: "text-blue-500" },
          { title: "Active Sprints", value: "12", sub: "4 due this week", icon: Activity, color: "text-indigo-500" },
          { title: "Assessments Completed", value: "87", sub: "+12 this week", icon: FileCheck, color: "text-emerald-500" },
          { title: "Collaboration Alerts", value: "5", sub: "2 critical", icon: AlertTriangle, color: "text-rose-500" },
        ].map((metric, idx) => (
          <div key={idx} className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm font-medium text-slate-500">{metric.title}</p>
                <h3 className="text-3xl font-bold text-slate-900 mt-1">{metric.value}</h3>
              </div>
              <div className={`p-2 bg-slate-50 rounded-lg ${metric.color}`}>
                <metric.icon className="w-5 h-5" />
              </div>
            </div>
            <p className={`text-xs ${metric.title === 'Collaboration Alerts' ? 'text-rose-500' : 'text-emerald-600'} font-medium`}>
              {metric.title !== 'Collaboration Alerts' && '↗ '}
              {metric.sub}
            </p>
          </div>
        ))}
      </div>

      {/* Middle Section: Chart & Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Trend Chart */}
        <div className="lg:col-span-2 bg-white p-6 rounded-xl border border-slate-100 shadow-sm">
          <h3 className="text-lg font-bold text-slate-900 mb-6">Average Scores Over Time</h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} dy={10} />
                <YAxis domain={[50, 100]} axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                <Tooltip 
                  contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                />
                <Line 
                  type="monotone" 
                  dataKey="score" 
                  stroke="#1e3a8a" 
                  strokeWidth={3}
                  dot={{ r: 4, fill: '#1e3a8a', strokeWidth: 0 }}
                  activeDot={{ r: 6, fill: '#3b82f6', strokeWidth: 0 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Alerts List */}
        <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col">
          <h3 className="text-lg font-bold text-slate-900 mb-4">Collaboration Alerts</h3>
          <div className="flex-1 overflow-y-auto pr-2 space-y-3">
            {alerts.map((alert, idx) => (
              <div key={idx} className="p-3 rounded-lg border border-slate-100 bg-slate-50 flex items-start gap-3">
                <div className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${alert.critical ? 'bg-rose-500' : 'bg-amber-400'}`} />
                <div>
                  <p className="text-sm font-semibold text-slate-900">{alert.team}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{alert.msg}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom Section: Recent Assessments Table */}
      <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm">
        <h3 className="text-lg font-bold text-slate-900 mb-6">Recent Assessments</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-200">
                <th className="pb-3 text-sm font-semibold text-slate-500">Team</th>
                <th className="pb-3 text-sm font-semibold text-slate-500">Project</th>
                <th className="pb-3 text-sm font-semibold text-slate-500">Sprint</th>
                <th className="pb-3 text-sm font-semibold text-slate-500">Score</th>
                <th className="pb-3 text-sm font-semibold text-slate-500">Status</th>
              </tr>
            </thead>
            <tbody>
              {assessments.map((row, idx) => (
                <tr key={idx} className="border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors">
                  <td className="py-4 text-sm font-medium text-slate-900">{row.team}</td>
                  <td className="py-4 text-sm text-slate-600">{row.project}</td>
                  <td className="py-4 text-sm text-slate-600">{row.sprint}</td>
                  <td className={`py-4 text-sm font-bold ${row.score >= 80 ? 'text-emerald-600' : 'text-rose-500'}`}>
                    {row.score}/100
                  </td>
                  <td className="py-4">
                    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                      row.status === 'Completed' 
                        ? 'bg-emerald-100 text-emerald-800' 
                        : 'bg-amber-100 text-amber-800'
                    }`}>
                      {row.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}