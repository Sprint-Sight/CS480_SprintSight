"use client";

import { Download, Loader2, Play, Star, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import { getAssessmentProjectOptions, getAssessmentReport } from "@/features/assessment/data";
import { API_BASE_URL, apiRequest, getAuthToken, isUuid } from "@/features/projects/components/projects-api";
import type { RubricScore } from "@/features/assessment/types";

type AssessmentProjectOption = {
  id: string;
  courseId?: string;
  label: string;
};

type BackendAssessmentReport = {
  report_id: string;
  model_name: string;
  mode: string;
  course_id: string;
  project_id: string;
  sprint_id: string;
  generated_at: string;
  rubric_weights: Record<string, number>;
  team_score: { score: number; rationale: string };
  individual_scores: Array<{ student_id: string; score: number; rationale: string }>;
  recommendations: string[];
};

type AssessmentJobEvent = {
  status?: string;
  progress?: number;
  message?: string;
  report_id?: string;
  error_message?: string;
};

const assessmentModels = [
  { id: "sprintsight-llama", label: "SprintSight Llama" },
  { id: "sprintsight-mistral", label: "SprintSight Mistral" },
  { id: "sprintsight-qwen", label: "SprintSight Qwen" },
  { id: "sprintsight-gemma", label: "SprintSight Gemma" },
] as const;

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
  const fallbackProjectOptions = useMemo(() => getAssessmentProjectOptions(), []);
  const [projectOptions, setProjectOptions] = useState<AssessmentProjectOption[]>(fallbackProjectOptions);
  const [selectedProjectId, setSelectedProjectId] = useState(fallbackProjectOptions[0]?.id ?? "");
  const [sprintId, setSprintId] = useState("sprint-1");
  const [modelName, setModelName] = useState("sprintsight-llama");
  const [report, setReport] = useState(() => getAssessmentReport(fallbackProjectOptions[0]?.id ?? ""));
  const [isLoadingReport, setIsLoadingReport] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [assessmentProgress, setAssessmentProgress] = useState(0);
  const [assessmentMessage, setAssessmentMessage] = useState("");
  const [assessmentError, setAssessmentError] = useState("");

  useEffect(() => {
    async function loadBackendProjects() {
      try {
        const courses = await apiRequest<Array<{ id: string }>>("/courses");
        const groups = await Promise.all(courses.map(async (course) => ({
          courseId: course.id,
          projects: await apiRequest<Array<{ id: string; team_name: string; project_name: string }>>(`/courses/${course.id}/projects`),
        })));
        const options = groups.flatMap(({ courseId, projects }) => projects.map((project) => ({
          id: project.id,
          courseId,
          label: `${project.team_name} - ${project.project_name}`,
        })));
        if (options.length > 0) {
          setProjectOptions(options);
          setSelectedProjectId(options[0].id);
        }
      } catch {
        // Demo fixture options remain available when backend projects are unavailable.
      }
    }

    loadBackendProjects();
  }, []);

  async function loadLatestReport(projectId = selectedProjectId, sprint = sprintId) {
    const project = projectOptions.find((option) => option.id === projectId);
    if (!isUuid(projectId) || !project?.courseId || !sprint.trim()) {
      setReport(getAssessmentReport(projectId));
      return;
    }

    setIsLoadingReport(true);
    setAssessmentError("");
    try {
      const backendReport = await apiRequest<BackendAssessmentReport>(
        `/assessments/latest?course_id=${encodeURIComponent(project.courseId)}&project_id=${encodeURIComponent(projectId)}&sprint_id=${encodeURIComponent(sprint.trim())}`
      );
      setReport({
        projectId: backendReport.project_id,
        sprintId: backendReport.sprint_id,
        sprintLabel: backendReport.sprint_id,
        teamLabel: project.label.split(" - ")[0] || "Project team",
        projectLabel: project.label.split(" - ").slice(1).join(" - ") || project.label,
        generatedAt: new Date(backendReport.generated_at).toLocaleString(),
        overallScore: Math.round(backendReport.team_score.score),
        overallGrade: backendReport.team_score.score >= 85 ? "A" : backendReport.team_score.score >= 75 ? "B" : "C",
        overallSummary: backendReport.team_score.rationale,
        rubricScores: Object.entries(backendReport.rubric_weights).map(([category, weight]) => ({
          category: category as RubricScore["category"],
          score: Math.round(backendReport.team_score.score),
          justification: `${Math.round(weight * 100)}% rubric weight.`,
        })),
        strengths: [],
        weaknesses: [],
        recommendations: backendReport.recommendations,
        narrativeFeedback: backendReport.individual_scores.map((score) => `${score.student_id}: ${score.rationale}`),
      });
    } catch (error) {
      setAssessmentError(error instanceof Error ? error.message : "Failed to load the latest assessment.");
    } finally {
      setIsLoadingReport(false);
    }
  }

  async function generateAssessment() {
    const project = projectOptions.find((option) => option.id === selectedProjectId);
    if (!isUuid(selectedProjectId) || !project?.courseId || !sprintId.trim()) {
      setAssessmentError("Select a backend project and enter a sprint ID before generating an assessment.");
      return;
    }

    setAssessmentError("");
    setIsGenerating(true);
    setAssessmentProgress(0);
    setAssessmentMessage("Starting assessment...");
    try {
      const job = await apiRequest<{ job_id: string }>("/assessments/assess", {
        method: "POST",
        body: JSON.stringify({
          course_id: project.courseId,
          project_id: selectedProjectId,
          sprint_id: sprintId.trim(),
          model_name: modelName,
        }),
      });
      const token = getAuthToken();
      if (!token) throw new Error("Your session has expired. Please log in again.");

      const eventsResponse = await fetch(`${API_BASE_URL}/assessments/jobs/${job.job_id}/events`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!eventsResponse.ok || !eventsResponse.body) throw new Error("Could not monitor assessment progress.");

      const reader = eventsResponse.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let finished = false;
      while (!finished) {
        const chunk = await reader.read();
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const event of events) {
          const dataLine = event.split("\n").find((line) => line.startsWith("data: "));
          if (!dataLine) continue;
          const data = JSON.parse(dataLine.slice(6)) as AssessmentJobEvent;
          setAssessmentProgress(data.progress ?? 0);
          setAssessmentMessage(data.message || data.status || "Assessment in progress...");
          if (data.status === "failed") throw new Error(data.error_message || "Assessment failed.");
          if (data.status === "completed") finished = true;
        }
      }
      await loadLatestReport(selectedProjectId, sprintId);
    } catch (error) {
      setAssessmentError(error instanceof Error ? error.message : "Assessment generation failed.");
    } finally {
      setIsGenerating(false);
    }
  }

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

        <div className="flex w-full max-w-2xl flex-wrap justify-end gap-3">
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

          <label className="min-w-[150px] space-y-1">
            <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500">Sprint ID</span>
            <input
              value={sprintId}
              onChange={(event) => setSprintId(event.target.value)}
              className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
              placeholder="sprint-1"
            />
          </label>

          <label className="min-w-[180px] space-y-1">
            <span className="block text-xs font-semibold uppercase tracking-wider text-slate-500">Assessment Model</span>
            <select
              value={modelName}
              onChange={(event) => setModelName(event.target.value)}
              className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-700 outline-none focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            >
              {assessmentModels.map((model) => (
                <option key={model.id} value={model.id}>{model.label}</option>
              ))}
            </select>
          </label>

          <button
            type="button"
            onClick={() => loadLatestReport()}
            disabled={isLoadingReport || isGenerating}
            className="inline-flex h-11 items-center gap-2 self-end rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
          >
            {isLoadingReport ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Load Latest
          </button>

          <button
            type="button"
            onClick={generateAssessment}
            disabled={isGenerating || isLoadingReport}
            className="inline-flex h-11 items-center gap-2 self-end rounded-xl bg-blue-900 px-4 text-sm font-semibold text-white transition hover:bg-blue-950 disabled:opacity-50"
          >
            {isGenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {isGenerating ? "Generating..." : "Generate Assessment"}
          </button>

          <button
            type="button"
            className="inline-flex h-11 items-center gap-2 self-end rounded-xl bg-blue-900 px-4 text-sm font-semibold text-white transition hover:bg-blue-950"
          >
            <Download className="h-4 w-4" />
            Download PDF
          </button>
        </div>
      </div>

      {assessmentMessage && (isGenerating || assessmentProgress > 0) && (
        <div className="rounded-xl border border-blue-100 bg-blue-50 p-3 text-sm text-blue-800">
          <div className="flex items-center justify-between gap-3">
            <span>{assessmentMessage}</span>
            <span className="font-semibold">{assessmentProgress}%</span>
          </div>
          <div className="mt-2 h-2 rounded-full bg-blue-100">
            <div className="h-full rounded-full bg-blue-700 transition-all" style={{ width: `${assessmentProgress}%` }} />
          </div>
        </div>
      )}
      {assessmentError && <p className="text-sm text-rose-600">{assessmentError}</p>}

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
