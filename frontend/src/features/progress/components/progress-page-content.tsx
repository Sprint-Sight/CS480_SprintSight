"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useState, useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { PROGRESS_DATA } from "@/features/progress/data";
import { getProjectIngestion, readIngestionState } from "@/features/ingestion/state";

const trendLegend = [
  { key: "requirements", label: "Requirements", color: "#1F3D6D" },
  { key: "codeQuality", label: "Code Quality", color: "#2F5B85" },
  { key: "testing", label: "Testing", color: "#3F7C9E" },
  { key: "documentation", label: "Documentation", color: "#5C98BD" },
  { key: "collaboration", label: "Collaboration", color: "#7DB6D9" },
] as const;

function MetricCard({ label, score, delta }: { label: string; score: number; delta: number }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
      <p className="text-xs text-slate-500">{label}</p>
      <div className="mt-1 flex items-end justify-between">
        <p className="text-4xl font-bold text-blue-900">{score}</p>
        <p className={`inline-flex items-center gap-1 text-sm font-semibold ${delta >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
          {delta >= 0 ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
          {delta >= 0 ? `+${delta}` : delta}
        </p>
      </div>
    </div>
  );
}

export default function ProgressPageContent() {
  const [role, setRole] = useState<"student" | "instructor" | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState(() => readIngestionState().selectedProjectId || "");
  const [ingestionVersion, setIngestionVersion] = useState(0);

  useEffect(() => {
    const savedRole = sessionStorage.getItem("sprintsight-auth-role") as "student" | "instructor" | null;
    setRole(savedRole ?? "student"); // Default to student to protect sensitive data
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
    <div className="space-y-5 p-8">
      <div>
        <h1 className="text-4xl font-bold tracking-tight text-blue-950">Comparative Progress</h1>
        <p className="mt-1 text-sm text-slate-500">Track performance trends across multiple sprints and identify improvements or regressions</p>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label="Requirements" score={PROGRESS_DATA.latestScores.requirements} delta={PROGRESS_DATA.scoreDeltas.requirements} />
        <MetricCard label="Code Quality" score={PROGRESS_DATA.latestScores.codeQuality} delta={PROGRESS_DATA.scoreDeltas.codeQuality} />
        <MetricCard label="Testing" score={PROGRESS_DATA.latestScores.testing} delta={PROGRESS_DATA.scoreDeltas.testing} />
        <MetricCard label="Documentation" score={PROGRESS_DATA.latestScores.documentation} delta={PROGRESS_DATA.scoreDeltas.documentation} />
        <MetricCard label="Collaboration" score={PROGRESS_DATA.latestScores.collaboration} delta={PROGRESS_DATA.scoreDeltas.collaboration} />
      </div>

      {(liveIngestion.git || liveIngestion.jira) && (
        <section className="rounded-2xl border border-blue-200 bg-blue-50/50 p-4">
          <h2 className="text-lg font-semibold text-blue-950">Live Ingestion Signals</h2>
          <div className="mt-2 grid grid-cols-1 gap-2 text-sm text-slate-700 md:grid-cols-3">
            <p>Git commits: <strong>{liveIngestion.git?.pagination?.total ?? liveIngestion.git?.commits.length ?? 0}</strong></p>
            <p>Code churn: <strong>{liveIngestion.git?.code_churn ?? 0}</strong></p>
            <p>Jira tickets: <strong>{liveIngestion.jira?.tickets.length ?? 0}</strong></p>
          </div>
        </section>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-xl font-semibold text-blue-950">Category Trends Over Sprints</h2>
        <div className="mt-3 h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={PROGRESS_DATA.categoryTrend}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="sprint" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
              <YAxis domain={[40, 100]} axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
              <Tooltip />
              {trendLegend.map((line) => (
                <Line
                  key={line.key}
                  type="monotone"
                  dataKey={line.key}
                  name={line.label}
                  stroke={line.color}
                  strokeWidth={2}
                  dot={{ r: 3, fill: "#fff", strokeWidth: 2 }}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Conditionally render instructor-only views */}
      {role === "instructor" && (
        <>
          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-xl font-semibold text-blue-950">Team Comparison Across Sprints</h2>
            <div className="mt-3 h-[260px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={PROGRESS_DATA.teamComparison}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="team" axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                  <YAxis domain={[50, 100]} axisLine={false} tickLine={false} tick={{ fill: "#64748b", fontSize: 12 }} />
                  <Tooltip />
                  <Legend />
                  <Bar dataKey="sprint3" name="Sprint3" fill="#5C98BD" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="sprint4" name="Sprint4" fill="#3F7C9E" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="sprint5" name="Sprint5" fill="#1F3D6D" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-xl font-semibold text-blue-950">Regression Alerts</h2>
            <div className="mt-3 space-y-2">
              {PROGRESS_DATA.regressionAlerts.map((alert) => (
                <article key={alert.id} className="rounded-xl border border-rose-200 bg-rose-50/40 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-rose-700">
                      {alert.team} - {alert.category}
                    </p>
                    <p className="text-sm font-bold text-rose-700">{alert.toScore - alert.fromScore}</p>
                  </div>
                  <p className="text-xs text-rose-600">
                    Score dropped from {alert.fromScore} to {alert.toScore} ({alert.fromSprint} to {alert.toSprint})
                  </p>
                </article>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}