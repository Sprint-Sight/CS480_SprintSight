"use client";

import { AlertTriangle, UserRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  getCollaborationDataset,
  getCollaborationProjectOptions,
  getContributionDataset,
} from "@/features/collaboration/data";
import type { TeamRiskIndicator } from "@/features/collaboration/types";
import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";

function getRiskTone(risk: TeamRiskIndicator["risk"]) {
  if (risk === "Low") {
    return {
      box: "border-emerald-200 bg-emerald-50/40",
      badge: "bg-emerald-100 text-emerald-700",
      bar: "bg-emerald-500",
    };
  }

  if (risk === "Medium") {
    return {
      box: "border-amber-200 bg-amber-50/40",
      badge: "bg-amber-100 text-amber-700",
      bar: "bg-amber-500",
    };
  }

  return {
    box: "border-rose-200 bg-rose-50/40",
    badge: "bg-rose-100 text-rose-700",
    bar: "bg-rose-500",
  };
}

function heatColor(score: number) {
  if (score <= 3) return "bg-sky-100 text-sky-700";
  if (score <= 7) return "bg-sky-300 text-sky-900";
  if (score <= 10) return "bg-[#2F6690] text-white";
  return "bg-[#1E3A8A] text-white";
}

export default function CollaborationPageContent() {
  const projectOptions = useMemo(() => getCollaborationProjectOptions(), []);
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || projectOptions[0]?.id || "");
  const [role, setRole] = useState<"student" | "instructor" | null>(null);
  const [ingestionVersion, setIngestionVersion] = useState(0);

  // Load datasets for the selected project
  const collaborationData = useMemo(() => getCollaborationDataset(selectedProjectId), [selectedProjectId]);
  const contributionData = useMemo(() => getContributionDataset(selectedProjectId), [selectedProjectId]);

  const comparisonChartData = useMemo(() => {
    return contributionData.members.map((member) => ({
      name: member.name.split(" ")[0],
      GitHub: member.githubScore,
      Jira: member.jiraScore,
      Peer: Math.round(member.peerScore * 20),
    }));
  }, [contributionData]);

  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | null;
    setRole(savedRole ?? "student");
  }, []);

  useEffect(() => {
    const refresh = () => {
      setSelectedProjectId(readIngestionState().selectedProjectId || "");
      setIngestionVersion((version) => version + 1);
    };
    window.addEventListener("sprintsight-ingestion-updated", refresh);
    return () => window.removeEventListener("sprintsight-ingestion-updated", refresh);
  }, []);

  const liveIngestion = useMemo(() => {
    void ingestionVersion;
    return getProjectIngestion(selectedProjectId);
  }, [selectedProjectId, ingestionVersion]);

  return (
    <div className="space-y-6 p-8">
      {/* Header & Global Controls */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">Team & Individual Analytics</h1>
          <p className="mt-1 text-sm text-slate-500">
            {collaborationData.subtitle} • {contributionData.sprintLabel}
          </p>
        </div>

        <div className="w-full max-w-sm">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">
            Project Context
          </label>
          <select
            value={selectedProjectId}
            onChange={(event) => setSelectedProjectId(event.target.value)}
            className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none ring-blue-100 transition focus:border-blue-300 focus:ring-2"
          >
            {projectOptions.map((project) => (
              <option key={project.id} value={project.id}>
                {project.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {(liveIngestion.git || liveIngestion.jira) && (
        <section className="rounded-2xl border border-blue-200 bg-blue-50/50 p-4">
          <h2 className="text-lg font-semibold text-blue-950">Live Project Signals</h2>
          <p className="mt-1 text-sm text-slate-700">
            {liveIngestion.git?.pagination?.total ?? liveIngestion.git?.commits.length ?? 0} Git commits, {liveIngestion.jira?.tickets.length ?? 0} Jira tickets, and {liveIngestion.documents} documents are available for this project.
          </p>
          <p className="mt-1 text-xs text-slate-500">Member-level collaboration scores remain fixture-based until the backend returns contributor IDs.</p>
        </section>
      )}

      {/* Section 1: Macro Team Collaboration Charts */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-blue-950">Commits by Member</h2>
          <div className="mt-3 h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={collaborationData.commitsByMember}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="member" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                <Tooltip cursor={{ fill: "rgba(30, 58, 138, 0.06)" }} />
                <Bar dataKey="commits" radius={[6, 6, 0, 0]} fill="#2F5B85" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-blue-950">Workload Distribution</h2>
          <div className="mt-3 h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={collaborationData.workloadDistribution}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={48}
                  outerRadius={84}
                  paddingAngle={2}
                >
                  {collaborationData.workloadDistribution.map((slice) => (
                    <Cell key={slice.name} fill={slice.color} />
                  ))}
                </Pie>
                <Tooltip formatter={(value: number) => `${value}%`} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-slate-600">
            {collaborationData.workloadDistribution.map((slice) => (
              <span key={slice.name} className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: slice.color }} />
                {slice.name}
              </span>
            ))}
          </div>
        </section>
      </div>

      {/* Section 2: Team Participation Heatmap */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold text-blue-950">Team Participation Heatmap</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[720px] border-separate border-spacing-y-2 text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-2 py-1">Member</th>
                <th className="px-2 py-1 text-center">Week 1</th>
                <th className="px-2 py-1 text-center">Week 2</th>
                <th className="px-2 py-1 text-center">Week 3</th>
                <th className="px-2 py-1 text-center">Week 4</th>
              </tr>
            </thead>
            <tbody>
              {collaborationData.participationHeatmap.map((row) => (
                <tr key={row.member}>
                  <td className="px-2 py-2 font-medium text-slate-800">{row.member}</td>
                  <td className="px-1 py-1">
                    <div className={`rounded-md py-2 text-center text-xs font-semibold ${heatColor(row.week1)}`}>
                      {row.week1}
                    </div>
                  </td>
                  <td className="px-1 py-1">
                    <div className={`rounded-md py-2 text-center text-xs font-semibold ${heatColor(row.week2)}`}>
                      {row.week2}
                    </div>
                  </td>
                  <td className="px-1 py-1">
                    <div className={`rounded-md py-2 text-center text-xs font-semibold ${heatColor(row.week3)}`}>
                      {row.week3}
                    </div>
                  </td>
                  <td className="px-1 py-1">
                    <div className={`rounded-md py-2 text-center text-xs font-semibold ${heatColor(row.week4)}`}>
                      {row.week4}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
          <span>Activity Level:</span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded bg-sky-100" />
            Low
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded bg-sky-300" />
            Medium
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded bg-[#1E3A8A]" />
            High
          </span>
        </div>
      </section>

      {/* Section 3: Multi-Source Contribution Comparison */}
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-xl font-semibold text-blue-950">Contribution Breakdown by Platform</h2>
        <div className="mt-4 h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={comparisonChartData} barCategoryGap="10%">
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
              <YAxis domain={[0, 100]} axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey="GitHub" fill="#1F3D6D" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Jira" fill="#3F7C9E" radius={[4, 4, 0, 0]} />
              <Bar dataKey="Peer" fill="#5C98BD" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Section 5: Risk Indicators (Instructor View Only) */}
      {role === "instructor" && (
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-blue-950">Collaboration Risk Indicators</h2>
          <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
            {collaborationData.riskIndicators.map((item) => {
              const tone = getRiskTone(item.risk);
              return (
                <article key={item.team} className={`rounded-xl border p-3 ${tone.box}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="inline-flex items-center gap-1 text-sm font-semibold text-slate-900">
                        <UserRound className="h-4 w-4 text-slate-500" />
                        {item.team}
                      </p>
                      <p className="mt-1 text-xs text-slate-600">{item.summary}</p>
                    </div>
                    <span
                      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${tone.badge}`}
                    >
                      <AlertTriangle className="h-3.5 w-3.5" />
                      {item.risk} Risk
                    </span>
                  </div>

                  <div className="mt-3">
                    <div className="mb-1 flex items-center justify-between text-xs text-slate-600">
                      <span>Balance Score</span>
                      <span>{item.balanceScore}%</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-white/80">
                      <div className={`h-full rounded-full ${tone.bar}`} style={{ width: `${item.balanceScore}%` }} />
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}