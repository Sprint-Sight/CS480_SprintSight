"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  FolderOpen,
  Activity,
  FileCheck,
  AlertTriangle,
  Award,
  Clock,
  CheckCircle2,
  GitCommit,
  CheckSquare,
  FileCode,
  MessageSquare,
  ArrowRight,
  Search,
  Filter,
  Plus,
  Trash2,
  Edit3,
  ChevronLeft,
  ChevronRight,
  Shield,
  UserCheck,
  UserPlus,
  X,
  MoreVertical,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { useRouter } from "next/navigation";

type Role = "student" | "instructor" | "admin";

interface UserAccount {
  id: string;
  fullName: string;
  email: string;
  role: Role;
  scope: string;
  status: "Active" | "Inactive";
  createdAt: string;
}

// --- Instructor Mock Data ---
const instructorChartData = [
  { name: "Sprint 1", score: 62 },
  { name: "Sprint 2", score: 67 },
  { name: "Sprint 3", score: 71 },
  { name: "Sprint 4", score: 73 },
  { name: "Sprint 5", score: 78 },
  { name: "Sprint 6", score: 76 },
  { name: "Sprint 7", score: 81 },
];

const instructorAlerts = [
  { team: "Team Delta", msg: "One member has 0 commits in Sprint 3", critical: true },
  { team: "Team Zeta", msg: "Uneven workload distribution detected", critical: false },
  { team: "Team Eta", msg: "Missing Jira task updates for 5 days", critical: false },
  { team: "Team Delta", msg: "Peer evaluation scores significantly diverge", critical: true },
  { team: "Team Theta", msg: "No documentation updates in Sprint 4", critical: false },
];

// --- Student Mock Data ---
const studentChartData = [
  { name: "Sprint 1", myScore: 78, teamAvg: 74, target: 85 },
  { name: "Sprint 2", myScore: 82, teamAvg: 79, target: 85 },
  { name: "Sprint 3", myScore: 85, teamAvg: 81, target: 85 },
  { name: "Sprint 4", myScore: 84, teamAvg: 82, target: 85 },
  { name: "Sprint 5", myScore: 88, teamAvg: 85, target: 85 },
];

const studentActionCenter = [
  { title: "Submit Sprint 5 Peer Evaluation", due: "Due in 2 days", icon: CheckSquare, badge: "Action Required", color: "text-amber-600 bg-amber-50 border-amber-200" },
  { title: "1 GitHub PR Waiting for Team Review", due: "PR #42 - Auth Flow Integration", icon: FileCode, badge: "Pending Review", color: "text-blue-600 bg-blue-50 border-blue-200" },
  { title: "Instructor Feedback on Artifact #3", due: "Posted yesterday", icon: MessageSquare, badge: "New Feedback", color: "text-emerald-600 bg-emerald-50 border-emerald-200" },
];

const studentSprintHistory = [
  { sprint: "Sprint 5 (Current)", myScore: 88, teamScore: 85, stats: "14 commits · 3 PRs · 8 tasks", feedback: "Strong backend performance; technical design document clear.", status: "In Progress" },
  { sprint: "Sprint 4", myScore: 84, teamScore: 82, stats: "11 commits · 2 PRs · 6 tasks", feedback: "Good effort in API integration. Ensure tests cover edge cases.", status: "Completed" },
  { sprint: "Sprint 3", myScore: 85, teamScore: 81, stats: "13 commits · 4 PRs · 7 tasks", feedback: "Excellent code quality. Great leadership in group discussions.", status: "Completed" },
  { sprint: "Sprint 2", myScore: 82, teamScore: 79, stats: "9 commits · 2 PRs · 5 tasks", feedback: "Consistent progress. Work on documentation completeness.", status: "Completed" },
  { sprint: "Sprint 1", myScore: 78, teamScore: 74, stats: "8 commits · 1 PR · 4 tasks", feedback: "Good baseline setup. Team sync can be improved.", status: "Completed" },
];

export default function DashboardPage() {
  const router = useRouter();
  const [role, setRole] = useState<Role>("instructor");
  const [fullName, setFullName] = useState<string>("");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as Role | null;
    const savedName = sessionStorage.getItem("sprintsight-auth-name");
    const token = sessionStorage.getItem("sprintsight-access-token");

    // Redirect admins directly to the standalone Admin IAM Console
    if (savedRole === "admin") {
      router.replace("/admin");
      return;
    }

    if (savedRole) setRole(savedRole);
    if (savedName) setFullName(savedName);
    setMounted(true);
  }, [router]);

  if (!mounted) return null;

  // Render Student Dashboard
  if (role === "student") {
    return (
      <div className="p-8 max-w-7xl mx-auto space-y-8 bg-slate-50 min-h-screen">
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-slate-900">My Dashboard</h1>
          <p className="text-slate-500 mt-1">
            Welcome back, <span className="font-semibold text-slate-700">{fullName || "Student"}</span>. Here is your project overview for <span className="font-semibold text-slate-700">Team Alpha — E-Commerce Platform</span>.
          </p>
        </div>

        {/* Top Metrics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm font-medium text-slate-500">Current Grade</p>
                <h3 className="text-3xl font-bold text-slate-900 mt-1">88<span className="text-lg font-normal text-slate-400">/100</span></h3>
              </div>
              <div className="p-2 bg-emerald-50 rounded-lg text-emerald-600">
                <Award className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs font-medium text-emerald-600">↗ On Track for Grade A</p>
          </div>

          <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm font-medium text-slate-500">Sprint Countdown</p>
                <h3 className="text-3xl font-bold text-slate-900 mt-1">4 Days</h3>
              </div>
              <div className="p-2 bg-blue-50 rounded-lg text-blue-600">
                <Clock className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs font-medium text-slate-500">Sprint 5 Ends Friday, 11:59 PM</p>
          </div>

          <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm font-medium text-slate-500">My Tasks</p>
                <h3 className="text-3xl font-bold text-slate-900 mt-1">8 / 10</h3>
              </div>
              <div className="p-2 bg-indigo-50 rounded-lg text-indigo-600">
                <CheckCircle2 className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs font-medium text-indigo-600">80% Jira Tasks Completed</p>
          </div>

          <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col justify-between">
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-sm font-medium text-slate-500">Contribution Share</p>
                <h3 className="text-3xl font-bold text-slate-900 mt-1">26%</h3>
              </div>
              <div className="p-2 bg-purple-50 rounded-lg text-purple-600">
                <GitCommit className="w-5 h-5" />
              </div>
            </div>
            <p className="text-xs font-medium text-purple-600">14 Commits · 3 PRs Merged</p>
          </div>
        </div>

        {/* Middle Section: Chart & Action Center */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-white p-6 rounded-xl border border-slate-100 shadow-sm">
            <h3 className="text-lg font-bold text-slate-900 mb-6">Performance Trend (My Score vs. Team)</h3>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={studentChartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} dy={10} />
                  <YAxis domain={[50, 100]} axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                  <Tooltip contentStyle={{ borderRadius: "8px", border: "none", boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)" }} />
                  <Legend verticalAlign="top" height={36} />
                  <Line type="monotone" name="My Score" dataKey="myScore" stroke="#2563eb" strokeWidth={3} dot={{ r: 4 }} />
                  <Line type="monotone" name="Team Average" dataKey="teamAvg" stroke="#94a3b8" strokeWidth={2} strokeDasharray="4 4" dot={false} />
                  <Line type="monotone" name="Target (85+)" dataKey="target" stroke="#10b981" strokeWidth={1.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col">
            <h3 className="text-lg font-bold text-slate-900 mb-4">Action Center</h3>
            <div className="flex-1 overflow-y-auto space-y-3">
              {studentActionCenter.map((item, idx) => (
                <div key={idx} className={`p-3.5 rounded-xl border ${item.color} transition-all hover:shadow-xs`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-700">
                      {item.badge}
                    </span>
                    <item.icon className="w-4 h-4 text-slate-500" />
                  </div>
                  <p className="text-sm font-semibold text-slate-900 mt-1">{item.title}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{item.due}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Bottom Section */}
        <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm">
          <h3 className="text-lg font-bold text-slate-900 mb-6">My Sprint Breakdown</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="pb-3 text-sm font-semibold text-slate-500">Sprint</th>
                  <th className="pb-3 text-sm font-semibold text-slate-500">My Score</th>
                  <th className="pb-3 text-sm font-semibold text-slate-500">Team Score</th>
                  <th className="pb-3 text-sm font-semibold text-slate-500">Contributions</th>
                  <th className="pb-3 text-sm font-semibold text-slate-500">AI Feedback Summary</th>
                  <th className="pb-3 text-sm font-semibold text-slate-500 text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {studentSprintHistory.map((row, idx) => (
                  <tr key={idx} className="border-b border-slate-100 last:border-0 hover:bg-slate-50 transition-colors">
                    <td className="py-4 text-sm font-semibold text-slate-900">{row.sprint}</td>
                    <td className="py-4 text-sm font-bold text-blue-600">{row.myScore}/100</td>
                    <td className="py-4 text-sm text-slate-600">{row.teamScore}/100</td>
                    <td className="py-4 text-xs text-slate-600">{row.stats}</td>
                    <td className="py-4 text-xs text-slate-600 max-w-xs truncate">{row.feedback}</td>
                    <td className="py-4 text-right">
                      <button type="button" className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-800">
                        View Details <ArrowRight className="w-3 h-3" />
                      </button>
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

  // Render Instructor Dashboard
  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 bg-slate-50 min-h-screen">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-slate-500 mt-1">
          Welcome back, <span className="font-semibold text-slate-700">{fullName || "Instructor"}</span>. Here&apos;s your assessment overview.
        </p>
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
            <p className={`text-xs ${metric.title === "Collaboration Alerts" ? "text-rose-500" : "text-emerald-600"} font-medium`}>
              {metric.title !== "Collaboration Alerts" && "↗ "}
              {metric.sub}
            </p>
          </div>
        ))}
      </div>

      {/* Middle Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white p-6 rounded-xl border border-slate-100 shadow-sm">
          <h3 className="text-lg font-bold text-slate-900 mb-6">Average Scores Over Time</h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={instructorChartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} dy={10} />
                <YAxis domain={[50, 100]} axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                <Tooltip contentStyle={{ borderRadius: "8px", border: "none", boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)" }} />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke="#1e3a8a"
                  strokeWidth={3}
                  dot={{ r: 4, fill: "#1e3a8a", strokeWidth: 0 }}
                  activeDot={{ r: 6, fill: "#3b82f6", strokeWidth: 0 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-white p-6 rounded-xl border border-slate-100 shadow-sm flex flex-col">
          <h3 className="text-lg font-bold text-slate-900 mb-4">Collaboration Alerts</h3>
          <div className="flex-1 overflow-y-auto pr-2 space-y-3">
            {instructorAlerts.map((alert, idx) => (
              <div key={idx} className="p-3 rounded-lg border border-slate-100 bg-slate-50 flex items-start gap-3">
                <div className={`mt-1.5 w-2 h-2 rounded-full flex-shrink-0 ${alert.critical ? "bg-rose-500" : "bg-amber-400"}`} />
                <div>
                  <p className="text-xs font-semibold text-slate-800">{alert.team}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{alert.msg}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}