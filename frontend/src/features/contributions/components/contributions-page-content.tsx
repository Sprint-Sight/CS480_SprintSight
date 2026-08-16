"use client";

import { CheckSquare, GitBranch, Users } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { getContributionDataset, getContributionProjectOptions } from "@/features/contributions/data";

function adjustmentBadge(value: number) {
  if (value > 0) {
    return {
      text: `+${value}%`,
      className: "text-emerald-600",
    };
  }

  if (value < 0) {
    return {
      text: `${value}%`,
      className: "text-rose-600",
    };
  }

  return {
    text: "0%",
    className: "text-slate-500",
  };
}

function gradeTone(grade: string) {
  if (grade.startsWith("A")) return "text-blue-900";
  if (grade.startsWith("B")) return "text-slate-800";
  return "text-amber-700";
}

export default function ContributionsPageContent() {
  const projectOptions = useMemo(() => getContributionProjectOptions(), []);
  const [selectedProjectId, setSelectedProjectId] = useState(projectOptions[0]?.id ?? "");

  const dataset = useMemo(() => getContributionDataset(selectedProjectId), [selectedProjectId]);

  const chartData = dataset.members.map((member) => ({
    name: member.name.split(" ")[0],
    GitHub: member.githubScore,
    Jira: member.jiraScore,
    Peer: Math.round(member.peerScore * 20),
  }));

  return (
    <div className="space-y-5 p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">Individual Contribution Analysis</h1>
          <p className="mt-1 text-sm text-slate-500">
            {dataset.teamLabel} - {dataset.projectLabel} - {dataset.sprintLabel} contribution breakdown
          </p>
        </div>

        <div className="w-full max-w-sm">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wider text-slate-500">Project context</label>
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

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-2xl font-semibold text-blue-950">Contribution Comparison</h2>
        <div className="mt-4 h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} barCategoryGap="10%">
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

      <section className="space-y-3">
        {dataset.members.map((member) => {
          const badge = adjustmentBadge(member.gradeAdjustmentPercent);
          return (
            <article key={member.id} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-sky-100 text-sm font-semibold text-blue-700">
                    {member.initials}
                  </div>
                  <div>
                    <p className="text-xl font-semibold text-blue-950">{member.name}</p>
                    <p className="text-sm text-slate-500">{member.role}</p>
                  </div>
                </div>

                <div className="grid min-w-[280px] grid-cols-3 gap-4 text-sm">
                  <div>
                    <p className="inline-flex items-center gap-1 text-slate-500"><GitBranch className="h-4 w-4" />GitHub</p>
                    <p className="text-2xl font-bold text-blue-900">{member.githubScore}%</p>
                  </div>
                  <div>
                    <p className="inline-flex items-center gap-1 text-slate-500"><CheckSquare className="h-4 w-4" />Jira</p>
                    <p className="text-2xl font-bold text-blue-900">{member.jiraScore}%</p>
                  </div>
                  <div>
                    <p className="inline-flex items-center gap-1 text-slate-500"><Users className="h-4 w-4" />Peer Eval</p>
                    <p className="text-2xl font-bold text-blue-900">{member.peerScore.toFixed(1)}/5.0</p>
                  </div>
                </div>

                <div className="text-right">
                  <p className="text-sm text-slate-500">Overall</p>
                  <p className="text-2xl font-bold text-blue-900">{member.overallScore}%</p>
                </div>

                <div className="text-right">
                  <p className="text-sm text-slate-500">Recommended</p>
                  <p className={`text-3xl font-bold ${gradeTone(member.recommendedGrade)}`}>{member.recommendedGrade}</p>
                  <p className={`text-sm font-semibold ${badge.className}`}>{badge.text}</p>
                </div>
              </div>

              <p className="pt-3 text-sm text-slate-600">
                <span className="font-semibold text-slate-800">AI Assessment:</span> {member.aiAssessment}
              </p>
            </article>
          );
        })}
      </section>
    </div>
  );
}
