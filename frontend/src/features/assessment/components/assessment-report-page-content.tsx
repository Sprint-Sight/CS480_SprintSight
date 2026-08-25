"use client";

import { Download, Star, TrendingUp } from "lucide-react";
import { useMemo, useState } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import { getAssessmentProjectOptions, getAssessmentReport } from "@/features/assessment/data";
import type { RubricScore } from "@/features/assessment/types";

function scoreBarColor(score: number) {
  if (score >= 85) return "bg-[#2F5B85]";
  if (score >= 75) return "bg-[#4F89B3]";
  return "bg-[#78B5D9]";
}

function CircularScore({ score }: { score: number }) {
  const radius = 44;
  const circumference = 2 * Math.PI * radius;
  const progress = (score / 100) * circumference;

  return (
    <div className="relative mx-auto flex h-40 w-40 items-center justify-center">
      <svg width="160" height="160" viewBox="0 0 160 160" className="-rotate-90">
        <circle cx="80" cy="80" r={radius} stroke="#dbe6f2" strokeWidth="8" fill="none" />
        <circle
          cx="80"
          cy="80"
          r={radius}
          stroke="#2F5B85"
          strokeWidth="8"
          strokeLinecap="round"
          fill="none"
          strokeDasharray={`${progress} ${circumference - progress}`}
        />
      </svg>
      <div className="absolute text-center">
        <div className="text-5xl font-bold text-blue-950">{score}</div>
      </div>
    </div>
  );
}

export default function AssessmentReportPageContent() {
  const projectOptions = useMemo(() => getAssessmentProjectOptions(), []);
  const [selectedProjectId, setSelectedProjectId] = useState(projectOptions[0]?.id ?? "");
  const report = useMemo(() => getAssessmentReport(selectedProjectId), [selectedProjectId]);

  const radarData = report.rubricScores.map((item) => ({
    category: item.category,
    score: item.score,
  }));

  return (
    <div className="space-y-5 p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-4xl font-bold tracking-tight text-blue-950">AI Assessment Report</h1>
          <p className="mt-1 text-sm text-slate-500">
            {report.teamLabel} - {report.projectLabel} - {report.sprintLabel}
          </p>
        </div>

        <div className="flex w-full max-w-xl flex-wrap justify-end gap-3">
          <div className="min-w-[280px] flex-1">
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

          <button
            type="button"
            className="inline-flex h-11 items-center gap-2 self-end rounded-xl bg-blue-900 px-4 text-sm font-semibold text-white transition hover:bg-blue-950"
          >
            <Download className="h-4 w-4" />
            Download PDF
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-500">Overall Sprint Score</h2>
          <CircularScore score={report.overallScore} />
          <div className="mt-1 flex items-center justify-center gap-1 text-sm font-semibold text-amber-500">
            <Star className="h-4 w-4" />
            <span>Grade {report.overallGrade}</span>
          </div>
          <p className="mt-4 text-center text-sm text-slate-600">{report.overallSummary}</p>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-2xl font-semibold text-blue-950">Rubric Score Breakdown</h2>
          <div className="mt-3 h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid stroke="#dbe6f2" />
                <PolarAngleAxis dataKey="category" tick={{ fill: "#64748b", fontSize: 12 }} />
                <Radar dataKey="score" stroke="#2F5B85" fill="#4F89B3" fillOpacity={0.35} />
                <Tooltip formatter={(value: number) => `${value}%`} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-2xl font-semibold text-blue-950">Category Scores and Justifications</h2>
        <div className="mt-4 space-y-3">
          {report.rubricScores.map((item: RubricScore) => (
            <article key={item.category} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-slate-900">{item.category}</h3>
                <span className="text-sm font-bold text-blue-900">{item.score}%</span>
              </div>
              <div className="h-2 rounded-full bg-slate-200">
                <div className={`h-full rounded-full ${scoreBarColor(item.score)}`} style={{ width: `${item.score}%` }} />
              </div>
              <p className="mt-2 text-sm text-slate-600">{item.justification}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <article className="rounded-2xl border border-emerald-200 bg-emerald-50/40 p-5 shadow-sm">
          <h2 className="text-2xl font-semibold text-emerald-700">Strengths</h2>
          <ul className="mt-3 space-y-2 text-sm text-slate-700">
            {report.strengths.map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-500" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </article>

        <article className="rounded-2xl border border-rose-200 bg-rose-50/40 p-5 shadow-sm">
          <h2 className="text-2xl font-semibold text-rose-700">Weaknesses</h2>
          <ul className="mt-3 space-y-2 text-sm text-slate-700">
            {report.weaknesses.map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="mt-1 h-1.5 w-1.5 rounded-full bg-rose-500" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </article>

        <article className="rounded-2xl border border-blue-200 bg-blue-50/40 p-5 shadow-sm">
          <h2 className="text-2xl font-semibold text-blue-700">Recommendations</h2>
          <ol className="mt-3 space-y-2 text-sm text-slate-700">
            {report.recommendations.map((item, index) => (
              <li key={item} className="flex items-start gap-2">
                <span className="inline-flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-white text-xs font-semibold text-blue-700">
                  {index + 1}
                </span>
                <span>{item}</span>
              </li>
            ))}
          </ol>
        </article>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="flex items-center gap-2 text-2xl font-semibold text-blue-950">
          <TrendingUp className="h-5 w-5" />
          Written Feedback and Justifications
        </h2>
        <div className="mt-3 space-y-2 text-sm text-slate-700">
          {report.narrativeFeedback.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>
        <p className="mt-4 text-xs text-slate-500">Generated: {report.generatedAt}</p>
      </section>
    </div>
  );
}
